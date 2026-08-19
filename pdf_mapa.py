"""
Gera o PDF do "Mapa de Atendimento Diário", replicando o layout oficial
do formulário impresso da UFPB/CRAS (mesma estrutura do arquivo .docx
usado como modelo: cabeçalho institucional com brasão, tabela numerada,
seção de Pesquisa/Extensão, contadores por categoria e assinaturas).
"""
from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, Image)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

LOGO_PATH = Path(__file__).parent / "assets" / "logo_cras.jpeg"

CODIGO_CONSULTA = {
    "Primeira consulta": "0",
    "Retorno": "1",
    "Acompanhamento/tratamento": "2",
}


def _categoria_atendimento(row):
    if row["servidor"] == "Sim":
        return "Servidor"
    elif row["assistido"] == "Sim":
        return "Disc. assistido (Prape)"
    else:
        return "Discente"


def gerar_pdf_mapa(medico, especialidade, data_sel, turno, atendimentos,
                    total_faltosos=0, chefe_setor=""):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                             leftMargin=1.0 * cm, rightMargin=1.0 * cm,
                             topMargin=0.8 * cm, bottomMargin=0.8 * cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle("titulo", parent=styles["Heading2"], alignment=TA_CENTER,
                                   fontName="Helvetica-Bold", fontSize=13, spaceAfter=2)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], alignment=TA_CENTER,
                                fontName="Helvetica-Bold", fontSize=9, leading=11)
    info_style = ParagraphStyle("info", parent=styles["Normal"], alignment=TA_CENTER,
                                 fontName="Helvetica-Bold", fontSize=9)

    elementos = []

    # --- Cabeçalho institucional (logo + texto) ---
    cabecalho_txt = Paragraph(
        "UNIVERSIDADE FEDERAL DA PARAÍBA<br/>"
        "CENTRO DE REFERÊNCIA EM ATENÇÃO À SAÚDE – CRAS<br/>"
        "Criação Resol. Consuni 04/2014<br/>"
        "Regimento Interno Resol. Consuni 14/2024", sub_style)
    if LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH), width=1.6 * cm, height=1.6 * cm)
        t_header = Table([[logo, cabecalho_txt, ""]], colWidths=[2.2 * cm, 21 * cm, 2.2 * cm])
        t_header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ]))
        elementos.append(t_header)
    else:
        elementos.append(cabecalho_txt)
    elementos.append(Spacer(1, 0.15 * cm))
    elementos.append(Paragraph("MAPA DE ATENDIMENTO DIÁRIO", titulo_style))
    elementos.append(Spacer(1, 0.1 * cm))

    # --- Linha de identificação (serviço / profissional / data / turno) ---
    marca_manha = "(X)" if turno == "MANHÃ" else "( )"
    marca_tarde = "(X)" if turno == "TARDE" else "( )"
    linha_info = (
        f"SERVIÇO: {especialidade or ''}&nbsp;&nbsp;&nbsp;"
        f"PROFISSIONAL: {medico or ''}&nbsp;&nbsp;&nbsp;"
        f"DATA: {data_sel.strftime('%d/%m/%Y')}&nbsp;&nbsp;&nbsp;"
        f"TURNO: MANHÃ {marca_manha}&nbsp;&nbsp;TARDE {marca_tarde}"
    )
    elementos.append(Paragraph(linha_info, info_style))
    elementos.append(Spacer(1, 0.12 * cm))

    # --- Tabela principal ---
    col_widths = [1.4 * cm, 1.9 * cm, 6.5 * cm, 3.2 * cm, 1.8 * cm, 4.2 * cm, 4.5 * cm]
    header_style = ParagraphStyle("th", parent=styles["Normal"], alignment=TA_CENTER,
                                   fontName="Helvetica-Bold", fontSize=8, textColor=colors.white,
                                   leading=9)
    cell_style = ParagraphStyle("td", parent=styles["Normal"], alignment=TA_LEFT,
                                 fontName="Helvetica", fontSize=8, leading=9)
    cell_center = ParagraphStyle("tdc", parent=cell_style, alignment=TA_CENTER)

    dados = [[
        Paragraph("Nº ORDEM", header_style), Paragraph("Nº CRAS", header_style),
        Paragraph("NOME DO USUÁRIO", header_style), Paragraph("MATRÍCULA/SIAPE", header_style),
        Paragraph("Consulta*", header_style), Paragraph("CATEGORIA USUÁRIO**", header_style),
        Paragraph("ASSINATURA DO USUÁRIO", header_style),
    ]]

    for i, a in enumerate(atendimentos[:12], start=1):
        cod = CODIGO_CONSULTA.get(a.get("consulta"), "")
        dados.append([
            Paragraph(str(i), cell_center), Paragraph(a.get("nr_cras") or "", cell_center),
            Paragraph(a.get("nome_usuario") or "", cell_style),
            Paragraph(a.get("matricula") or "", cell_center),
            Paragraph(cod, cell_center),
            Paragraph(_categoria_atendimento(a), cell_style), "",
        ])
    for i in range(len(atendimentos) + 1, 13):
        dados.append([Paragraph(str(i), cell_center), "", "", "", "", "", ""])
    # 1 linha em branco sem numeração (espaço extra, igual ao modelo original)
    for _ in range(1):
        dados.append(["", "", "", "", "", "", ""])

    t = Table(dados, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5E4E")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    elementos.append(t)

    # --- Linha "Projeto: Pesquisa ( ) Extensão ( )   Título do Projeto:" ---
    projeto_style = ParagraphStyle("projeto", parent=styles["Normal"], fontName="Helvetica-Bold",
                                    fontSize=8)
    t_projeto = Table(
        [[Paragraph("Projeto: Pesquisa ( )  Extensão ( )     Título do Projeto:", projeto_style)]],
        colWidths=[sum(col_widths)])
    t_projeto.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    elementos.append(t_projeto)

    # --- 6 linhas para Pesquisa/Extensão (em branco, preenchimento manual) ---
    dados_proj = []
    for i in range(1, 7):
        dados_proj.append([Paragraph(str(i), cell_center), "", "", "", "", "", ""])
    t_proj_tbl = Table(dados_proj, colWidths=col_widths)
    t_proj_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    elementos.append(t_proj_tbl)

    # --- Linha de resumo (contadores) ---
    servidores = sum(1 for a in atendimentos if a["servidor"] == "Sim")
    disc_assistido = sum(1 for a in atendimentos if a["assistido"] == "Sim" and a["servidor"] != "Sim")
    discentes = sum(1 for a in atendimentos if a["assistido"] != "Sim" and a["servidor"] != "Sim")
    primeira = sum(1 for a in atendimentos if a.get("consulta") == "Primeira consulta")
    retorno = sum(1 for a in atendimentos if a.get("consulta") == "Retorno")
    tratamento = sum(1 for a in atendimentos if a.get("consulta") == "Acompanhamento/tratamento")

    resumo_txt = (
        f"Servidor: {servidores}&nbsp;&nbsp;&nbsp;Discente: {discentes}&nbsp;&nbsp;&nbsp;"
        f"Discente assistido pela Prape: {disc_assistido}&nbsp;&nbsp;&nbsp;"
        f"Pesquisa/Extensão: 0&nbsp;&nbsp;&nbsp;Consulta: {primeira}&nbsp;&nbsp;&nbsp;"
        f"Retorno: {retorno}&nbsp;&nbsp;&nbsp;tratamento: {tratamento}&nbsp;&nbsp;&nbsp;"
        f"Faltosos: {total_faltosos}"
    )
    t_resumo = Table([[Paragraph(resumo_txt, projeto_style)]], colWidths=[sum(col_widths)])
    t_resumo.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    elementos.append(t_resumo)

    elementos.append(Spacer(1, 0.3 * cm))

    # --- Assinaturas ---
    nome_style = ParagraphStyle("nome", parent=styles["Normal"], fontName="Helvetica-Bold",
                                 fontSize=9, alignment=TA_CENTER)
    label_style = ParagraphStyle("label", parent=styles["Normal"], fontName="Helvetica-Bold",
                                  fontSize=8, alignment=TA_CENTER)
    linha_assin = "_" * 40

    t_assin = Table([
        [Paragraph(chefe_setor or "", nome_style), ""],
        [Paragraph(linha_assin, nome_style), Paragraph(linha_assin, nome_style)],
        [Paragraph("ASSINATURA CHEFE DE SETOR", label_style),
         Paragraph("ASSINATURA E CARIMBO DO PROFISSIONAL", label_style)],
    ], colWidths=[sum(col_widths) / 2, sum(col_widths) / 2])
    t_assin.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elementos.append(t_assin)

    elementos.append(Spacer(1, 0.2 * cm))
    nota_style = ParagraphStyle("nota", parent=styles["Normal"], fontSize=7.5)
    elementos.append(Paragraph(
        "* Consulta: primeira consulta (0)&nbsp;&nbsp;retorno (1)&nbsp;&nbsp;"
        "acompanhamento/tratamento (2)", nota_style))
    elementos.append(Paragraph("**Categoria: servidor, discente ou discente assistido", nota_style))

    doc.build(elementos)
    buffer.seek(0)
    return buffer
