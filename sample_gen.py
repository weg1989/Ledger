"""Generates a handful of synthetic invoice PDFs so the pipeline can be tested
end-to-end without needing real vendor data. Not part of the shipped pipeline."""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
os.makedirs(OUT, exist_ok=True)


def draw_invoice(path, *, invoice_no="INV-10432", inv_date="03/14/2026",
                  vendor="Northwind Office Supplies Ltd.", po_number="PO-88291",
                  items=None, subtotal=None, tax=None, total=None,
                  tax_label="Tax (8%)", omit_invoice_no=False, omit_total=False):
    items = items or [
        ("A4 Paper Ream (500 sheets)", 40, 4.25, 170.00),
        ("Toner Cartridge - Black", 6, 62.50, 375.00),
        ("Stapler Heavy Duty", 10, 8.90, 89.00),
    ]
    if subtotal is None:
        subtotal = sum(i[3] for i in items)
    if tax is None:
        tax = round(subtotal * 0.08, 2)
    if total is None:
        total = round(subtotal + tax, 2)

    c = canvas.Canvas(path, pagesize=letter)
    w, h = letter
    y = h - inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, y, vendor)
    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(inch, y, "1420 Commerce Drive, Suite 200, Austin, TX 78701")
    y -= 30

    c.setFont("Helvetica-Bold", 13)
    c.drawString(inch, y, "INVOICE")
    y -= 20
    c.setFont("Helvetica", 10)
    if not omit_invoice_no:
        c.drawString(inch, y, f"Invoice Number: {invoice_no}")
        y -= 15
    c.drawString(inch, y, f"Invoice Date: {inv_date}")
    y -= 15
    if po_number:
        c.drawString(inch, y, f"PO Number: {po_number}")
        y -= 15
    c.drawString(inch, y, "Bill To: Acme Manufacturing Corp, 900 Industrial Pkwy")
    y -= 30

    # table header
    c.setFont("Helvetica-Bold", 9)
    cols = [inch, 3.6 * inch, 4.4 * inch, 5.4 * inch]
    headers = ["Description", "Qty", "Unit Price", "Amount"]
    for cx, htext in zip(cols, headers):
        c.drawString(cx, y, htext)
    y -= 5
    c.line(inch, y, 6.9 * inch, y)
    y -= 15

    c.setFont("Helvetica", 9)
    for desc, qty, price, amt in items:
        c.drawString(cols[0], y, desc)
        c.drawString(cols[1], y, str(qty))
        c.drawString(cols[2], y, f"${price:,.2f}")
        c.drawString(cols[3], y, f"${amt:,.2f}")
        y -= 15

    y -= 10
    c.line(4.2 * inch, y, 6.9 * inch, y)
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(4.4 * inch, y, "Subtotal:")
    c.drawString(5.6 * inch, y, f"${subtotal:,.2f}")
    y -= 15
    c.drawString(4.4 * inch, y, f"{tax_label}:")
    c.drawString(5.6 * inch, y, f"${tax:,.2f}")
    y -= 15
    if not omit_total:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(4.4 * inch, y, "Total Due:")
        c.drawString(5.6 * inch, y, f"${total:,.2f}")

    c.setFont("Helvetica", 7)
    c.drawString(inch, 0.5 * inch, "Thank you for your business.  Payment due within 30 days.")
    c.save()
    return {"invoice_no": invoice_no, "vendor": vendor, "po_number": po_number,
            "subtotal": subtotal, "tax": tax, "total": total}


if True:  # generate samples now
    # 1. Clean, happy-path invoice
    info1 = draw_invoice(f"{OUT}/clean_invoice.pdf")
    print("clean_invoice.pdf ->", info1)

    # 2. Same invoice re-sent (duplicate) - identical content
    draw_invoice(f"{OUT}/duplicate_invoice.pdf")

    # 3. Split-PO invoice: partial billing against a larger PO
    info3 = draw_invoice(
        f"{OUT}/split_po_invoice.pdf",
        invoice_no="INV-10500", po_number="PO-77000",
        vendor="Steelwork Fabrication Inc.",
        items=[("Structural Steel Beams - Batch 2 of 3", 12, 410.00, 4920.00)],
    )
    print("split_po_invoice.pdf ->", info3)

    # 4. Missing invoice number AND total (degraded scan style)
    draw_invoice(
        f"{OUT}/missing_fields_invoice.pdf",
        omit_invoice_no=True, omit_total=True,
        vendor="QuickPrint Graphics", po_number=None,
    )

    # 5. Embedded-tax invoice: tax is a nonzero, explicitly-labeled amount
    #    that is already included in the subtotal (not additive). A naive
    #    "subtotal + tax == total" check would wrongly flag this as a
    #    370.37 mismatch; tax_mode-aware validation should not.
    items5 = [("Consulting Services - March Retainer", 1, 5000.00, 5000.00)]
    draw_invoice(
        f"{OUT}/embedded_tax_invoice.pdf",
        invoice_no="INV-20911", po_number="PO-55110",
        vendor="Meridian Consulting Group",
        items=items5, subtotal=5000.00, tax=370.37, total=5000.00,
        tax_label="Tax (VAT included)",
    )

    print("All sample PDFs generated in", OUT)

    # 6. No-PO invoice: every mandatory field present EXCEPT the PO number.
    #    Can't be safely auto-approved (no way to verify against a purchase
    #    order) or safely rejected (nothing else is wrong with it) -- this is
    #    exactly the case the vendor correspondence system exists for.
    info6 = draw_invoice(
        f"{OUT}/no_po_invoice.pdf",
        invoice_no="INV-30044", po_number=None,
        vendor="BrightPath Logistics",
        items=[("Freight - March consolidated shipment", 1, 2450.00, 2450.00)],
        subtotal=2450.00, tax=0.00, total=2450.00, tax_label="Tax (n/a)",
    )
    print("no_po_invoice.pdf ->", info6)

    # 7. Scanned-image version of the happy-path invoice: same content, but
    #    flattened to a PNG so there's no text layer -> forces Tier 2 (OCR + LLM).
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(f"{OUT}/clean_invoice.pdf", dpi=200)
        pages[0].save(f"{OUT}/scanned_invoice.png")
        print("scanned_invoice.png -> generated from clean_invoice.pdf")
    except Exception as e:
        print("Could not generate scanned_invoice.png (needs poppler/pdf2image):", e)
