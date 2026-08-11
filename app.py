import streamlit as st
from datetime import date
import pandas as pd

import db
from pdf_mapa import gerar_pdf_mapa

st.set_page_config(page_title="CRAS - Sistema de Atendimento", page_icon="🏥", layout="wide")
db.init_db()

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

        if atendimentos:
            df = pd.DataFrame(atendimentos)[
                ["nr_cras", "nome_usuario", "matricula", "falta_profissional",
                 "assistido", "servidor"]
            ]
            df.columns = ["Nº CRAS", "Nome do usuário", "Matrícula", "Falta profissional",
                           "Assistido", "Servidor"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum atendimento encontrado para esse filtro.")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total atendidos", len(atendimentos))
        servidores = sum(1 for a in atendimentos if a["servidor"] == "Sim")
        assistidos = sum(1 for a in atendimentos if a["assistido"] == "Sim" and a["servidor"] != "Sim")
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

    aba = st.tabs(["Ficha (todos os atendimentos)", "Base (resumo por dia/médico)", "Médicos cadastrados"])

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
        df = pd.DataFrame(db.listar_medicos())
        st.dataframe(df, use_container_width=True, hide_index=True)
