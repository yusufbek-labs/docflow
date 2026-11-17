"""Synthetic sample invoices (reportlab). All companies are fictional.

Six PDFs across three layouts; the last one is deliberately broken (its printed
subtotal and total do not match its line items) so it must land in "Needs review".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

D = Decimal
CENT = D("0.01")


@dataclass
class Sample:
    filename: str
    layout: str                       # classic | modern | compact
    vendor: str
    vendor_addr: list[str]
    customer: str
    customer_addr: list[str]
    number: str
    issued: tuple[int, int, int]      # y, m, d
    due: tuple[int, int, int]
    currency: str
    tax_rate: Decimal
    items: list[tuple[str, Decimal, Decimal]]
    printed_subtotal: Decimal | None = None      # overrides to create a broken invoice
    printed_total: Decimal | None = None
    broken: bool = False

    @property
    def subtotal(self) -> Decimal:
        return sum((q * p for _, q, p in self.items), D(0))


SAMPLES: list[Sample] = [
    Sample("invoice_01_brightwave.pdf", "classic", "Brightwave Studios Ltd",
           ["14 Orchard Lane", "Portland, OR 97201"], "Marlow & Finch Retail Inc.",
           ["880 Commerce Street", "Seattle, WA 98101"], "INV-1001",
           (2025, 3, 4), (2025, 4, 3), "USD", D("8"),
           [("Brand identity package", D(1), D("2400.00")),
            ("Website copywriting (pages)", D(8), D("150.00")),
            ("Stock photo licenses", D(12), D("15.00"))]),
    Sample("invoice_02_copperline.pdf", "classic", "Copperline Supply Co.",
           ["2200 Foundry Road", "Columbus, OH 43215"], "Tidewater Bakery LLC",
           ["31 Harbor Way", "Baltimore, MD 21201"], "INV-20458",
           (2025, 5, 19), (2025, 6, 18), "USD", D("6.5"),
           [('Copper fittings 3/4" (box)', D(20), D("42.50")),
            ("Pipe cutter", D(2), D("18.75")),
            ("Delivery", D(1), D("35.00"))]),
    Sample("invoice_03_alpenhorn.pdf", "modern", "Alpenhorn Logistics GmbH",
           ["Bergstrasse 12", "80331 Muenchen, Germany"], "Seeblick Hotels AG",
           ["Seestrasse 4", "8002 Zuerich, Switzerland"], "AL-2025-0042",
           (2025, 3, 12), (2025, 4, 11), "EUR", D("19"),
           [("Pallet transport Muenchen-Zuerich", D(6), D("480.00")),
            ("Customs handling", D(1), D("215.50")),
            ("Storage (pallet-week)", D(24), D("12.75"))]),
    Sample("invoice_04_verdant.pdf", "modern", "Verdant Digital OU",
           ["Tamme tee 7", "10115 Tallinn, Estonia"], "Nordlicht Studios",
           ["Kirkegata 21", "0153 Oslo, Norway"], "VD-0317",
           (2025, 6, 2), (2025, 7, 2), "EUR", D("20"),
           [("Cloud hosting (month)", D(3), D("189.00")),
            ("Security audit", D(1), D("2250.00")),
            ("Support hours", D(14), D("65.00"))]),
    Sample("invoice_05_harbourlight.pdf", "compact", "Harbourlight Consulting LLP",
           ["9 Quayside", "Bristol BS1 4RB"], "Ashdown & Pike Ltd",
           ["Unit 3, Mill Court", "Leeds LS2 8AA"], "HC/25/117",
           (2025, 3, 15), (2025, 4, 14), "GBP", D("20"),
           [("Strategy workshop (day)", D(3), D("850.00")),
            ("Process audit report", D(1), D("1400.00")),
            ("Travel expenses", D(1), D("212.60"))]),
    Sample("invoice_06_quillon.pdf", "compact", "Quillon Print Works",
           ["Unit 8, Press Yard", "Manchester M4 5BA"], "Fernbank Dental Group",
           ["27 Park Row", "Nottingham NG1 6GR"], "QPW-0954",
           (2025, 4, 22), (2025, 5, 22), "GBP", D("20"),
           [("A5 flyers (pack)", D(10), D("42.50")),
            ("Business cards (box of 500)", D(4), D("38.00")),
            ("Roll-up banner", D(2), D("285.00"))],
           printed_subtotal=D("1247.00"), printed_total=D("1500.00"), broken=True),
]


# ------------------------------------------------------------------ formatting
def _tax(s: Sample, subtotal: Decimal) -> Decimal:
    return (subtotal * s.tax_rate / 100).quantize(CENT, ROUND_HALF_UP)


def _fmt(s: Sample, x: Decimal) -> str:
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}[s.currency]
    txt = f"{x:,.2f}"
    if s.layout == "modern":                       # European number format
        txt = txt.replace(",", "_").replace(".", ",").replace("_", ".")
    return sym + txt


def _qty(s: Sample, q: Decimal) -> str:
    t = f"{q:f}".rstrip("0").rstrip(".") if "." in f"{q:f}" else f"{q:f}"
    return t.replace(".", ",") if s.layout == "modern" else t


def _pct(rate: Decimal) -> str:
    return f"{rate:f}".rstrip("0").rstrip(".")


def _date(s: Sample, t: tuple[int, int, int]) -> str:
    from datetime import date
    d = date(*t)
    if s.layout == "classic":
        return d.isoformat()
    if s.layout == "modern":
        return f"{d.day:02d} {d.strftime('%B %Y')}"
    return d.strftime("%d/%m/%Y")


def _totals(s: Sample) -> tuple[Decimal, Decimal, Decimal]:
    sub = s.printed_subtotal if s.printed_subtotal is not None else s.subtotal
    tax = _tax(s, sub)
    total = s.printed_total if s.printed_total is not None else sub + tax
    return sub, tax, total


# -------------------------------------------------------------------- layouts
def _classic(c: canvas.Canvas, s: Sample) -> None:
    w, h = A4
    sub, tax, total = _totals(s)
    y = h - 60
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, y, s.vendor)
    c.setFont("Helvetica", 9)
    for a in s.vendor_addr:
        y -= 13
        c.drawString(50, y, a)
    y -= 40
    c.setFont("Helvetica-Bold", 28)
    c.drawString(50, y, "INVOICE")
    c.setFont("Helvetica", 10)
    for t in (f"Invoice No: {s.number}", f"Date: {_date(s, s.issued)}",
              f"Due Date: {_date(s, s.due)}", f"Currency: {s.currency}"):
        y -= 16
        c.drawString(50, y, t)
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Bill To:")
    c.setFont("Helvetica", 10)
    for t in [s.customer, *s.customer_addr]:
        y -= 14
        c.drawString(50, y, t)
    y -= 36
    c.setFillColor(colors.HexColor("#EEEEEE"))
    c.rect(45, y - 5, w - 90, 18, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Description")
    for x, t in ((330, "Qty"), (430, "Unit Price"), (540, "Amount")):
        c.drawRightString(x, y, t)
    c.setFont("Helvetica", 10)
    for desc, q, p in s.items:
        y -= 20
        c.drawString(50, y, desc)
        c.drawRightString(330, y, _qty(s, q))
        c.drawRightString(430, y, _fmt(s, p))
        c.drawRightString(540, y, _fmt(s, q * p))
    y -= 14
    c.line(330, y, 540, y)
    for label, val, bold in ((f"Subtotal:", sub, False), (f"Tax ({_pct(s.tax_rate)}%):", tax, False),
                             ("Total Due:", total, True)):
        y -= 18
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(380, y, label)
        c.drawRightString(540, y, _fmt(s, val))
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 50, "Payment within 30 days. Sample document - fictional company, generated by docflow.")


def _modern(c: canvas.Canvas, s: Sample) -> None:
    w, h = A4
    sub, tax, total = _totals(s)
    c.setFillColor(colors.HexColor("#0B6E4F"))
    c.rect(0, h - 90, w, 90, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, h - 52, s.vendor)
    c.setFillColor(colors.HexColor("#222222"))
    y = h - 130
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Invoice # {s.number}")
    c.setFont("Helvetica", 10)
    for t in (f"Issued: {_date(s, s.issued)}", f"Payment due: {_date(s, s.due)}"):
        y -= 16
        c.drawString(40, y, t)
    y -= 32
    c.setFillColor(colors.HexColor("#0B6E4F"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Billed to")
    c.setFillColor(colors.HexColor("#222222"))
    c.setFont("Helvetica", 10)
    for t in [s.customer, *s.customer_addr]:
        y -= 14
        c.drawString(40, y, t)
    y -= 36
    c.setStrokeColor(colors.HexColor("#0B6E4F"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Item")
    for x, t in ((340, "Quantity"), (440, "Rate"), (550, "Total")):
        c.drawRightString(x, y, t)
    c.line(40, y - 6, 555, y - 6)
    c.setFont("Helvetica", 10)
    for desc, q, p in s.items:
        y -= 22
        c.drawString(40, y, desc)
        c.drawRightString(340, y, _qty(s, q))
        c.drawRightString(440, y, _fmt(s, p))
        c.drawRightString(550, y, _fmt(s, q * p))
    y -= 16
    c.line(340, y, 555, y)
    for label, val, bold in (("Net amount:", sub, False), (f"VAT ({_pct(s.tax_rate)}%):", tax, False),
                             ("Amount due:", total, True)):
        y -= 20
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(380, y, label)
        c.drawRightString(550, y, _fmt(s, val))
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Sample document - fictional company, generated by docflow.")


def _compact(c: canvas.Canvas, s: Sample) -> None:
    w, h = A4
    sub, tax, total = _totals(s)
    y = h - 50
    c.setFont("Courier-Bold", 13)
    c.drawString(40, y, "TAX INVOICE")
    y -= 24
    c.setFont("Times-Bold", 15)
    c.drawString(40, y, s.vendor)
    c.setFont("Times-Roman", 10)
    for a in s.vendor_addr:
        y -= 12
        c.drawString(40, y, a)
    y -= 26
    for t in (f"Invoice Number: {s.number}", f"Invoice Date: {_date(s, s.issued)}",
              f"Due By: {_date(s, s.due)}", f"Customer: {s.customer}"):
        y -= 14
        c.drawString(40, y, t)
    for a in s.customer_addr:
        y -= 12
        c.drawString(100, y, a)
    y -= 30
    c.setFont("Times-Bold", 10)
    c.drawString(40, y, "Description")
    c.drawString(330, y, "Qty x Unit")
    c.drawRightString(550, y, "Amount")
    c.line(40, y - 4, 555, y - 4)
    c.setFont("Times-Roman", 10)
    for desc, q, p in s.items:
        y -= 18
        c.drawString(40, y, desc)
        c.drawString(330, y, f"{_qty(s, q)} x {_fmt(s, p)}")
        c.drawRightString(550, y, _fmt(s, q * p))
    y -= 14
    c.line(380, y, 555, y)
    for label, val, bold in (("Net total:", sub, False), (f"VAT ({_pct(s.tax_rate)}%):", tax, False),
                             ("Gross total:", total, True)):
        y -= 16
        c.setFont("Times-Bold" if bold else "Times-Roman", 11)
        c.drawString(380, y, label)
        c.drawRightString(550, y, _fmt(s, val))
    c.setFont("Times-Italic", 8)
    c.drawString(40, 40, "Sample document - fictional company, generated by docflow.")


RENDERERS = {"classic": _classic, "modern": _modern, "compact": _compact}


def generate_samples(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for s in SAMPLES:
        path = folder / s.filename
        c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
        c.setTitle(f"Invoice {s.number}")
        RENDERERS[s.layout](c, s)
        c.showPage()
        c.save()
        out.append(path)
    return out
