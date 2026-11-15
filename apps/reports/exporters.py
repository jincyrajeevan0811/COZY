import csv
import io
from decimal import Decimal

from django.http import HttpResponse


def _filename(report, start, end, ext):
    return f"cozy-{report['title'].lower().replace(' ', '-').replace('&', 'and')}-{start}-to-{end}.{ext}"


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def export_csv(report, start, end):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{_filename(report, start, end, "csv")}"'
    writer = csv.writer(response)
    writer.writerow(report["columns"])
    for row in report["rows"]:
        writer.writerow(row)
    if report.get("totals"):
        writer.writerow(report["totals"])
    return response


def export_xlsx(report, start, end):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = report["title"][:30]
    ws.append([f"COZY — {report['title']}", f"{start} to {end}"])
    ws["A1"].font = Font(bold=True, size=13, color="B76E79")
    ws.append([])
    ws.append(report["columns"])
    for cell in ws[3]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F3E9DC")
    for row in report["rows"]:
        ws.append([_plain(v) for v in row])
    if report.get("totals"):
        ws.append([_plain(v) for v in report["totals"]])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
    for idx in report.get("money_cols", []):
        col = ws.cell(row=3, column=idx + 1).column_letter
        for cell in ws[col][3:]:
            cell.number_format = '₹#,##0.00'
    for column in ws.columns:
        width = max(len(str(c.value or "")) for c in column) + 2
        ws.column_dimensions[column[0].column_letter].width = min(width, 45)
    buffer = io.BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{_filename(report, start, end, "xlsx")}"'
    return response


def export_pdf(report, start, end):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def fmt(value, idx):
        if idx in report.get("money_cols", []) and isinstance(value, (int, float, Decimal)):
            return f"Rs. {value:,.2f}"
        return str(value)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    data = [report["columns"]] + [[fmt(v, i) for i, v in enumerate(row)] for row in report["rows"]]
    if report.get("totals"):
        data.append([fmt(v, i) for i, v in enumerate(report["totals"])])
    table = Table(data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3E9DC")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5D9CC")),
    ]
    if report.get("totals"):
        style.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
    table.setStyle(TableStyle(style))
    story = [Paragraph(f"COZY — {report['title']}", styles["Title"]),
             Paragraph(f"{start} to {end}", styles["Normal"]), Spacer(1, 6 * mm), table]
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{_filename(report, start, end, "pdf")}"'
    return response
