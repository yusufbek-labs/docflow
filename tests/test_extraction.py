from datetime import date
from decimal import Decimal as D

import pytest

# file -> (layout, number, vendor, customer, currency, issue date, due date,
#          subtotal, tax, total, number of line items)
EXPECTED = {
    "invoice_01_brightwave.pdf": ("classic", "INV-1001", "Brightwave Studios Ltd",
                                  "Marlow & Finch Retail Inc.", "USD", date(2025, 3, 4),
                                  date(2025, 4, 3), "3780.00", "302.40", "4082.40", 3),
    "invoice_02_copperline.pdf": ("classic", "INV-20458", "Copperline Supply Co.",
                                  "Tidewater Bakery LLC", "USD", date(2025, 5, 19),
                                  date(2025, 6, 18), "922.50", "59.96", "982.46", 3),
    "invoice_03_alpenhorn.pdf": ("modern", "AL-2025-0042", "Alpenhorn Logistics GmbH",
                                 "Seeblick Hotels AG", "EUR", date(2025, 3, 12),
                                 date(2025, 4, 11), "3401.50", "646.29", "4047.79", 3),
    "invoice_04_verdant.pdf": ("modern", "VD-0317", "Verdant Digital OU",
                               "Nordlicht Studios", "EUR", date(2025, 6, 2),
                               date(2025, 7, 2), "3727.00", "745.40", "4472.40", 3),
    "invoice_05_harbourlight.pdf": ("compact", "HC/25/117", "Harbourlight Consulting LLP",
                                    "Ashdown & Pike Ltd", "GBP", date(2025, 3, 15),
                                    date(2025, 4, 14), "4162.60", "832.52", "4995.12", 3),
}


@pytest.mark.parametrize("fname", sorted(EXPECTED))
def test_fields_extracted_per_layout(invoices, fname):
    layout, num, vendor, cust, cur, d1, d2, sub, tax, total, n = EXPECTED[fname]
    inv = invoices[fname]
    assert inv.layout == layout
    assert inv.value("invoice_number") == num
    assert inv.value("vendor") == vendor
    assert inv.value("customer") == cust
    assert inv.value("currency") == cur
    assert inv.value("invoice_date") == d1
    assert inv.value("due_date") == d2
    assert inv.value("subtotal") == D(sub)
    assert inv.value("tax") == D(tax)
    assert inv.value("total") == D(total)
    assert len(inv.line_items) == n
    assert all(f.confidence == "high" for f in inv.fields.values())
    assert not inv.needs_review


def test_three_distinct_layouts_are_covered(invoices):
    assert {i.layout for i in invoices.values()} == {"classic", "modern", "compact"}


def test_european_number_format_and_line_items(invoices):
    items = invoices["invoice_03_alpenhorn.pdf"].line_items
    assert [(li.description, li.qty, li.unit_price, li.amount) for li in items] == [
        ("Pallet transport Muenchen-Zuerich", D(6), D("480.00"), D("2880.00")),
        ("Customs handling", D(1), D("215.50"), D("215.50")),
        ("Storage (pallet-week)", D(24), D("12.75"), D("306.00")),
    ]


def test_qty_x_unit_column_layout(invoices):
    li = invoices["invoice_05_harbourlight.pdf"].line_items[0]
    assert (li.description, li.qty, li.unit_price, li.amount) == (
        "Strategy workshop (day)", D(3), D("850.00"), D("2550.00"))


def test_description_with_digits_and_quotes(invoices):
    li = invoices["invoice_02_copperline.pdf"].line_items[0]
    assert li.description == 'Copper fittings 3/4" (box)'
    assert li.qty == D(20)


def test_unknown_layout_yields_missing_fields_not_guesses(cfg):
    from docflow.extract import extract_text
    inv = extract_text("Some random document\nwith no invoice structure", "x.pdf", cfg)
    assert inv.layout is None
    assert inv.value("total") is None and inv.line_items == []
    assert inv.needs_review
