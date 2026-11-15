"""PDF invoice generation with ReportLab."""
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.website_settings.models import WebsiteSetting

ROSE = colors.HexColor("#B76E79")
CHARCOAL = colors.HexColor("#2B2B2B")
CHAMPAGNE = colors.HexColor("#F3E9DC")


def _rs(value):
    # The built-in PDF fonts don't include the ₹ glyph, so use "Rs."
    return f"Rs. {value:,.2f}"


def build_invoice_pdf(order):
    site = WebsiteSetting.load()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Invoice {order.order_number}")
    styles = getSampleStyleSheet()
    brand = ParagraphStyle("brand", parent=styles["Title"], fontName="Times-Bold", fontSize=26, textColor=ROSE,
                           alignment=0, spaceAfter=2)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=CHARCOAL)
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=9.5, leading=13, textColor=CHARCOAL)
    heading = ParagraphStyle("heading", parent=normal, fontName="Helvetica-Bold", fontSize=10)

    story = []
    seller = [f"<b>{site.site_name} Fashion Jewellery</b>"]
    if site.address:
        seller.append(site.address.replace("\n", "<br/>"))
    seller.append(f"{site.contact_email} {('· ' + site.contact_phone) if site.contact_phone else ''}")
    if site.gstin:
        seller.append(f"GSTIN: {site.gstin}")

    header = Table(
        [[Paragraph(site.site_name, brand), Paragraph("<b>TAX INVOICE</b>", ParagraphStyle(
            "inv", parent=normal, alignment=2, fontSize=14, textColor=CHARCOAL))],
         [Paragraph("<br/>".join(seller), small), Paragraph(
             f"Invoice no: <b>INV-{order.order_number}</b><br/>Order no: {order.order_number}<br/>"
             f"Order date: {timezone.localtime(order.created_at):%d %b %Y}<br/>"
             f"Payment: {order.get_payment_method_display()} ({order.get_payment_status_display()})",
             ParagraphStyle("meta", parent=small, alignment=2))]],
        colWidths=[95 * mm, 79 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 8 * mm)]

    address = "<br/>".join([f"<b>{order.full_name}</b>"] + order.address_lines + [f"Phone: {order.phone}", order.email])
    story += [Paragraph("Bill / Ship to", heading), Paragraph(address, normal), Spacer(1, 6 * mm)]

    rows = [["#", "Item", "SKU", "Qty", "Unit price", "Amount"]]
    for idx, item in enumerate(order.items.all(), start=1):
        name = item.product_name + (f"<br/><font size=8 color='#777777'>{item.variant_name}</font>" if item.variant_name else "")
        rows.append([str(idx), Paragraph(name, normal), item.sku, str(item.quantity), _rs(item.unit_price), _rs(item.line_total)])
    table = Table(rows, colWidths=[8 * mm, 72 * mm, 30 * mm, 12 * mm, 26 * mm, 26 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CHAMPAGNE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5D9CC")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [table, Spacer(1, 4 * mm)]

    totals = [["Subtotal", _rs(order.subtotal)]]
    if order.coupon_discount:
        totals.append([f"Coupon ({order.coupon_code})", f"- {_rs(order.coupon_discount)}"])
    totals.append(["Shipping", _rs(order.shipping_charge) if order.shipping_charge else "FREE"])
    if order.gift_wrap_charge:
        totals.append(["Gift wrap", _rs(order.gift_wrap_charge)])
    if order.cod_charge:
        totals.append(["COD charge", _rs(order.cod_charge)])
    tax_label = f"GST {order.tax_percent:.0f}% ({'included' if order.tax_inclusive else 'added'})"
    totals.append([tax_label, _rs(order.tax_amount)])
    totals.append(["Grand total", _rs(order.grand_total)])
    tot = Table(totals, colWidths=[50 * mm, 35 * mm], hAlign="RIGHT")
    tot.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, ROSE),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
    ]))
    story += [tot, Spacer(1, 10 * mm)]
    story.append(Paragraph(
        "Thank you for shopping with COZY! This is a computer-generated invoice and does not require a signature. "
        f"{site.return_policy_summary}", small))
    doc.build(story)
    return buffer.getvalue()
