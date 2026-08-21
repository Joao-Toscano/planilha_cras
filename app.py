import streamlit as st
from datetime import date
from pathlib import Path
import pandas as pd

import db
from pdf_mapa import gerar_pdf_mapa

ASSETS = Path(__file__).parent / "assets"

PAGINAS_ADMIN = ["📝 Lançamento Diário", "🖨️ Mapa de Atendimento", "📊 Dashboard", "📁 Base de Dados"]
PAGINAS_RECEPCAO = ["📝 Lançamento Diário", "🖨️ Mapa de Atendimento"]

USUARIOS = {
    "admin": {"chave_senha": "senha_admin", "perfil": "admin", "rotulo": "Administrador"},
    "recepcao": {"chave_senha": "senha_recepcao", "perfil": "recepcao", "rotulo": "Recepção"},
}


import base64


def _img_b64(nome_arquivo):
    return base64.b64encode((ASSETS / nome_arquivo).read_bytes()).decode()


def mostrar_logo_principal(width=170):
    st.markdown(
        f"<div style='text-align:center;'>"
        f"<img src='data:image/png;base64,{_img_b64('logo_cras_ufpb.png')}' width='{width}'>"
        f"</div>", unsafe_allow_html=True
    )


def mostrar_rodape_gesp():
    st.divider()
    st.markdown(
        "<p style='text-align:center;color:gray;font-size:0.85rem;'>Desenvolvido por</p>"
        f"<div style='text-align:center;'>"
        f"<img src='data:image/png;base64,{_img_b64('logo_gesp.png')}' width='90'>"
        f"</div>", unsafe_allow_html=True
    )


def tela_configuracao_inicial():
    mostrar_logo_principal()
    st.markdown("<h1 style='text-align:center;'>Sistema de Atendimento CRAS</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:gray;'>Primeira configuração</p>", unsafe_allow_html=True)
    st.write("")
    st.write("Antes de começar a usar o sistema, defina as senhas de acesso para os dois perfis "
             "(usuários **admin** e **recepcao**).")
    with st.form("form_setup"):
        st.subheader("Administrador  (usuário: admin)")
        st.caption("Acesso total: Lançamento, Mapa, Dashboard e Base de Dados.")
        senha_admin = st.text_input("Senha do Administrador", type="password")
        confirmar_admin = st.text_input("Confirme a senha do Administrador", type="password")
        st.subheader("Recepção  (usuário: recepcao)")
        st.caption("Acesso a Lançamento Diário e Mapa de Atendimento.")
        senha_recepcao = st.text_input("Senha da Recepção", type="password")
        confirmar_recepcao = st.text_input("Confirme a senha da Recepção", type="password")
        enviar = st.form_submit_button("Salvar e continuar", width='stretch')

    if enviar:
        if not senha_admin or not senha_recepcao:
            st.error("Preencha as duas senhas.")
        elif senha_admin != confirmar_admin or senha_recepcao != confirmar_recepcao:
            st.error("A confirmação não coincide com a senha digitada.")
        else:
            db.set_config("senha_admin", senha_admin)
            db.set_config("senha_recepcao", senha_recepcao)
            st.success("Senhas definidas! Redirecionando para o login...")
            st.rerun()

    mostrar_rodape_gesp()


def tela_login():
    mostrar_logo_principal()
    st.markdown("<h1 style='text-align:center;'>Sistema de Atendimento CRAS</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:gray;'>Faça login para continuar</p>",
                unsafe_allow_html=True)
    st.write("")

    col_form, col_info = st.columns(2)
    with col_form:
        usuario = st.text_input("Usuário", key="login_usuario", placeholder="admin ou recepcao")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar", width='stretch'):
            u = USUARIOS.get(usuario.strip().lower())
            if u and senha and senha == db.get_config(u["chave_senha"], None):
                st.session_state["perfil"] = u["perfil"]
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    with col_info:
        st.info(
            "**Perfis disponíveis:**\n\n"
            "- **admin** — acesso total (Lançamento, Mapa, Dashboard, Base de Dados)\n"
            "- **recepcao** — acesso a Lançamento Diário e Mapa de Atendimento\n\n"
            "Esqueceu a senha? Peça para um Administrador redefinir em "
            "**Base de Dados > ⚙️ Configurações**."
        )

    mostrar_rodape_gesp()


st.set_page_config(page_title="CRAS - Sistema de Atendimento", page_icon="🏥", layout="wide")
resultado_init = db.init_db()

# Primeiro acesso: força a definição das senhas antes de liberar qualquer página
if not db.get_config("senha_admin") or not db.get_config("senha_recepcao"):
    tela_configuracao_inicial()
    st.stop()

# Login: exige usuário + senha antes de mostrar qualquer página
if "perfil" not in st.session_state:
    tela_login()
    st.stop()

if resultado_init["erros"]:
    with st.sidebar:
        st.error("⚠️ Problemas ao carregar os dados — veja 'Base de Dados > Diagnóstico'.")
elif resultado_init["info"]:
    with st.sidebar:
        st.info("ℹ️ Alguns dados foram completados automaticamente — veja 'Base de Dados > Diagnóstico'.")

with st.sidebar:
    st.markdown(
        f"<div style='text-align:center;'>"
        f"<img src='data:image/png;base64,{_img_b64('logo_cras_ufpb.png')}' width='120'>"
        f"</div>", unsafe_allow_html=True
    )

st.sidebar.title("🏥 CRAS")

opcoes_pagina = PAGINAS_ADMIN if st.session_state["perfil"] == "admin" else PAGINAS_RECEPCAO
pagina = st.sidebar.radio("Navegação", opcoes_pagina)

st.sidebar.divider()
rotulo_perfil = "Administrador" if st.session_state["perfil"] == "admin" else "Recepção"
st.sidebar.caption(f"Conectado como **{rotulo_perfil}**")
if st.sidebar.button("🚪 Sair"):
    del st.session_state["perfil"]
    st.rerun()

with st.sidebar:
    st.divider()
    st.markdown(
        "<p style='text-align:center;color:gray;font-size:0.8rem;margin-bottom:4px;'>"
        "Desenvolvido por</p>"
        f"<div style='text-align:center;'>"
        f"<img src='data:image/png;base64,{_img_b64('logo_gesp.png')}' width='60'>"
        f"</div>", unsafe_allow_html=True
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
            nr_matricula = st.text_input("Nº Matrícula/SIAPE")
        with col2:
            medico = st.selectbox("Nome do médico", nomes_medicos, index=None,
                                   placeholder="Selecione o médico")
            categoria = st.radio(
                "Categoria do atendimento",
                ["Discente (não assistido)", "Discente assistido (Prape)", "Servidor"],
                horizontal=False,
            )
            consulta = st.radio(
                "Tipo de consulta",
                ["Primeira consulta", "Retorno", "Acompanhamento/tratamento"],
                horizontal=False,
            )

        enviado = st.form_submit_button("💾 Salvar na Base", width='stretch')

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
                                   nr_matricula, categoria_key, consulta)
            st.success("Registro salvo com sucesso!")

    st.divider()

    # -----------------------------------------------------------------
    # Adicionar dia só com médico + turno (sem dados de paciente)
    # -----------------------------------------------------------------
    with st.expander("➕ Adicionar dia (só médico e turno) — marcar se ele veio ou não"):
        st.caption("Use aqui quando quiser só registrar presença/falta do profissional num dia/"
                   "turno, sem lançar nenhum paciente específico.")
        with st.form("form_dia_medico", clear_on_submit=True):
            cold1, cold2, cold3 = st.columns(3)
            with cold1:
                medico_dia = st.selectbox("Médico", nomes_medicos, index=None,
                                           placeholder="Selecione o médico", key="medico_dia")
            with cold2:
                data_dia = st.date_input("Data", value=date.today(), format="DD/MM/YYYY",
                                          key="data_dia")
            with cold3:
                turno_dia = st.selectbox("Turno", ["MANHÃ", "TARDE"], key="turno_dia")
            veio = st.radio("Situação do profissional", ["Presença", "Falta", "Feriado"],
                            horizontal=True)
            enviar_dia = st.form_submit_button("Registrar")

        if enviar_dia:
            if not medico_dia:
                st.error("Selecione o médico.")
            else:
                db.registrar_dia(data_dia, medico_dia, turno_dia, veio)
                st.success(f"Dia registrado: {medico_dia} — {data_dia.strftime('%d/%m/%Y')} "
                           f"({turno_dia}) — {veio}.")

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
        df_rev["nome_usuario"] = df_rev["nome_usuario"].fillna("").replace(
            "", "(sem paciente — marcador de presença)")
        df_rev["motivo"] = df_rev["motivo"].fillna("")
        df_rev_exibir = df_rev[["medico", "turno", "nome_usuario", "matricula", "motivo", "status"]].copy()
        df_rev_exibir.columns = ["Médico", "Turno", "Nome do usuário", "Matrícula", "Motivo", "Status"]

        editado = st.data_editor(
            df_rev_exibir,
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=db.STATUS_OPCOES, required=True
                ),
            },
            disabled=["Médico", "Turno", "Nome do usuário", "Matrícula", "Motivo"],
            width='stretch',
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

        with st.expander("🗑️ Excluir um lançamento (feito por engano, duplicado, etc.)"):
            opcoes = {
                f"{r['nome_usuario'] or '(sem nome)'} — {r['medico']} — {r['turno']} — {r['status']}": r["id"]
                for r in registros
            }
            escolha = st.selectbox("Lançamento a excluir", list(opcoes.keys()), index=None,
                                    placeholder="Selecione", key="lancamento_excluir")
            if st.button("Excluir definitivamente", type="secondary") and escolha:
                db.excluir_atendimento(opcoes[escolha])
                st.success("Lançamento excluído.")
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

    chefe_setor = st.text_input(
        "Nome do Chefe de Setor (para a assinatura no PDF)",
        value=db.get_config("chefe_setor", ""),
        help="Fica salvo para os próximos mapas gerados.",
    )
    if chefe_setor != db.get_config("chefe_setor", ""):
        db.set_config("chefe_setor", chefe_setor)

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
                ["nr_cras", "nome_usuario", "matricula", "consulta", "assistido", "servidor"]
            ]
            df.columns = ["Nº CRAS", "Nome do usuário", "Matrícula", "Tipo de consulta",
                           "Assistido", "Servidor"]
            st.dataframe(df, width='stretch', hide_index=True)
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
                                     atendimentos, total_faltosos=n_faltas,
                                     chefe_setor=chefe_setor)
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
    st.caption("Os mesmos 10 gráficos da planilha original (aba 'Dinâmicas'), calculados a partir "
               "do histórico real + lançamentos feitos aqui no app.")

    base_df = db.get_base_df()

    if base_df.empty:
        st.info("Ainda não há atendimentos registrados. Use a página de Lançamento Diário.")
    else:
        import plotly.express as px

        base_df["data"] = pd.to_datetime(base_df["data"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Dias com atendimento", base_df["data"].nunique())
        col2.metric("Total de atendimentos", int(base_df["total_atendidos"].sum()))
        col3.metric("Servidores atendidos", int(base_df["atendidos_servidores"].sum()))
        col4.metric("Discentes assistidos", int(base_df["discentes_assistidos"].sum()))

        st.divider()

        anos = sorted(base_df["data"].dt.year.unique(), reverse=True)
        ano_sel = st.selectbox("Filtrar por ano", ["Todos"] + [str(a) for a in anos])
        df = base_df if ano_sel == "Todos" else base_df[base_df["data"].dt.year == int(ano_sel)]

        CORES = ["#00622F", "#3C8659", "#7DAE8C", "#B8D4C2", "#C9A227"]

        # 1) Metas x Atendimentos por Médico
        st.subheader("Metas/Atendimentos por Médico")
        por_med = df.groupby("medico").agg(
            Atendidos=("total_atendidos", "sum"), Dias=("data", "count")
        ).reset_index().sort_values("Atendidos", ascending=False)

        # Meta diária de referência por médico: o valor mais frequente entre os
        # dias com meta > 0 (alguns dias vêm com meta=0 na base histórica —
        # não usamos esses para não subestimar a meta diária real).
        meta_diaria = (
            df[df["meta"] > 0].groupby("medico")["meta"]
            .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else 0)
        )
        por_med["MetaDiaria"] = por_med["medico"].map(meta_diaria).fillna(0)
        por_med["Meta"] = por_med["Dias"] * por_med["MetaDiaria"]

        fig1 = px.bar(por_med, x="medico", y=["Atendidos", "Meta"], barmode="group",
                      labels={"medico": "", "value": "Quantidade", "variable": ""},
                      hover_data={"Dias": True, "MetaDiaria": True},
                      color_discrete_sequence=CORES)
        st.plotly_chart(fig1, width='stretch')
        st.caption("Meta = dias contabilizados no período × meta diária do médico.")

        c1, c2 = st.columns(2)
        with c1:
            # 2) Metas x Atendimentos por Especialidade
            st.subheader("Metas/Atendimentos por Especialidade")
            por_esp = df.groupby("especialidade").agg(
                Atendidos=("total_atendidos", "sum"), Meta=("meta", "sum")
            ).reset_index().sort_values("Atendidos", ascending=False)
            fig2 = px.bar(por_esp, x="especialidade", y=["Atendidos", "Meta"], barmode="group",
                          labels={"especialidade": "", "value": "Quantidade", "variable": ""},
                          color_discrete_sequence=CORES)
            st.plotly_chart(fig2, width='stretch')
        with c2:
            # 3) Categoria dos Atendimentos (pizza)
            st.subheader("Categoria dos Atendimentos")
            cat = pd.DataFrame({
                "Categoria": ["Servidor", "Discente", "Discente assistido (Prape)"],
                "Total": [df["atendidos_servidores"].sum(), df["discentes_naoassistidos"].sum(),
                          df["discentes_assistidos"].sum()],
            })
            fig3 = px.pie(cat, names="Categoria", values="Total", color_discrete_sequence=CORES)
            st.plotly_chart(fig3, width='stretch')

        # 4) Classificação de Desempenho por Médico
        st.subheader("Classificação de Desempenho por Médico")
        desemp = df[df["classif_desempenho"].notna()].groupby(
            ["medico", "classif_desempenho"]).size().reset_index(name="Dias")
        fig4 = px.bar(desemp, x="medico", y="Dias", color="classif_desempenho", barmode="stack",
                      labels={"medico": "", "classif_desempenho": ""},
                      color_discrete_sequence=CORES)
        st.plotly_chart(fig4, width='stretch')

        c3, c4 = st.columns(2)
        with c3:
            # 5) Ano x Atendimentos
            st.subheader("Ano x Atendimentos")
            por_ano = base_df.groupby(base_df["data"].dt.year)["total_atendidos"].sum().reset_index()
            por_ano.columns = ["Ano", "Atendidos"]
            fig5 = px.bar(por_ano, x="Ano", y="Atendidos", color_discrete_sequence=CORES)
            fig5.update_xaxes(type="category")
            st.plotly_chart(fig5, width='stretch')
        with c4:
            # 6) Meses x Atendimentos
            st.subheader("Meses x Atendimentos")
            por_mes = df.groupby("mes")["total_atendidos"].sum().reindex(db.NOMES_MES).dropna().reset_index()
            por_mes.columns = ["Mês", "Atendidos"]
            fig6 = px.bar(por_mes, x="Mês", y="Atendidos", color_discrete_sequence=CORES)
            st.plotly_chart(fig6, width='stretch')

        # 7) Médico x Atendimentos
        st.subheader("Médico x Atendimentos")
        med_at = df.groupby("medico")["total_atendidos"].sum().sort_values(ascending=False).reset_index()
        med_at.columns = ["Médico", "Atendidos"]
        fig7 = px.bar(med_at, x="Médico", y="Atendidos", color_discrete_sequence=CORES)
        st.plotly_chart(fig7, width='stretch')

        c5, c6 = st.columns(2)
        with c5:
            # 8) Categoria das Faltas Profissionais (pizza)
            st.subheader("Categoria das Faltas Profissionais")
            faltas_map = {0: "Presença", 1: "Ausência", 2: "Férias/Feriado"}
            fp = df[df["falta_profissional"].notna()].copy()
            fp["categoria"] = fp["falta_profissional"].map(faltas_map)
            fp_cont = fp.groupby("categoria").size().reset_index(name="Total")
            fig8 = px.pie(fp_cont, names="categoria", values="Total", color_discrete_sequence=CORES)
            st.plotly_chart(fig8, width='stretch')
        with c6:
            # 10) Categoria do Desempenho (pizza) — geral, não por médico
            st.subheader("Categoria do Desempenho")
            desemp_geral = df.groupby("classif_desempenho").size().reset_index(name="Total")
            desemp_geral = desemp_geral[desemp_geral["classif_desempenho"].notna()]
            fig10 = px.pie(desemp_geral, names="classif_desempenho", values="Total",
                           color_discrete_sequence=CORES)
            st.plotly_chart(fig10, width='stretch')

        # 9) Médicos x Faltas Profissionais
        st.subheader("Médicos x Faltas Profissionais")
        fp_med = df[df["falta_profissional"].notna()].copy()
        fp_med["categoria"] = fp_med["falta_profissional"].map(faltas_map)
        fp_med_cont = fp_med.groupby(["medico", "categoria"]).size().reset_index(name="Dias")
        fig9 = px.bar(fp_med_cont, x="medico", y="Dias", color="categoria", barmode="stack",
                      labels={"medico": "", "categoria": ""}, color_discrete_sequence=CORES)
        st.plotly_chart(fig9, width='stretch')

        with st.expander("Ver tabela completa do histórico"):
            st.dataframe(df.sort_values("data", ascending=False), width='stretch', hide_index=True)

# =====================================================================
# PÁGINA 4 — Base de Dados (equivalente às abas "Ficha" e "Base")
# =====================================================================
elif pagina == "📁 Base de Dados":
    st.title("Base de Dados")

    aba = st.tabs(["Ficha (todos os atendimentos)", "Base (resumo por dia/médico)",
                   "Médicos cadastrados", "⚙️ Configurações", "🔧 Diagnóstico"])

    with aba[0]:
        df = db.get_ficha_df()
        st.dataframe(df, width='stretch', hide_index=True)
        if not df.empty:
            st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode("utf-8"),
                                "ficha.csv", "text/csv")

    with aba[1]:
        df = db.get_base_df()
        st.dataframe(df, width='stretch', hide_index=True)
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
        st.dataframe(df_medicos, width='stretch', hide_index=True)

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
        st.subheader("🔒 Senhas de acesso")
        st.caption("Trocar a senha de um perfil desconecta imediatamente qualquer sessão aberta "
                   "com a senha antiga (é preciso entrar de novo).")

        col_a, col_r = st.columns(2)
        with col_a:
            st.markdown("**Administrador**")
            with st.form("form_senha_admin"):
                nova_admin = st.text_input("Nova senha", type="password", key="nova_senha_admin")
                confirmar_admin = st.text_input("Confirme", type="password", key="conf_senha_admin")
                salvar_admin = st.form_submit_button("Salvar senha do Administrador")
            if salvar_admin:
                if not nova_admin:
                    st.error("A senha não pode ficar em branco.")
                elif nova_admin != confirmar_admin:
                    st.error("As senhas não coincidem.")
                else:
                    db.set_config("senha_admin", nova_admin)
                    st.success("Senha do Administrador atualizada.")

        with col_r:
            st.markdown("**Recepção**")
            with st.form("form_senha_recepcao"):
                nova_recepcao = st.text_input("Nova senha", type="password", key="nova_senha_recepcao")
                confirmar_recepcao = st.text_input("Confirme", type="password", key="conf_senha_recepcao")
                salvar_recepcao = st.form_submit_button("Salvar senha da Recepção")
            if salvar_recepcao:
                if not nova_recepcao:
                    st.error("A senha não pode ficar em branco.")
                elif nova_recepcao != confirmar_recepcao:
                    st.error("As senhas não coincidem.")
                else:
                    db.set_config("senha_recepcao", nova_recepcao)
                    st.success("Senha da Recepção atualizada.")

        st.divider()
        st.subheader("Nome do Chefe de Setor")
        st.caption("Usado na assinatura do Mapa de Atendimento em PDF (também editável na "
                   "página 'Mapa de Atendimento').")
        chefe_config = st.text_input("Nome", value=db.get_config("chefe_setor", ""),
                                      key="chefe_setor_config")
        if chefe_config != db.get_config("chefe_setor", ""):
            db.set_config("chefe_setor", chefe_config)
            st.success("Salvo.")

    with aba[4]:
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
