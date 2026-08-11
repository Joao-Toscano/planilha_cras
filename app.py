import streamlit as st
from datetime import date
import pandas as pd

import db
from pdf_mapa import gerar_pdf_mapa

st.set_page_config(page_title="CRAS - Sistema de Atendimento", page_icon="🏥", layout="wide")
resultado_init = db.init_db()
if resultado_init["erros"]:
    with st.sidebar:
        st.error("⚠️ Problemas ao carregar os dados — veja 'Base de Dados > Diagnóstico'.")
elif resultado_init["info"]:
    with st.sidebar:
        st.info("ℹ️ Alguns dados foram completados automaticamente — veja 'Base de Dados > Diagnóstico'.")

st.sidebar.title("🏥 CRAS")
pagina = st.sidebar.radio(
    "Navegação",
    ["📝 Lançamento Diário", "🖨️ Mapa de Atendimento", "📊 Dashboard", "📁 Base de Dados"],
)

# =====================================================================
# PÁGINA 1 — Lançamento Diário (equivalente à aba "Início")
# =====================================================================
if pagina == "📝 Lançamento Diário":
    st.title("Lançamento Diário")
    st.caption("Preencha os dados do atendimento e clique em Salvar.")

    medicos = db.listar_medicos()
    nomes_medicos = [m["nome"] for m in medicos]

    with st.form("form_lancamento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nr_cras = st.text_input("Nº CRAS")
            data_atendimento = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            turno = st.selectbox("Turno", ["MANHÃ", "TARDE"])
            usuario = st.text_input("Nome do usuário")
        with col2:
            nr_matricula = st.text_input("Nº Matrícula/SIAPE")
            medico = st.selectbox("Nome do médico", nomes_medicos, index=None,
                                   placeholder="Selecione o médico")
            categoria = st.radio(
                "Categoria do atendimento",
                ["Discente (não assistido)", "Discente assistido (Prape)", "Servidor"],
                horizontal=False,
            )

        enviado = st.form_submit_button("💾 Salvar na Base", use_container_width=True)

    if enviado:
        if not data_atendimento:
            st.error("Preencha a DATA antes de salvar.")
        elif not medico:
            st.error("Selecione o NOME DO MÉDICO antes de salvar.")
        else:
            categoria_key = {
                "Discente (não assistido)": "discente",
                "Discente assistido (Prape)": "assistido",
                "Servidor": "servidor",
            }[categoria]
            db.salvar_atendimento(nr_cras, data_atendimento, medico, turno, usuario,
                                   nr_matricula, categoria_key)
            st.success("Registro salvo com sucesso!")

    st.divider()
    st.caption(f"Última atualização: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}")

    # -----------------------------------------------------------------
    # Registrar falta do profissional (sem nenhum atendimento no dia)
    # -----------------------------------------------------------------
    with st.expander("🚫 Registrar falta do profissional (dia sem nenhum atendimento)"):
        st.caption("Use aqui quando o profissional não compareceu — sem preencher um "
                   "atendimento por paciente.")
        with st.form("form_falta", clear_on_submit=True):
            colf1, colf2, colf3 = st.columns(3)
            with colf1:
                medico_falta = st.selectbox("Médico", nomes_medicos, index=None,
                                             placeholder="Selecione o médico", key="medico_falta")
            with colf2:
                data_falta = st.date_input("Data", value=date.today(), format="DD/MM/YYYY", key="data_falta")
            with colf3:
                turno_falta = st.selectbox("Turno", ["MANHÃ", "TARDE"], key="turno_falta")
            motivo_falta = st.radio("Motivo", ["Ausência", "Férias/Feriado"], horizontal=True)
            enviar_falta = st.form_submit_button("Registrar falta")

        if enviar_falta:
            if not medico_falta:
                st.error("Selecione o médico.")
            else:
                db.registrar_falta_profissional(medico_falta, data_falta, turno_falta, motivo_falta)
                st.success(f"Falta registrada: {medico_falta} — {data_falta.strftime('%d/%m/%Y')} ({motivo_falta}).")

    # -----------------------------------------------------------------
    # Verificação: houve ou não atendimento nesse dia/médico?
    # -----------------------------------------------------------------
    with st.expander("🔍 Verificar se houve atendimento num dia"):
        colv1, colv2, colv3 = st.columns(3)
        with colv1:
            medico_verif = st.selectbox("Médico", nomes_medicos, index=None,
                                         placeholder="Selecione o médico", key="medico_verif")
        with colv2:
            data_verif = st.date_input("Data", value=date.today(), format="DD/MM/YYYY", key="data_verif")
        with colv3:
            turno_verif = st.selectbox("Turno", ["Ambos", "MANHÃ", "TARDE"], key="turno_verif")

        if medico_verif:
            turno_filtro = None if turno_verif == "Ambos" else turno_verif
            resultado = db.get_verificacao_atendimento(medico_verif, data_verif, turno_filtro)

            if resultado["status"] == "sem_registro":
                st.warning("Nenhum registro encontrado — não foi lançado atendimento nem falta "
                          "para esse dia/médico/turno.")
            elif resultado["status"] == "faltou":
                motivos = ", ".join(sorted({f["falta_profissional"] for f in resultado["faltas"]}))
                st.error(f"❌ Não houve atendimento — profissional ausente ({motivos}).")
            else:
                st.success(f"✅ Houve atendimento — {len(resultado['atendimentos'])} paciente(s) "
                          f"atendido(s) nesse dia/turno.")
                df_v = pd.DataFrame(resultado["atendimentos"])[["nome_usuario", "matricula", "turno"]]
                df_v.columns = ["Nome do usuário", "Matrícula", "Turno"]
                st.dataframe(df_v, use_container_width=True, hide_index=True)

# =====================================================================
# PÁGINA 2 — Mapa de Atendimento (equivalente à aba "Mapa Impressao")
# =====================================================================
elif pagina == "🖨️ Mapa de Atendimento":
    st.title("Mapa de Atendimento Diário")

    medicos = db.listar_medicos()
    nomes_medicos = [m["nome"] for m in medicos]

    col1, col2, col3 = st.columns(3)
    with col1:
        medico_sel = st.selectbox("Médico", nomes_medicos, index=None,
                                   placeholder="Selecione o médico")
    with col2:
        data_sel = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
    with col3:
        turno_sel = st.selectbox("Turno", ["Ambos", "MANHÃ", "TARDE"])

    if st.button("🔎 Gerar Mapa"):
        if not medico_sel:
            st.error("Informe o médico.")
        else:
            turno_filtro = None if turno_sel == "Ambos" else turno_sel
            atendimentos = db.get_mapa_atendimento(medico_sel, data_sel, turno_filtro)
            st.session_state["mapa_atendimentos"] = atendimentos
            st.session_state["mapa_medico"] = medico_sel
            st.session_state["mapa_data"] = data_sel
            st.session_state["mapa_turno"] = turno_sel

    if "mapa_atendimentos" in st.session_state:
        atendimentos = st.session_state["mapa_atendimentos"]
        medico_sel = st.session_state["mapa_medico"]
        data_sel = st.session_state["mapa_data"]
        turno_sel = st.session_state["mapa_turno"]

        med = db.buscar_medico(medico_sel)
        especialidade = med["especialidade"] if med else ""

        st.subheader(f"{medico_sel} — {especialidade}")
        st.write(f"**Data:** {data_sel.strftime('%d/%m/%Y')} · **Turno:** {turno_sel}")

        faltas = [a for a in atendimentos if a.get("falta_profissional") != "Presença"]
        atendimentos_reais = [a for a in atendimentos if a.get("falta_profissional") == "Presença"]

        if faltas and not atendimentos_reais:
            motivos = ", ".join(sorted({f["falta_profissional"] for f in faltas}))
            st.error(f"❌ Profissional ausente nesse dia/turno ({motivos}) — nenhum atendimento realizado.")
        elif not atendimentos and not faltas:
            st.warning("Nenhum registro encontrado — sem atendimento nem falta lançados para esse filtro.")

        if atendimentos_reais:
            df = pd.DataFrame(atendimentos_reais)[
                ["nr_cras", "nome_usuario", "matricula", "assistido", "servidor"]
            ]
            df.columns = ["Nº CRAS", "Nome do usuário", "Matrícula", "Assistido", "Servidor"]
            st.dataframe(df, use_container_width=True, hide_index=True)

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total atendidos", len(atendimentos_reais))
        servidores = sum(1 for a in atendimentos_reais if a["servidor"] == "Sim")
        assistidos = sum(1 for a in atendimentos_reais if a["assistido"] == "Sim" and a["servidor"] != "Sim")
        col_b.metric("Servidores", servidores)
        col_c.metric("Discentes assistidos", assistidos)

        pdf_buffer = gerar_pdf_mapa(medico_sel, especialidade, data_sel, turno_sel, atendimentos)
        st.download_button(
            "🖨️ Baixar Mapa em PDF", data=pdf_buffer,
            file_name=f"Mapa_{medico_sel}_{data_sel.strftime('%d-%m-%Y')}.pdf",
            mime="application/pdf",
        )

# =====================================================================
# PÁGINA 3 — Dashboard
# =====================================================================
elif pagina == "📊 Dashboard":
    st.title("Dashboard")
    st.caption("Inclui o histórico real importado da planilha original (Base 2025 - 2026), "
               "mais os lançamentos feitos aqui no app.")

    base_df = db.get_base_df()

    if base_df.empty:
        st.info("Ainda não há atendimentos registrados. Use a página de Lançamento Diário.")
    else:
        base_df["data"] = pd.to_datetime(base_df["data"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Dias com atendimento", base_df["data"].nunique())
        col2.metric("Total de atendimentos", int(base_df["total_atendidos"].sum()))
        col3.metric("Servidores atendidos", int(base_df["atendidos_servidores"].sum()))
        col4.metric("Discentes assistidos", int(base_df["discentes_assistidos"].sum()))

        st.divider()

        anos = sorted(base_df["data"].dt.year.unique(), reverse=True)
        ano_sel = st.selectbox("Filtrar por ano", ["Todos"] + [str(a) for a in anos])
        df_filtrado = base_df if ano_sel == "Todos" else base_df[base_df["data"].dt.year == int(ano_sel)]

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Atendimentos por especialidade")
            por_esp = df_filtrado.groupby("especialidade")["total_atendidos"].sum().sort_values(ascending=False)
            st.bar_chart(por_esp)
        with c2:
            st.subheader("Atendimentos por médico")
            por_medico = df_filtrado.groupby("medico")["total_atendidos"].sum().sort_values(ascending=False)
            st.bar_chart(por_medico)

        st.subheader("Atendimentos por mês")
        df_filtrado = df_filtrado.copy()
        df_filtrado["ano_mes"] = df_filtrado["data"].dt.to_period("M").astype(str)
        por_mes = df_filtrado.groupby("ano_mes")["total_atendidos"].sum()
        st.line_chart(por_mes)

        with st.expander("Ver tabela completa do histórico"):
            st.dataframe(df_filtrado.sort_values("data", ascending=False),
                         use_container_width=True, hide_index=True)

# =====================================================================
# PÁGINA 4 — Base de Dados (equivalente às abas "Ficha" e "Base")
# =====================================================================
elif pagina == "📁 Base de Dados":
    st.title("Base de Dados")

    aba = st.tabs(["Ficha (todos os atendimentos)", "Base (resumo por dia/médico)",
                   "Médicos cadastrados", "🔧 Diagnóstico"])

    with aba[0]:
        df = db.get_ficha_df()
        st.dataframe(df, use_container_width=True, hide_index=True)
        if not df.empty:
            st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode("utf-8"),
                                "ficha.csv", "text/csv")

    with aba[1]:
        df = db.get_base_df()
        st.dataframe(df, use_container_width=True, hide_index=True)
        if not df.empty:
            st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode("utf-8"),
                                "base.csv", "text/csv")

    with aba[2]:
        st.subheader("➕ Adicionar novo médico")
        with st.form("form_novo_medico", clear_on_submit=True):
            colm1, colm2 = st.columns(2)
            with colm1:
                novo_nome = st.text_input("Nome completo")
                nova_especialidade = st.text_input("Especialidade")
            with colm2:
                novo_cod = st.text_input("Código (opcional, ex: A, B, C...)")
                nova_meta = st.number_input("Meta de atendimento diária (opcional)",
                                             min_value=0, step=1, value=0)
            enviar_medico = st.form_submit_button("Adicionar médico")

        if enviar_medico:
            meta_final = nova_meta if nova_meta > 0 else None
            ok, erro = db.adicionar_medico(novo_nome, nova_especialidade, novo_cod, meta_final)
            if ok:
                st.success(f"Médico '{novo_nome.strip()}' adicionado com sucesso!")
                st.rerun()
            else:
                st.error(erro)

        st.divider()
        st.subheader("Médicos cadastrados")
        df_medicos = pd.DataFrame(db.listar_medicos())
        st.dataframe(df_medicos, use_container_width=True, hide_index=True)

        with st.expander("🗑️ Remover um médico da lista"):
            st.caption("Isso só tira o nome das opções do formulário — atendimentos já "
                       "lançados em nome desse médico continuam salvos normalmente.")
            nomes_remover = [m["nome"] for m in db.listar_medicos()]
            medico_remover = st.selectbox("Médico a remover", nomes_remover, index=None,
                                           placeholder="Selecione", key="medico_remover")
            if st.button("Remover", type="secondary") and medico_remover:
                db.remover_medico(medico_remover)
                st.success(f"'{medico_remover}' removido da lista.")
                st.rerun()

    with aba[3]:
        st.caption("Use esta aba se os gráficos ou a lista de médicos aparecerem vazios.")
        if resultado_init["erros"]:
            for e in resultado_init["erros"]:
                st.error(e)
        if resultado_init["info"]:
            for i in resultado_init["info"]:
                st.info(i)
        if not resultado_init["erros"] and not resultado_init["info"]:
            st.success("Nenhum problema encontrado na inicialização.")

        st.write("**Caminhos verificados:**")
        st.code(
            f"Banco de dados:     {db.DB_PATH}  (existe: {db.DB_PATH.exists()})\n"
            f"Seed de médicos:    {db.MEDICOS_SEED}  (existe: {db.MEDICOS_SEED.exists()})\n"
            f"Seed do histórico:  {db.BASE_HISTORICO_SEED}  (existe: {db.BASE_HISTORICO_SEED.exists()})",
            language="text"
        )

        base_df = db.get_base_df()
        medicos_df = pd.DataFrame(db.listar_medicos())
        st.write("**Linhas atualmente no banco:**")
        st.write(f"- Tabela `base` (histórico + lançamentos): **{len(base_df)}** linhas")
        st.write(f"- Tabela `medicos`: **{len(medicos_df)}** linhas")

        if st.button("🔄 Forçar recarregar o histórico (se a tabela 'base' estiver vazia)"):
            recarregados = db.forcar_reseed_base()
            if recarregados:
                st.success(f"{recarregados} registros recarregados do histórico. Atualize a página.")
            else:
                st.warning("A tabela 'base' já tem dados (ou o arquivo de histórico não foi "
                           "encontrado) — nada foi alterado, para não duplicar registros.")
