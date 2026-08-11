"""
Gera o PDF do "Mapa de Atendimento Diário", equivalente ao botão
GerarMapaPDF do arquivo original.
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


def gerar_pdf_mapa(medico, especialidade, data_sel, turno, atendimentos, total_faltosos=0):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                             leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                             topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle("titulo", parent=styles["Heading2"], alignment=TA_CENTER)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], alignment=TA_CENTER)

    elementos = []
    elementos.append(Paragraph(
        "UNIVERSIDADE FEDERAL DA PARAÍBA<br/>"
        "CENTRO DE REFERÊNCIA EM ATENÇÃO À SAÚDE – CRAS", sub_style))
    elementos.append(Spacer(1, 0.3 * cm))
    elementos.append(Paragraph("MAPA DE ATENDIMENTO DIÁRIO", titulo_style))
    elementos.append(Spacer(1, 0.4 * cm))

    cabecalho = [
        ["SERVIÇO:", especialidade or "", "PROFISSIONAL:", medico or "",
         "DATA:", data_sel.strftime("%d/%m/%Y"), "TURNO:", turno or "Ambos"]
    ]
    t_cab = Table(cabecalho, colWidths=[2.2*cm, 4.5*cm, 2.8*cm, 5*cm, 1.8*cm, 2.5*cm, 1.8*cm, 2.5*cm])
    t_cab.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(t_cab)
    elementos.append(Spacer(1, 0.4 * cm))

    # Nota: 'atendimentos' já vem filtrado só com status='Realizado' (feito em
    # db.get_mapa_atendimento) — o mapa impresso mostra apenas quem
    # efetivamente foi atendido.
    dados = [["Nº ORDEM", "Nº CRAS", "NOME DO USUÁRIO", "MATRÍCULA/SIAPE", "CATEGORIA USUÁRIO", "ASSINATURA"]]

    totais = {"Servidor": 0, "Disc. Assistido": 0, "Disc. Nao Assist.": 0}
    for i, a in enumerate(atendimentos[:12], start=1):
        if a["servidor"] == "Sim":
            categoria = "Servidor"
        elif a["assistido"] == "Sim":
            categoria = "Disc. Assistido"
        else:
            categoria = "Disc. Nao Assist."
        totais[categoria] += 1
        dados.append([
            str(i), a.get("nr_cras") or "", a.get("nome_usuario") or "",
            a.get("matricula") or "", categoria, ""
        ])

    # Preenche linhas em branco até 12
    for i in range(len(atendimentos) + 1, 13):
        dados.append([str(i), "", "", "", "", ""])

    t = Table(dados, colWidths=[1.8*cm, 2.2*cm, 6*cm, 3.2*cm, 3.8*cm, 3.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5E4E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
    ]))
    elementos.append(t)
    elementos.append(Spacer(1, 0.5 * cm))

    resumo = [[
        f"Servidor: {totais['Servidor']}", f"Discente: {totais['Disc. Nao Assist.']}",
        f"Disc. Assistido (Prape): {totais['Disc. Assistido']}",
        f"Total Atendidos: {len(atendimentos)}", f"Faltosos: {total_faltosos}"
    ]]
    t_resumo = Table(resumo, colWidths=[5*cm, 5*cm, 6*cm, 4*cm, 3*cm])
    t_resumo.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(t_resumo)

    doc.build(elementos)
    buffer.seek(0)
    return buffer
