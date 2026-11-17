from datetime import date
from decimal import Decimal as D

from docflow.models import HIGH, FieldValue, Invoice, LineItem
from docflow.validate import validate

TODAY = date(2026, 1, 1)


def make(**over) -> Invoice:
    f = dict(invoice_number="A-1", invoice_date=date(2025, 5, 1), due_date=date(2025, 6, 1),
             vendor="V Ltd", customer="C Ltd", currency="USD",
             subtotal=D("100.00"), tax=D("10.00"), total=D("110.00"))
    f.update(over)
    inv = Invoice("t.pdf", "classic")
    for k, v in f.items():
        inv.fields[k] = FieldValue(v, HIGH if v is not None else "low", "rule")
    inv.line_items = [LineItem("a", D(2), D("30.00"), D("60.00")),
                      LineItem("b", D(1), D("40.00"), D("40.00"))]
    inv.line_items_confidence = HIGH
    return inv


def codes(inv):
    return {i.code for i in inv.issues}


def test_clean_invoice_passes():
    inv = validate(make(), today=TODAY)
    assert inv.issues == [] and not inv.needs_review


def test_missing_required_field():
    inv = validate(make(customer=None), today=TODAY)
    assert "missing_field" in codes(inv) and inv.needs_review


def test_missing_optional_fields_are_fine():
    inv = make(due_date=None, tax=None, total=D("100.00"))
    inv.fields["due_date"].confidence = inv.fields["tax"].confidence = "n/a"
    assert not validate(inv, today=TODAY).needs_review


def test_line_items_must_sum_to_subtotal():
    inv = validate(make(subtotal=D("120.00"), total=D("130.00")), today=TODAY)
    assert "lines_vs_subtotal" in codes(inv)
    assert inv.fields["subtotal"].confidence == "low"      # implicated fields are downgraded
    assert inv.line_items_confidence == "low"


def test_subtotal_plus_tax_must_equal_total():
    inv = validate(make(total=D("111.00")), today=TODAY)
    assert codes(inv) == {"total_math"}
    assert {"subtotal", "tax", "total"} <= set(inv.low_confidence_fields)


def test_rounding_tolerance_of_one_cent():
    assert not validate(make(total=D("110.01")), today=TODAY).needs_review
    assert validate(make(total=D("110.02")), today=TODAY).needs_review


def test_line_arithmetic():
    inv = make()
    inv.line_items[0].amount = D("61.00")
    inv.fields["subtotal"].value, inv.fields["total"].value = D("101.00"), D("111.00")
    assert "line_math" in codes(validate(inv, today=TODAY))


def test_no_line_items_is_an_error():
    inv = make()
    inv.line_items, inv.line_items_confidence = [], "low"
    assert "no_line_items" in codes(validate(inv, today=TODAY))


def test_future_invoice_date():
    assert "date_future" in codes(validate(make(invoice_date=date(2026, 3, 1),
                                                due_date=date(2026, 4, 1)), today=TODAY))


def test_implausibly_old_date():
    assert "date_old" in codes(validate(make(invoice_date=date(1985, 1, 1), due_date=None),
                                        today=TODAY))


def test_due_date_before_invoice_date():
    assert "due_before_issue" in codes(validate(make(due_date=date(2025, 4, 1)), today=TODAY))


def test_low_confidence_field_alone_routes_to_review():
    inv = make()
    inv.fields["vendor"].confidence = "low"
    assert validate(inv, today=TODAY).needs_review
