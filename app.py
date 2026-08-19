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

    # -----------------------------------------------------------------
    # Atendimentos do dia — revisar e marcar status (Realizado / Falta)
    # -----------------------------------------------------------------
    st.subheader("📋 Atendimentos do dia")
    st.caption("Marque abaixo se cada atendimento aconteceu ou não, e o motivo — "
               "só os marcados como 'Realizado' entram no Mapa de Atendimento.")

    colr1, colr2 = st.columns(2)
    with colr1:
        data_revisao = st.date_input("Dia a revisar", value=date.today(),
                                      format="DD/MM/YYYY", key="data_revisao")
    with colr2:
        medico_revisao = st.selectbox("Filtrar por médico (opcional)", ["Todos"] + nomes_medicos,
                                       key="medico_revisao")

    registros = db.get_atendimentos_do_dia(
        data_revisao, None if medico_revisao == "Todos" else medico_revisao
    )

    if not registros:
        st.info("Nenhum atendimento lançado para esse dia.")
    else:
        df_rev = pd.DataFrame(registros).set_index("id")
        df_rev_exibir = df_rev[["medico", "turno", "nome_usuario", "matricula", "status"]].copy()
        df_rev_exibir.columns = ["Médico", "Turno", "Nome do usuário", "Matrícula", "Status"]

        editado = st.data_editor(
            df_rev_exibir,
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=db.STATUS_OPCOES, required=True
                ),
            },
            disabled=["Médico", "Turno", "Nome do usuário", "Matrícula"],
            use_container_width=True,
            key="editor_atendimentos_dia",
        )

        # Salva automaticamente qualquer mudança de status assim que ela
        # acontece (sem precisar de um botão separado) — compara o que veio
        # do editor com o que estava no banco nesse carregamento da página.
        mudancas = [
            (int(ficha_id), linha["Status"])
            for ficha_id, linha in editado.iterrows()
            if linha["Status"] != df_rev_exibir.loc[ficha_id, "Status"]
        ]
        if mudancas:
            for ficha_id, novo_status in mudancas:
                db.atualizar_status_atendimento(ficha_id, novo_status)
            st.toast(f"{len(mudancas)} atendimento(s) atualizado(s).", icon="✅")
            st.rerun()

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

    # Sempre busca na hora, direto do banco — sem guardar em cache entre
    # páginas, para nunca mostrar um resultado desatualizado depois de
    # alguém mudar um status na página de Lançamento Diário.
    if medico_sel:
        turno_filtro = None if turno_sel == "Ambos" else turno_sel
        atendimentos = db.get_mapa_atendimento(medico_sel, data_sel, turno_filtro)

        med = db.buscar_medico(medico_sel)
        especialidade = med["especialidade"] if med else ""

        st.subheader(f"{medico_sel} — {especialidade}")
        st.write(f"**Data:** {data_sel.strftime('%d/%m/%Y')} · **Turno:** {turno_sel}")

        n_faltas = db.contar_nao_realizados(medico_sel, data_sel, turno_filtro)

        if not atendimentos and n_faltas:
            st.error(f"❌ Nenhum atendimento realizado nesse dia/turno — {n_faltas} falta(s) registrada(s).")
        elif not atendimentos:
            st.warning("Nenhum registro encontrado para esse filtro. Lance atendimentos na página "
                      "'Lançamento Diário'.")
        else:
            df = pd.DataFrame(atendimentos)[
                ["nr_cras", "nome_usuario", "matricula", "assistido", "servidor"]
            ]
            df.columns = ["Nº CRAS", "Nome do usuário", "Matrícula", "Assistido", "Servidor"]
            st.dataframe(df, use_container_width=True, hide_index=True)
            if n_faltas:
                st.caption(f"ℹ️ {n_faltas} atendimento(s) desse dia/turno não entraram aqui por "
                          f"estarem marcados como falta — ajuste em 'Lançamento Diário'.")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total atendidos", len(atendimentos))
        servidores = sum(1 for a in atendimentos if a["servidor"] == "Sim")
        assistidos = sum(1 for a in atendimentos if a["assistido"] == "Sim" and a["servidor"] != "Sim")
        col_b.metric("Servidores", servidores)
        col_c.metric("Discentes assistidos", assistidos)

        pdf_buffer = gerar_pdf_mapa(medico_sel, especialidade, data_sel, turno_sel,
                                     atendimentos, total_faltosos=n_faltas)
        st.download_button(
            "🖨️ Baixar Mapa em PDF", data=pdf_buffer,
            file_name=f"Mapa_{medico_sel}_{data_sel.strftime('%d-%m-%Y')}.pdf",
            mime="application/pdf",
        )
    else:
        st.info("Selecione um médico para ver o mapa de atendimento.")

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
