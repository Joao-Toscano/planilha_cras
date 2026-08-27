"""
Camada de dados do app CRAS.
Usa PostgreSQL (Supabase) como substituto das abas "Ficha" e
"Base" / "Base 2025 - 2026" da planilha original — banco na nuvem, fora do
disco temporário do Streamlit Cloud, então os dados não somem quando o app
dorme/reinicia.
"""
import json
import psycopg2
import psycopg2.extensions
import psycopg2.extras
import psycopg2.pool
import streamlit as st
from pathlib import Path
from datetime import date, datetime

MEDICOS_SEED = Path(__file__).parent / "data" / "medicos.json"
BASE_HISTORICO_SEED = Path(__file__).parent / "data" / "base_historico.json"
AGENDAS_SEED = Path(__file__).parent / "data" / "agendas_2026.json"
FALTAS_SEED = Path(__file__).parent / "data" / "faltas_profissionais_2026.json"

NOMES_MES = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
NOMES_DIA = ["Segunda-feira", "Terca-feira", "Quarta-feira", "Quinta-feira",
             "Sexta-feira", "Sabado", "Domingo"]  # Python weekday(): 0=segunda


def nome_mes(d: date) -> str:
    return NOMES_MES[d.month - 1]


def nome_dia(d: date) -> str:
    return NOMES_DIA[d.weekday()]


# ---------------------------------------------------------------------
# Camada de compatibilidade: o restante deste arquivo foi escrito no
# estilo do sqlite3 (placeholders "?", conn.execute(...) direto, linhas
# acessíveis tanto por posição linha[0] quanto por nome linha["coluna"]).
# Essas classes traduzem isso para o psycopg2/PostgreSQL sem precisar
# reescrever cada consulta espalhada pelo arquivo.
# ---------------------------------------------------------------------

class PGRow:
    """Imita sqlite3.Row: aceita índice numérico (linha[0]) e por nome
    (linha["coluna"]), e dict(linha) funciona também."""
    __slots__ = ("_data", "_cols")

    def __init__(self, data, cols):
        self._data = data
        self._cols = cols

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[key]
        return self._data[self._cols.index(key)]

    def get(self, key, default=None):
        try:
            return self[key]
        except (ValueError, IndexError):
            return default

    def keys(self):
        return self._cols

    def __iter__(self):
        return iter(self._data)

    def __repr__(self):
        return repr(dict(zip(self._cols, self._data)))


class PGCursor:
    def __init__(self, cur):
        self._cur = cur

    def _cols(self):
        return [d[0] for d in self._cur.description] if self._cur.description else []

    def execute(self, sql, params=()):
        self._cur.execute(sql.replace("?", "%s"), params)
        return self

    def executemany(self, sql, seq_params):
        self._cur.executemany(sql.replace("?", "%s"), list(seq_params))
        return self

    def execute_values(self, sql, argslist):
        """Manda várias linhas numa ÚNICA instrução SQL de verdade (uma
        viagem ao banco, não uma por linha) — ao contrário de executemany(),
        que o psycopg2 executa linha por linha por baixo dos panos mesmo
        parecendo 'em lote'. Use isso para inserções grandes (centenas ou
        milhares de linhas). O sql deve ter um único 'VALUES %s' no lugar
        da lista de parênteses."""
        if not argslist:
            return self
        psycopg2.extras.execute_values(self._cur, sql.replace("?", "%s"), argslist)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return None if row is None else PGRow(row, self._cols())

    def fetchall(self):
        cols = self._cols()
        return [PGRow(r, cols) for r in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def description(self):
        return self._cur.description

    def __getattr__(self, name):
        return getattr(self._cur, name)


class PGConnection:
    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool

    def cursor(self):
        return PGCursor(self._conn.cursor())

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # Com pool: devolve a conexão para reuso em vez de fechar de verdade
        # (abrir uma conexão nova a cada consulta é o que estava deixando o
        # app lento — cada conexão nova até o Supabase custa uma viagem de
        # ida e volta pela internet + autenticação).
        if self._pool is not None:
            try:
                # Garante que não sobra transação pendente "contaminando" a
                # conexão para o próximo uso (caso algum código tenha
                # esquecido de dar commit/rollback antes de fechar).
                self._conn.rollback()
            except Exception:
                pass
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
        else:
            self._conn.close()


def _get_db_url():
    """Lê a connection string do Postgres/Supabase das Secrets do Streamlit
    (chave 'supabase_db_url'). Levanta um erro claro se não encontrar."""
    try:
        import streamlit as st
        url = st.secrets.get("supabase_db_url")
    except Exception:
        url = None
    if not url:
        import os
        url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "Não encontrei a chave 'supabase_db_url' nas Secrets do Streamlit. "
            "Configure em Settings > Secrets do app (ou em .streamlit/secrets.toml "
            "localmente) com: supabase_db_url = \"postgresql://...\""
        )
    return url


# Pool de conexões reaproveitáveis — criado uma única vez por processo (fica
# vivo entre as reexecuções do script que o Streamlit faz a cada interação),
# em vez de abrir/fechar uma conexão nova pela internet a cada consulta.
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=_get_db_url(), connect_timeout=10
        )
    return _pool


def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    return PGConnection(conn, pool)


def _limpar_cache():
    """Chamado depois de qualquer escrita, para que a tela mostre os dados
    atualizados na hora em vez de esperar o cache expirar sozinho."""
    st.cache_data.clear()


_ja_inicializado = None  # None = ainda não rodou; depois vira o resultado, cacheado


def init_db():
    # init_db() era chamado sem condição a cada interação (o Streamlit reexecuta
    # o script inteiro a cada clique). Isso significava reenviar ~2.000 linhas
    # do histórico pela internet pra conferir "já existe?" a cada clique —
    # a causa real da lentidão. Agora só roda de verdade uma vez por processo
    # (a primeira vez que o app inicia depois de um deploy/reinício); nas
    # próximas chamadas, devolve o resultado já calculado na hora.
    global _ja_inicializado
    if _ja_inicializado is not None:
        return _ja_inicializado

    conn = get_conn()
    try:
        resultado = _init_db_interno(conn)
    finally:
        # Garante que a conexão sempre volta pro pool, mesmo se algo no meio
        # do processo der erro — antes, um erro aqui deixava a conexão presa
        # pra sempre, esvaziando o pool aos poucos até estourar.
        conn.close()

    _ja_inicializado = resultado
    return _ja_inicializado


def _init_db_interno(conn):
    cur = conn.cursor()

    avisos = []
    erros = []

    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicos (
            id SERIAL PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL,
            especialidade TEXT,
            cod TEXT,
            meta INTEGER
        )
    """)

    # Ficha: um registro por atendimento (equivalente à aba "Ficha")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ficha (
            id SERIAL PRIMARY KEY,
            nr_cras TEXT,
            data TEXT NOT NULL,
            mes TEXT,
            dia_semana TEXT,
            turno TEXT,
            ordem INTEGER,
            medico TEXT,
            especialidade TEXT,
            matricula TEXT,
            nome_usuario TEXT,
            assistido TEXT,
            servidor TEXT,
            consulta TEXT,
            status TEXT DEFAULT 'Realizado',
            motivo TEXT,
            criado_em TEXT
        )
    """)


    # Base: um registro por (data, médico) - equivalente às abas "Base" / "Base 2025 - 2026"
    cur.execute("""
        CREATE TABLE IF NOT EXISTS base (
            id SERIAL PRIMARY KEY,
            data TEXT NOT NULL,
            mes TEXT,
            dia_semana TEXT,
            medico TEXT,
            especialidade TEXT,
            cod_medico TEXT,
            discentes_assistidos INTEGER DEFAULT 0,
            discentes_naoassistidos INTEGER DEFAULT 0,
            atendidos_servidores INTEGER DEFAULT 0,
            faltosos INTEGER DEFAULT 0,
            falta_profissional INTEGER DEFAULT 0,
            agendados INTEGER,
            total_atendidos INTEGER DEFAULT 0,
            meta INTEGER,
            absenteismo REAL,
            ocupacao REAL,
            classif_absenteismo TEXT,
            classif_ocupacao TEXT,
            classif_desempenho TEXT,
            UNIQUE(data, medico)
        )
    """)

    conn.commit()

    # Migração defensiva: se já existir um cras.db de uma versão anterior
    # (sem as colunas de agregados), adiciona as colunas que faltarem, para
    # não falhar silenciosamente nem quebrar com "no such column".
    colunas_esperadas = {
        "discentes_assistidos": "INTEGER DEFAULT 0",
        "discentes_naoassistidos": "INTEGER DEFAULT 0",
        "atendidos_servidores": "INTEGER DEFAULT 0",
        "faltosos": "INTEGER DEFAULT 0",
        "falta_profissional": "INTEGER DEFAULT 0",
        "agendados": "INTEGER",
        "total_atendidos": "INTEGER DEFAULT 0",
        "meta": "INTEGER",
        "absenteismo": "REAL",
        "ocupacao": "REAL",
        "classif_absenteismo": "TEXT",
        "classif_ocupacao": "TEXT",
        "classif_desempenho": "TEXT",
    }
    colunas_existentes = {row[0] for row in cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'base'")}
    for col, tipo in colunas_esperadas.items():
        if col not in colunas_existentes:
            cur.execute(f"ALTER TABLE base ADD COLUMN {col} {tipo}")
            avisos.append(f"Coluna '{col}' estava faltando na tabela 'base' (banco de uma versão "
                           f"anterior) — adicionada automaticamente.")
    conn.commit()

    # Migração da tabela 'ficha': troca o antigo campo tri-state
    # 'falta_profissional' por 'status' (por atendimento individual).
    colunas_ficha = {row[0] for row in cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'ficha'")}
    if "status" not in colunas_ficha:
        cur.execute("ALTER TABLE ficha ADD COLUMN status TEXT DEFAULT 'Realizado'")
        if "falta_profissional" in colunas_ficha:
            # Registros antigos marcados como falta viram 'Falta do profissional';
            # os demais (inclusive os sem essa coluna) assumem 'Realizado'.
            cur.execute("""
                UPDATE ficha SET status = CASE
                    WHEN falta_profissional IS NOT NULL AND falta_profissional != 'Presença'
                    THEN 'Falta do profissional' ELSE 'Realizado' END
            """)
        avisos.append("Coluna 'status' adicionada à tabela 'ficha' (banco de uma versão anterior).")
        conn.commit()
    if "consulta" not in colunas_ficha:
        cur.execute("ALTER TABLE ficha ADD COLUMN consulta TEXT")
        avisos.append("Coluna 'consulta' adicionada à tabela 'ficha' (banco de uma versão anterior).")
        conn.commit()
    if "motivo" not in colunas_ficha:
        cur.execute("ALTER TABLE ficha ADD COLUMN motivo TEXT")
        avisos.append("Coluna 'motivo' adicionada à tabela 'ficha' (banco de uma versão anterior).")
        conn.commit()

    # Sincroniza médicos: roda sempre (não só na primeira vez), usando
    # INSERT OR IGNORE, para preencher automaticamente qualquer médico que
    # esteja faltando — inclusive se o banco já existia de uma versão
    # anterior com uma lista incompleta. Não duplica quem já existe.
    if MEDICOS_SEED.exists():
        medicos = json.loads(MEDICOS_SEED.read_text(encoding="utf-8"))
        antes = cur.execute("SELECT COUNT(*) FROM medicos").fetchone()[0]
        cur.execute_values(
            "INSERT INTO medicos (id, nome, especialidade, cod, meta) VALUES %s "
            "ON CONFLICT (id) DO NOTHING",
            [(m["id"], m["nome"], m["especialidade"], m["cod"], m["meta"]) for m in medicos]
        )
        conn.commit()
        depois = cur.execute("SELECT COUNT(*) FROM medicos").fetchone()[0]
        if depois > antes:
            avisos.append(f"{depois - antes} médico(s) que estavam faltando no banco foram "
                           f"adicionados automaticamente (total agora: {depois}).")
    else:
        erros.append(f"Arquivo de médicos não encontrado em: {MEDICOS_SEED}")

    # Como os médicos do histórico entram com id explícito (do JSON), a
    # sequência do SERIAL precisa ser adiantada manualmente, senão um novo
    # médico cadastrado pela tela poderia tentar usar um id já existente.
    cur.execute(
        "SELECT setval(pg_get_serial_sequence('medicos','id'), "
        "COALESCE((SELECT MAX(id) FROM medicos), 1))"
    )
    conn.commit()

    # Sincroniza o histórico da mesma forma: roda sempre, usando INSERT OR
    # IGNORE (a restrição UNIQUE(data, medico) evita duplicar registros já
    # existentes) — preenche automaticamente qualquer linha do histórico que
    # ainda esteja faltando.
    if BASE_HISTORICO_SEED.exists():
        registros = json.loads(BASE_HISTORICO_SEED.read_text(encoding="utf-8"))
        antes = cur.execute("SELECT COUNT(*) FROM base").fetchone()[0]
        cur.execute_values("""
            INSERT INTO base
                (data, mes, dia_semana, medico, especialidade, cod_medico,
                 discentes_assistidos, discentes_naoassistidos, atendidos_servidores,
                 faltosos, falta_profissional, agendados, total_atendidos, meta,
                 absenteismo, ocupacao, classif_absenteismo, classif_ocupacao, classif_desempenho)
            VALUES %s
            ON CONFLICT (data, medico) DO NOTHING
        """, [
            (r["data"], r["mes"], r["dia_semana"], r["medico"], r["especialidade"], r["cod_medico"],
             r["discentes_assistidos"], r["discentes_naoassistidos"], r["atendidos_servidores"],
             r["faltosos"], r["falta_profissional"], r["agendados"], r["total_atendidos"], r["meta"],
             r["absenteismo"], r["ocupacao"], r["classif_absenteismo"], r["classif_ocupacao"],
             r["classif_desempenho"])
            for r in registros
        ])
        conn.commit()
        depois = cur.execute("SELECT COUNT(*) FROM base").fetchone()[0]
        if depois > antes:
            avisos.append(f"{depois - antes} registro(s) do histórico que estavam faltando foram "
                           f"adicionados automaticamente (total agora: {depois}).")
    else:
        erros.append(f"Arquivo de histórico não encontrado em: {BASE_HISTORICO_SEED}")

    # Importa as agendas de 2026 (Nutrição/Odontologia) uma única vez — como
    # esses atendimentos não têm uma chave natural pra evitar duplicar (ao
    # contrário do histórico, que usa UNIQUE(data,medico)), o controle é
    # feito por uma marca salva em 'config' assim que termina.
    # IMPORTANTE: isso é feito em LOTE (poucas idas ao banco), não um
    # atendimento de cada vez — com ~1.800 registros, inserir um por um
    # significaria milhares de viagens de ida e volta até o Supabase pela
    # internet, o que estourava o tempo do processo antes de terminar.
    if AGENDAS_SEED.exists():
        ja_importado = cur.execute(
            "SELECT valor FROM config WHERE chave = 'agendas_2026_importadas'"
        ).fetchone()
        if not ja_importado:
            dados_agenda = json.loads(AGENDAS_SEED.read_text(encoding="utf-8"))

            # 1) Médicos novos que a agenda trouxe e ainda não existem
            for medico_novo in dados_agenda.get("medicos_novos", []):
                cur.execute(
                    "INSERT INTO medicos (nome, especialidade, cod, meta) VALUES (?,?,?,?) "
                    "ON CONFLICT (nome) DO NOTHING",
                    (medico_novo["nome"], medico_novo["especialidade"],
                     medico_novo["cod"], medico_novo["meta"])
                )
            conn.commit()
            medicos_cache = {m["nome"]: m for m in
                              [dict(r) for r in cur.execute("SELECT * FROM medicos")]}

            # 2) Monta todas as linhas da Ficha de uma vez
            linhas_ficha = []
            deltas_base = {}  # (data, medico) -> incrementos agregados

            def _delta(data_iso, medico):
                chave = (data_iso, medico)
                if chave not in deltas_base:
                    deltas_base[chave] = {
                        "discentes_assistidos": 0, "discentes_naoassistidos": 0,
                        "atendidos_servidores": 0, "faltosos": 0, "total_atendidos": 0,
                        "especialidade": "", "cod_medico": "", "meta": None,
                    }
                return deltas_base[chave]

            for at in dados_agenda.get("atendimentos", []):
                med = medicos_cache.get(at["medico"], {})
                especialidade = med.get("especialidade") or ""
                cod_medico = med.get("cod") or ""
                status = "Falta do usuário" if at["faltou"] else "Realizado"
                assistido = "Sim" if at["categoria"] == "assistido" else "Não"
                servidor = "Sim" if at["categoria"] == "servidor" else "Não"
                data_obj = date.fromisoformat(at["data"])

                linhas_ficha.append((
                    at["nr_cras"], at["data"], nome_mes(data_obj), nome_dia(data_obj), "",
                    None, at["medico"], especialidade, at["matricula"], at["nome_usuario"],
                    assistido, servidor, at["consulta"], status, None,
                    datetime.now().isoformat(timespec="seconds"),
                ))

                d = _delta(at["data"], at["medico"])
                d["especialidade"] = especialidade
                d["cod_medico"] = cod_medico
                d["meta"] = med.get("meta")
                if not at["faltou"]:
                    d["total_atendidos"] += 1
                    if at["categoria"] == "assistido":
                        d["discentes_assistidos"] += 1
                    elif at["categoria"] == "servidor":
                        d["atendidos_servidores"] += 1
                    else:
                        d["discentes_naoassistidos"] += 1
                else:
                    d["faltosos"] += 1

            for dia in dados_agenda.get("dias_especiais", []):
                med = medicos_cache.get(dia["medico"], {})
                data_obj = date.fromisoformat(dia["data"])
                linhas_ficha.append((
                    None, dia["data"], nome_mes(data_obj), nome_dia(data_obj), "",
                    None, dia["medico"], med.get("especialidade") or "", None, None,
                    "Não", "Não", None, "Falta do profissional", dia["motivo"],
                    datetime.now().isoformat(timespec="seconds"),
                ))
                d = _delta(dia["data"], dia["medico"])
                d["especialidade"] = med.get("especialidade") or ""
                d["cod_medico"] = med.get("cod") or ""
                d["meta"] = med.get("meta")
                d["faltosos"] += 1

            # 3) Grava tudo na Ficha numa única operação em lote (de verdade)
            if linhas_ficha:
                cur.execute_values("""
                    INSERT INTO ficha (nr_cras, data, mes, dia_semana, turno, ordem, medico,
                                        especialidade, matricula, nome_usuario, assistido,
                                        servidor, consulta, status, motivo, criado_em)
                    VALUES %s
                """, linhas_ficha)
                conn.commit()

            # 4) Atualiza a Base com os totais agregados, também em lote —
            # usa EXCLUDED (o valor que se tentou inserir) em vez de repetir
            # os valores na query, o que também permite usar execute_values
            linhas_base = []
            for (data_iso, medico), d in deltas_base.items():
                data_obj = date.fromisoformat(data_iso)
                linhas_base.append((
                    data_iso, nome_mes(data_obj), nome_dia(data_obj), medico,
                    d["especialidade"], d["cod_medico"],
                    d["discentes_assistidos"], d["discentes_naoassistidos"],
                    d["atendidos_servidores"], d["faltosos"], d["total_atendidos"], d["meta"],
                ))
            if linhas_base:
                cur.execute_values("""
                    INSERT INTO base (data, mes, dia_semana, medico, especialidade, cod_medico,
                                       discentes_assistidos, discentes_naoassistidos,
                                       atendidos_servidores, faltosos, total_atendidos, meta)
                    VALUES %s
                    ON CONFLICT (data, medico) DO UPDATE SET
                        discentes_assistidos = base.discentes_assistidos + EXCLUDED.discentes_assistidos,
                        discentes_naoassistidos = base.discentes_naoassistidos + EXCLUDED.discentes_naoassistidos,
                        atendidos_servidores = base.atendidos_servidores + EXCLUDED.atendidos_servidores,
                        faltosos = base.faltosos + EXCLUDED.faltosos,
                        total_atendidos = base.total_atendidos + EXCLUDED.total_atendidos
                """, linhas_base)
                conn.commit()

            set_config("agendas_2026_importadas", datetime.now().isoformat(timespec="seconds"))
            avisos.append(
                f"{len(dados_agenda.get('atendimentos', []))} atendimentos e "
                f"{len(dados_agenda.get('dias_especiais', []))} dias especiais das agendas 2026 "
                f"(Nutrição/Odontologia) importados automaticamente em lote."
            )

    # Importa as faltas profissionais do relatório anual de diagnóstico —
    # mesma lógica (uma vez só, em lote, marcado por uma flag no config).
    # Os dias que já tinham vindo da agenda mensal (Férias/Atestado) foram
    # excluídos deste arquivo antes de gerar o JSON, para não contar em dobro.
    if FALTAS_SEED.exists():
        ja_importado_faltas = cur.execute(
            "SELECT valor FROM config WHERE chave = 'faltas_profissionais_2026_importadas'"
        ).fetchone()
        if not ja_importado_faltas:
            faltas = json.loads(FALTAS_SEED.read_text(encoding="utf-8"))
            medicos_cache2 = {m["nome"]: m for m in
                              [dict(r) for r in cur.execute("SELECT * FROM medicos")]}

            linhas_ficha_falta = []
            deltas_falta = {}
            for f in faltas:
                med = medicos_cache2.get(f["medico"], {})
                data_obj = date.fromisoformat(f["data"])
                linhas_ficha_falta.append((
                    None, f["data"], nome_mes(data_obj), nome_dia(data_obj), "",
                    None, f["medico"], med.get("especialidade") or "", None, None,
                    "Não", "Não", None, "Falta do profissional", f["motivo"],
                    datetime.now().isoformat(timespec="seconds"),
                ))
                chave = (f["data"], f["medico"])
                if chave not in deltas_falta:
                    deltas_falta[chave] = {
                        "especialidade": med.get("especialidade") or "",
                        "cod_medico": med.get("cod") or "",
                        "meta": med.get("meta"),
                        "faltosos": 0,
                        "falta_profissional": 0,
                    }
                deltas_falta[chave]["faltosos"] += 1
                deltas_falta[chave]["falta_profissional"] = 1 if f["motivo"] == "Falta" else 2

            if linhas_ficha_falta:
                cur.execute_values("""
                    INSERT INTO ficha (nr_cras, data, mes, dia_semana, turno, ordem, medico,
                                        especialidade, matricula, nome_usuario, assistido,
                                        servidor, consulta, status, motivo, criado_em)
                    VALUES %s
                """, linhas_ficha_falta)
                conn.commit()

            linhas_base_falta = []
            for (data_iso, medico), d in deltas_falta.items():
                data_obj = date.fromisoformat(data_iso)
                linhas_base_falta.append((
                    data_iso, nome_mes(data_obj), nome_dia(data_obj), medico,
                    d["especialidade"], d["cod_medico"],
                    d["faltosos"], d["falta_profissional"], d["meta"],
                ))
            if linhas_base_falta:
                cur.execute_values("""
                    INSERT INTO base (data, mes, dia_semana, medico, especialidade, cod_medico,
                                       faltosos, falta_profissional, meta)
                    VALUES %s
                    ON CONFLICT (data, medico) DO UPDATE SET
                        faltosos = base.faltosos + EXCLUDED.faltosos,
                        falta_profissional = EXCLUDED.falta_profissional
                """, linhas_base_falta)
                conn.commit()

            set_config("faltas_profissionais_2026_importadas",
                       datetime.now().isoformat(timespec="seconds"))
            avisos.append(
                f"{len(faltas)} faltas profissionais (relatório anual de diagnóstico) "
                f"importadas automaticamente em lote."
            )

    conn.commit()
    return {"info": avisos, "erros": erros}


@st.cache_data(ttl=30)
def listar_medicos():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM medicos ORDER BY nome").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def buscar_medico(nome: str):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM medicos WHERE nome = ?", (nome,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def adicionar_medico(nome: str, especialidade: str, cod: str, meta):
    """
    Adiciona um novo profissional à lista de médicos. Retorna (True, None) em
    caso de sucesso, ou (False, mensagem) se o nome já existir ou os dados
    forem inválidos.
    """
    nome = (nome or "").strip()
    if not nome:
        return False, "O nome não pode ficar em branco."

    if buscar_medico(nome):
        return False, f"Já existe um médico cadastrado com o nome '{nome}'."

    conn = get_conn()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO medicos (nome, especialidade, cod, meta) VALUES (?,?,?,?)",
                (nome, (especialidade or "").strip(), (cod or "").strip(), meta)
            )
            conn.commit()
        except psycopg2.Error as e:
            conn.rollback()
            return False, f"Não foi possível salvar: {e}"
    finally:
        conn.close()
    _limpar_cache()
    return True, None


def remover_medico(nome: str):
    """Remove um médico da lista de cadastro (não apaga atendimentos já
    lançados em seu nome, apenas tira das opções do formulário)."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM medicos WHERE nome = ?", (nome,))
        conn.commit()
    finally:
        conn.close()
    _limpar_cache()


def salvar_atendimento(nr_cras, data_atendimento: date, medico, turno, usuario,
                        nr_matricula, categoria, consulta="Primeira consulta"):
    """
    categoria: 'servidor' | 'assistido' | 'discente'
    consulta: 'Primeira consulta' | 'Retorno' | 'Acompanhamento/tratamento'
              (equivale aos códigos 0/1/2 do Mapa de Atendimento impresso)
    Equivale à macro SalvarNaBase do arquivo original.
    O atendimento entra como status='Realizado' — use atualizar_status_atendimento()
    depois, na revisão do dia, se precisar marcar que não ocorreu.
    """
    med = buscar_medico(medico)
    especialidade = med["especialidade"] if med else ""
    cod_medico = med["cod"] if med else ""

    assistido = "Sim" if categoria == "assistido" else "Não"
    servidor = "Sim" if categoria == "servidor" else "Não"

    conn = get_conn()
    try:
        cur = conn.cursor()

        # Ordem: quantos atendimentos esse usuário já teve (equivalente à fórmula COUNTIFS da coluna F)
        ordem = cur.execute(
            "SELECT COUNT(*) FROM ficha WHERE nome_usuario = ?", (usuario,)
        ).fetchone()[0] + 1

        cur.execute("""
            INSERT INTO ficha (nr_cras, data, mes, dia_semana, turno, ordem, medico,
                                especialidade, matricula, nome_usuario, assistido, servidor,
                                consulta, status, criado_em)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (nr_cras, data_atendimento.isoformat(), nome_mes(data_atendimento),
              nome_dia(data_atendimento), turno, ordem, medico, especialidade,
              nr_matricula, usuario, assistido, servidor, consulta, "Realizado",
              datetime.now().isoformat(timespec="seconds")))

        # Base: um registro agregado por (data, médico). Usa UPSERT atômico
        # (INSERT ... ON CONFLICT) em vez de "verificar se existe, depois inserir
        # ou atualizar" — esse padrão em dois passos tem uma condição de corrida
        # real quando duas pessoas salvam pro mesmo dia/médico ao mesmo tempo.
        meta = med["meta"] if med else None
        campo = {"assistido": "discentes_assistidos",
                 "discente": "discentes_naoassistidos",
                 "servidor": "atendidos_servidores"}[categoria]

        cur.execute(f"""
            INSERT INTO base (data, mes, dia_semana, medico, especialidade, cod_medico,
                               discentes_assistidos, discentes_naoassistidos, atendidos_servidores,
                               total_atendidos, meta)
            VALUES (?,?,?,?,?,?,?,?,?,1,?)
            ON CONFLICT (data, medico) DO UPDATE SET
                {campo} = base.{campo} + 1,
                total_atendidos = base.total_atendidos + 1
        """, (data_atendimento.isoformat(), nome_mes(data_atendimento),
              nome_dia(data_atendimento), medico, especialidade, cod_medico,
              1 if categoria == "assistido" else 0,
              1 if categoria == "discente" else 0,
              1 if categoria == "servidor" else 0,
              meta))

        conn.commit()
    finally:
        conn.close()
    _limpar_cache()


def registrar_dia(data_ref: date, medico: str, turno: str, motivo: str):
    """
    Registra um dia/turno só com médico + situação, sem dados de paciente —
    para marcar rapidamente a presença do profissional nesse turno.
    motivo: 'Presença' | 'Falta' | 'Feriado'
    Aparece na revisão do dia (com nome em branco) e o status pode ser
    trocado depois, igual a qualquer outro lançamento.
    Não soma em nenhuma categoria de atendimento (Servidor/Discente/etc) —
    só marca a situação do profissional, e alimenta o código de falta
    profissional (0/1/2) usado nos gráficos do Dashboard.
    """
    med = buscar_medico(medico)
    especialidade = med["especialidade"] if med else ""
    cod_medico = med["cod"] if med else ""
    status = "Realizado" if motivo == "Presença" else "Falta do profissional"
    codigo_falta = {"Presença": 0, "Falta": 1, "Feriado": 2}[motivo]

    conn = get_conn()
    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO ficha (data, mes, dia_semana, turno, medico, especialidade,
                                assistido, servidor, status, motivo, criado_em)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (data_ref.isoformat(), nome_mes(data_ref), nome_dia(data_ref), turno,
              medico, especialidade, "Não", "Não", status, motivo,
              datetime.now().isoformat(timespec="seconds")))

        meta = med["meta"] if med else None
        incremento_faltosos = 0 if motivo == "Presença" else 1

        cur.execute("""
            INSERT INTO base (data, mes, dia_semana, medico, especialidade, cod_medico,
                               faltosos, falta_profissional, meta)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT (data, medico) DO UPDATE SET
                faltosos = base.faltosos + ?,
                falta_profissional = ?
        """, (data_ref.isoformat(), nome_mes(data_ref), nome_dia(data_ref),
              medico, especialidade, cod_medico, incremento_faltosos,
              codigo_falta, meta,
              incremento_faltosos, codigo_falta))

        conn.commit()
    finally:
        conn.close()
    _limpar_cache()


STATUS_OPCOES = ["Realizado", "Falta do profissional", "Falta do usuário"]


@st.cache_data(ttl=30)
def get_atendimentos_do_dia(data_ref: date, medico: str | None = None):
    """Lista os atendimentos lançados numa data (opcionalmente filtrando por
    médico), para revisão/marcação de status — equivalente a olhar a aba
    Ficha filtrada pelo dia. Não traz os registros importados em lote de
    planilhas de agenda (esses vêm sem turno e já chegam com o status
    resolvido — não fazem parte da revisão do dia a dia; para achar/excluir
    um deles, use a busca)."""
    conn = get_conn()
    try:
        q = "SELECT * FROM ficha WHERE data = ? AND turno IS NOT NULL AND turno != ''"
        params = [data_ref.isoformat()]
        if medico:
            q += " AND medico = ?"
            params.append(medico)
        q += " ORDER BY turno, nome_usuario"
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()
    return rows


@st.cache_data(ttl=30)
def buscar_atendimentos(medico: str | None = None, data_inicio: date | None = None,
                         data_fim: date | None = None, nome_paciente: str | None = None):
    """
    Busca flexível na Ficha: por médico num intervalo de dias, e/ou por
    nome (ou parte do nome) do paciente — pode combinar os filtros ou usar
    só um deles.
    """
    conn = get_conn()
    try:
        condicoes = []
        params = []

        if medico:
            condicoes.append("medico = ?")
            params.append(medico)
        if data_inicio:
            condicoes.append("data >= ?")
            params.append(data_inicio.isoformat())
        if data_fim:
            condicoes.append("data <= ?")
            params.append(data_fim.isoformat())
        if nome_paciente:
            condicoes.append("nome_usuario ILIKE ?")
            params.append(f"%{nome_paciente}%")

        q = "SELECT * FROM ficha"
        if condicoes:
            q += " WHERE " + " AND ".join(condicoes)
        q += " ORDER BY data DESC, turno, nome_usuario"

        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()
    return rows


def _campo_categoria(row):
    if row["servidor"] == "Sim":
        return "atendidos_servidores"
    elif row["assistido"] == "Sim":
        return "discentes_assistidos"
    else:
        return "discentes_naoassistidos"


def atualizar_status_atendimento(ficha_id: int, novo_status: str):
    """
    Marca um atendimento já lançado como Realizado / Falta do profissional /
    Falta do usuário, e ajusta os totais agregados da tabela 'base' de
    acordo — assim o Dashboard e o Mapa continuam corretos.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        row = cur.execute("SELECT * FROM ficha WHERE id = ?", (ficha_id,)).fetchone()
        if row is None:
            return False
        row = dict(row)
        status_antigo = row["status"] or "Realizado"

        if status_antigo == novo_status:
            return True

        cur.execute("UPDATE ficha SET status = ? WHERE id = ?", (novo_status, ficha_id))

        base_row = cur.execute(
            "SELECT * FROM base WHERE data = ? AND medico = ?",
            (row["data"], row["medico"])
        ).fetchone()

        if base_row is not None:
            sem_paciente = not row.get("nome_usuario")
            era_realizado = status_antigo == "Realizado"
            fica_realizado = novo_status == "Realizado"

            if sem_paciente:
                # Marcador de presença/falta (sem dados de paciente) — só mexe
                # em 'faltosos', nunca em total_atendidos nem nas categorias.
                if era_realizado and not fica_realizado:
                    cur.execute("UPDATE base SET faltosos = faltosos + 1 WHERE id = ?", (base_row["id"],))
                elif not era_realizado and fica_realizado:
                    cur.execute("UPDATE base SET faltosos = GREATEST(faltosos - 1, 0) WHERE id = ?",
                                (base_row["id"],))
            else:
                campo = _campo_categoria(row)
                if era_realizado and not fica_realizado:
                    cur.execute(f"""
                        UPDATE base SET {campo} = GREATEST({campo} - 1, 0),
                                         total_atendidos = GREATEST(total_atendidos - 1, 0),
                                         faltosos = faltosos + 1
                        WHERE id = ?
                    """, (base_row["id"],))
                elif not era_realizado and fica_realizado:
                    cur.execute(f"""
                        UPDATE base SET {campo} = {campo} + 1,
                                         total_atendidos = total_atendidos + 1,
                                         faltosos = GREATEST(faltosos - 1, 0)
                        WHERE id = ?
                    """, (base_row["id"],))
            # se trocou entre dois motivos de falta diferentes, os totais não mudam

        conn.commit()
    finally:
        conn.close()
    _limpar_cache()
    return True


@st.cache_data(ttl=30)
def contar_nao_realizados(medico: str, data_ref: date, turno: str | None = None):
    """Quantos atendimentos desse dia/médico(/turno) NÃO foram realizados."""
    conn = get_conn()
    try:
        q = "SELECT COUNT(*) FROM ficha WHERE medico = ? AND data = ? AND status != 'Realizado'"
        params = [medico, data_ref.isoformat()]
        if turno:
            q += " AND turno = ?"
            params.append(turno)
        n = conn.execute(q, params).fetchone()[0]
    finally:
        conn.close()
    return n


def excluir_atendimento(ficha_id: int):
    """
    Exclui definitivamente um lançamento (por engano, duplicado, etc.) e
    ajusta os totais agregados da tabela 'base' de acordo, para não deixar
    contagem "fantasma" nos totais/Dashboard.
    Retorna True se excluiu, False se o registro não foi encontrado.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        row = cur.execute("SELECT * FROM ficha WHERE id = ?", (ficha_id,)).fetchone()
        if row is None:
            return False
        row = dict(row)

        base_row = cur.execute(
            "SELECT * FROM base WHERE data = ? AND medico = ?",
            (row["data"], row["medico"])
        ).fetchone()

        if base_row is not None:
            if row["status"] == "Realizado":
                if row.get("nome_usuario"):
                    campo = _campo_categoria(row)
                    cur.execute(f"""
                        UPDATE base SET {campo} = GREATEST({campo} - 1, 0),
                                         total_atendidos = GREATEST(total_atendidos - 1, 0)
                        WHERE id = ?
                    """, (base_row["id"],))
                # marcador de presença sem paciente: nada a decrementar aqui
            else:
                cur.execute("UPDATE base SET faltosos = GREATEST(faltosos - 1, 0) WHERE id = ?",
                            (base_row["id"],))

        cur.execute("DELETE FROM ficha WHERE id = ?", (ficha_id,))
        conn.commit()
    finally:
        conn.close()
    _limpar_cache()
    return True


def forcar_reseed_base():
    """Recarrega o histórico manualmente, só se a tabela 'base' estiver vazia
    (evita duplicar registros se já tiver dados). Usado pelo botão de
    diagnóstico. Retorna o número de registros inseridos (0 se nada mudou)."""
    if not BASE_HISTORICO_SEED.exists():
        return 0
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM base")
        if cur.fetchone()[0] > 0:
            return 0
        registros = json.loads(BASE_HISTORICO_SEED.read_text(encoding="utf-8"))
        cur.execute_values("""
            INSERT INTO base
                (data, mes, dia_semana, medico, especialidade, cod_medico,
                 discentes_assistidos, discentes_naoassistidos, atendidos_servidores,
                 faltosos, falta_profissional, agendados, total_atendidos, meta,
                 absenteismo, ocupacao, classif_absenteismo, classif_ocupacao, classif_desempenho)
            VALUES %s
            ON CONFLICT (data, medico) DO NOTHING
        """, [
            (r["data"], r["mes"], r["dia_semana"], r["medico"], r["especialidade"], r["cod_medico"],
             r["discentes_assistidos"], r["discentes_naoassistidos"], r["atendidos_servidores"],
             r["faltosos"], r["falta_profissional"], r["agendados"], r["total_atendidos"], r["meta"],
             r["absenteismo"], r["ocupacao"], r["classif_absenteismo"], r["classif_ocupacao"],
             r["classif_desempenho"])
            for r in registros
        ])
        conn.commit()
        n = len(registros)
    finally:
        conn.close()
    _limpar_cache()
    return n


@st.cache_data(ttl=30)
def get_ficha_df():
    import pandas as pd
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ficha ORDER BY data, id")
        colunas = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=colunas)
    finally:
        conn.rollback()
        pool.putconn(conn)
    return df


@st.cache_data(ttl=30)
def get_base_df():
    import pandas as pd
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM base ORDER BY data")
        colunas = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=colunas)
    finally:
        conn.rollback()
        pool.putconn(conn)
    return df


@st.cache_data(ttl=30)
def get_config(chave, default=""):
    conn = get_conn()
    try:
        row = conn.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    finally:
        conn.close()
    return row["valor"] if row else default


def set_config(chave, valor):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO config (chave, valor) VALUES (?, ?) "
                     "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (chave, valor))
        conn.commit()
    finally:
        conn.close()
    _limpar_cache()


TABELAS_BACKUP = ["medicos", "base", "ficha", "config"]


def gerar_backup_json():
    """
    Monta um backup completo do banco (médicos, base, ficha, config — inclui
    as senhas) em formato JSON, pronto para download. Não grava nada em
    disco — é para o usuário baixar e guardar em local seguro (Google Drive,
    e-mail, etc.), já que o disco do Streamlit Cloud é temporário.
    """
    conn = get_conn()
    try:
        dump = {
            "versao": 1,
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "tabelas": {},
        }
        for tabela in TABELAS_BACKUP:
            rows = conn.execute(f"SELECT * FROM {tabela}").fetchall()
            dump["tabelas"][tabela] = [dict(r) for r in rows]
    finally:
        conn.close()
    return json.dumps(dump, ensure_ascii=False, indent=1).encode("utf-8")


def restaurar_backup_json(conteudo: bytes):
    """
    Restaura um backup gerado por gerar_backup_json(). Substitui TODO o
    conteúdo atual das tabelas pelo do backup (operação destrutiva —
    a tela que chama isso deve pedir confirmação antes).
    Retorna um resumo {tabela: quantidade_restaurada}.
    """
    dump = json.loads(conteudo.decode("utf-8"))
    if "tabelas" not in dump:
        raise ValueError("Arquivo de backup inválido — não parece ter sido gerado por este sistema.")

    resumo = {}
    conn = get_conn()
    cur = conn.cursor()
    try:
        for tabela in TABELAS_BACKUP:
            registros = dump["tabelas"].get(tabela, [])
            cur.execute(f"DELETE FROM {tabela}")
            if registros:
                colunas = list(registros[0].keys())
                colunas_sql = ",".join(colunas)
                cur.execute_values(
                    f"INSERT INTO {tabela} ({colunas_sql}) VALUES %s",
                    [tuple(r.get(c) for c in colunas) for r in registros]
                )
            resumo[tabela] = len(registros)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    _limpar_cache()
    return resumo


@st.cache_data(ttl=30)
def get_mapa_atendimento(medico: str, data_sel: date, turno: str | None):
    """Retorna a lista de atendimentos REALIZADOS de um médico numa data (e
    turno opcional) — equivalente à macro GerarMapaPDF, já excluindo faltas.
    Marcadores de presença sem paciente (feitos por registrar_dia) não
    entram aqui, pois não representam um atendimento de fato."""
    conn = get_conn()
    try:
        q = ("SELECT * FROM ficha WHERE medico = ? AND data = ? AND status = 'Realizado' "
             "AND nome_usuario IS NOT NULL AND nome_usuario != ''")
        params = [medico, data_sel.isoformat()]
        if turno:
            q += " AND turno = ?"
            params.append(turno)
        q += " ORDER BY id"
        rows = conn.execute(q, params).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
