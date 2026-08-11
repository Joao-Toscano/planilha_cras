"""
Camada de dados do app CRAS.
Usa SQLite (arquivo local cras.db) como substituto das abas
"Ficha" e "Base" / "Base 2025 - 2026" da planilha original.
"""
import sqlite3
import json
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(__file__).parent / "cras.db"
MEDICOS_SEED = Path(__file__).parent / "medicos.json"
BASE_HISTORICO_SEED = Path(__file__).parent / "base_historico.json"

NOMES_MES = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
NOMES_DIA = ["Segunda-feira", "Terca-feira", "Quarta-feira", "Quinta-feira",
             "Sexta-feira", "Sabado", "Domingo"]  # Python weekday(): 0=segunda


def nome_mes(d: date) -> str:
    return NOMES_MES[d.month - 1]


def nome_dia(d: date) -> str:
    return NOMES_DIA[d.weekday()]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    avisos = []
    erros = []

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medicos (
            id INTEGER PRIMARY KEY,
            nome TEXT UNIQUE NOT NULL,
            especialidade TEXT,
            cod TEXT,
            meta INTEGER
        )
    """)

    # Ficha: um registro por atendimento (equivalente à aba "Ficha")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ficha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            realizado TEXT,
            consulta TEXT,
            falta_profissional TEXT,
            criado_em TEXT
        )
    """)

    # Base: um registro por (data, médico) - equivalente às abas "Base" / "Base 2025 - 2026"
    cur.execute("""
        CREATE TABLE IF NOT EXISTS base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    colunas_existentes = {row[1] for row in cur.execute("PRAGMA table_info(base)")}
    for col, tipo in colunas_esperadas.items():
        if col not in colunas_existentes:
            cur.execute(f"ALTER TABLE base ADD COLUMN {col} {tipo}")
            avisos.append(f"Coluna '{col}' estava faltando na tabela 'base' (banco de uma versão "
                           f"anterior) — adicionada automaticamente.")
    conn.commit()

    # Sincroniza médicos: roda sempre (não só na primeira vez), usando
    # INSERT OR IGNORE, para preencher automaticamente qualquer médico que
    # esteja faltando — inclusive se o banco já existia de uma versão
    # anterior com uma lista incompleta. Não duplica quem já existe.
    if MEDICOS_SEED.exists():
        medicos = json.loads(MEDICOS_SEED.read_text(encoding="utf-8"))
        antes = cur.execute("SELECT COUNT(*) FROM medicos").fetchone()[0]
        cur.executemany(
            "INSERT OR IGNORE INTO medicos (id, nome, especialidade, cod, meta) VALUES (?,?,?,?,?)",
            [(m["id"], m["nome"], m["especialidade"], m["cod"], m["meta"]) for m in medicos]
        )
        conn.commit()
        depois = cur.execute("SELECT COUNT(*) FROM medicos").fetchone()[0]
        if depois > antes:
            avisos.append(f"{depois - antes} médico(s) que estavam faltando no banco foram "
                           f"adicionados automaticamente (total agora: {depois}).")
    else:
        erros.append(f"Arquivo de médicos não encontrado em: {MEDICOS_SEED}")

    # Sincroniza o histórico da mesma forma: roda sempre, usando INSERT OR
    # IGNORE (a restrição UNIQUE(data, medico) evita duplicar registros já
    # existentes) — preenche automaticamente qualquer linha do histórico que
    # ainda esteja faltando.
    if BASE_HISTORICO_SEED.exists():
        registros = json.loads(BASE_HISTORICO_SEED.read_text(encoding="utf-8"))
        antes = cur.execute("SELECT COUNT(*) FROM base").fetchone()[0]
        cur.executemany("""
            INSERT OR IGNORE INTO base
                (data, mes, dia_semana, medico, especialidade, cod_medico,
                 discentes_assistidos, discentes_naoassistidos, atendidos_servidores,
                 faltosos, falta_profissional, agendados, total_atendidos, meta,
                 absenteismo, ocupacao, classif_absenteismo, classif_ocupacao, classif_desempenho)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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

    conn.close()
    return {"info": avisos, "erros": erros}


def listar_medicos():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM medicos ORDER BY nome").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_medico(nome: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM medicos WHERE nome = ?", (nome,)).fetchone()
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
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO medicos (nome, especialidade, cod, meta) VALUES (?,?,?,?)",
            (nome, (especialidade or "").strip(), (cod or "").strip(), meta)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        return False, f"Não foi possível salvar: {e}"
    conn.close()
    return True, None


def remover_medico(nome: str):
    """Remove um médico da lista de cadastro (não apaga atendimentos já
    lançados em seu nome, apenas tira das opções do formulário)."""
    conn = get_conn()
    conn.execute("DELETE FROM medicos WHERE nome = ?", (nome,))
    conn.commit()
    conn.close()


def salvar_atendimento(nr_cras, data_atendimento: date, medico, turno, usuario,
                        nr_matricula, categoria):
    """
    categoria: 'servidor' | 'assistido' | 'discente'
    Equivale à macro SalvarNaBase do arquivo original.
    Cada atendimento lançado aqui é, por definição, uma presença do
    profissional (falta_profissional = 'Presença') — para registrar um dia
    em que o profissional faltou, sem nenhum paciente atendido, use
    registrar_falta_profissional().
    """
    med = buscar_medico(medico)
    especialidade = med["especialidade"] if med else ""
    cod_medico = med["cod"] if med else ""

    assistido = "Sim" if categoria == "assistido" else "Não"
    servidor = "Sim" if categoria == "servidor" else "Não"

    conn = get_conn()
    cur = conn.cursor()

    # Ordem: quantos atendimentos esse usuário já teve (equivalente à fórmula COUNTIFS da coluna F)
    ordem = cur.execute(
        "SELECT COUNT(*) FROM ficha WHERE nome_usuario = ?", (usuario,)
    ).fetchone()[0] + 1

    cur.execute("""
        INSERT INTO ficha (nr_cras, data, mes, dia_semana, turno, ordem, medico,
                            especialidade, matricula, nome_usuario, assistido, servidor,
                            falta_profissional, criado_em)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (nr_cras, data_atendimento.isoformat(), nome_mes(data_atendimento),
          nome_dia(data_atendimento), turno, ordem, medico, especialidade,
          nr_matricula, usuario, assistido, servidor, "Presença",
          datetime.now().isoformat(timespec="seconds")))

    # Base: um registro agregado por (data, médico). Diferente do VBA original
    # (que só criava a linha e não voltava a atualizá-la), aqui a linha é
    # criada na primeira vez e os contadores são incrementados nos lançamentos
    # seguintes do mesmo dia/médico — assim o resumo diário fica sempre correto.
    meta = med["meta"] if med else None
    existente = cur.execute(
        "SELECT id FROM base WHERE data = ? AND medico = ?",
        (data_atendimento.isoformat(), medico)
    ).fetchone()

    if existente is None:
        cur.execute("""
            INSERT INTO base (data, mes, dia_semana, medico, especialidade, cod_medico,
                               discentes_assistidos, discentes_naoassistidos, atendidos_servidores,
                               total_atendidos, meta)
            VALUES (?,?,?,?,?,?,?,?,?,1,?)
        """, (data_atendimento.isoformat(), nome_mes(data_atendimento),
              nome_dia(data_atendimento), medico, especialidade, cod_medico,
              1 if categoria == "assistido" else 0,
              1 if categoria == "discente" else 0,
              1 if categoria == "servidor" else 0,
              meta))
    else:
        campo = {"assistido": "discentes_assistidos",
                 "discente": "discentes_naoassistidos",
                 "servidor": "atendidos_servidores"}[categoria]
        cur.execute(f"""
            UPDATE base SET {campo} = {campo} + 1, total_atendidos = total_atendidos + 1
            WHERE id = ?
        """, (existente["id"],))

    conn.commit()
    conn.close()


def registrar_falta_profissional(medico, data_ref: date, turno, motivo):
    """
    Registra que o profissional NÃO compareceu num dia/turno (sem nenhum
    atendimento de paciente) — equivalente a marcar 'Falta profissional' na
    aba Ficha do arquivo original.
    motivo: 'Ausência' ou 'Férias/Feriado'
    """
    med = buscar_medico(medico)
    especialidade = med["especialidade"] if med else ""
    cod_medico = med["cod"] if med else ""

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO ficha (data, mes, dia_semana, turno, medico, especialidade,
                            falta_profissional, criado_em)
        VALUES (?,?,?,?,?,?,?,?)
    """, (data_ref.isoformat(), nome_mes(data_ref), nome_dia(data_ref), turno,
          medico, especialidade, motivo,
          datetime.now().isoformat(timespec="seconds")))

    meta = med["meta"] if med else None
    existente = cur.execute(
        "SELECT id FROM base WHERE data = ? AND medico = ?",
        (data_ref.isoformat(), medico)
    ).fetchone()

    if existente is None:
        cur.execute("""
            INSERT INTO base (data, mes, dia_semana, medico, especialidade, cod_medico,
                               faltosos, meta)
            VALUES (?,?,?,?,?,?,1,?)
        """, (data_ref.isoformat(), nome_mes(data_ref), nome_dia(data_ref),
              medico, especialidade, cod_medico, meta))
    else:
        cur.execute("UPDATE base SET faltosos = faltosos + 1 WHERE id = ?", (existente["id"],))

    conn.commit()
    conn.close()


def get_verificacao_atendimento(medico: str, data_sel: date, turno: str | None = None):
    """
    Verifica se houve atendimento (ou falta do profissional) num dia/médico —
    equivalente a conferir a aba Ficha manualmente. Retorna um resumo pronto
    para exibir na tela.
    """
    conn = get_conn()
    q = "SELECT * FROM ficha WHERE medico = ? AND data = ?"
    params = [medico, data_sel.isoformat()]
    if turno:
        q += " AND turno = ?"
        params.append(turno)
    q += " ORDER BY id"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()

    if not rows:
        return {"status": "sem_registro", "atendimentos": [], "faltas": []}

    faltas = [r for r in rows if r["falta_profissional"] != "Presença"]
    atendimentos = [r for r in rows if r["falta_profissional"] == "Presença"]

    if faltas and not atendimentos:
        status = "faltou"
    elif atendimentos:
        status = "atendeu"
    else:
        status = "sem_registro"

    return {"status": status, "atendimentos": atendimentos, "faltas": faltas}


def forcar_reseed_base():
    """Recarrega o histórico manualmente, só se a tabela 'base' estiver vazia
    (evita duplicar registros se já tiver dados). Usado pelo botão de
    diagnóstico. Retorna o número de registros inseridos (0 se nada mudou)."""
    if not BASE_HISTORICO_SEED.exists():
        return 0
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM base")
    if cur.fetchone()[0] > 0:
        conn.close()
        return 0
    registros = json.loads(BASE_HISTORICO_SEED.read_text(encoding="utf-8"))
    cur.executemany("""
        INSERT OR IGNORE INTO base
            (data, mes, dia_semana, medico, especialidade, cod_medico,
             discentes_assistidos, discentes_naoassistidos, atendidos_servidores,
             faltosos, falta_profissional, agendados, total_atendidos, meta,
             absenteismo, ocupacao, classif_absenteismo, classif_ocupacao, classif_desempenho)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
    conn.close()
    return n


def get_ficha_df():
    import pandas as pd
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM ficha ORDER BY data, id", conn)
    conn.close()
    return df


def get_base_df():
    import pandas as pd
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM base ORDER BY data", conn)
    conn.close()
    return df


def get_mapa_atendimento(medico: str, data_sel: date, turno: str | None):
    """Retorna a lista de atendimentos de um médico numa data (e turno opcional),
    equivalente à macro GerarMapaPDF."""
    conn = get_conn()
    q = "SELECT * FROM ficha WHERE medico = ? AND data = ?"
    params = [medico, data_sel.isoformat()]
    if turno:
        q += " AND turno = ?"
        params.append(turno)
    q += " ORDER BY id"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
