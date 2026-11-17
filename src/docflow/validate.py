"""Validation rules. Failing checks add Issues and downgrade the involved fields to LOW."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .extract import Config
from .models import LOW, NA, REQUIRED_FIELDS, Invoice, Issue

MIN_PLAUSIBLE_DATE = date(2000, 1, 1)


def validate(inv: Invoice, cfg: Config | None = None, today: date | None = None) -> Invoice:
    tol = cfg.amount_tolerance if cfg else Decimal("0.01")
    today = today or date.today()
    new: list[Issue] = []

    # 1. required fields -------------------------------------------------------
    for name in REQUIRED_FIELDS:
        if inv.value(name) in (None, ""):
            new.append(Issue("missing_field", f"Required field '{name}' was not found", "error", [name]))
    if not inv.line_items:
        new.append(Issue("no_line_items", "No line items were extracted", "error", ["line_items"]))

    # 2. line arithmetic -------------------------------------------------------
    for n, li in enumerate(inv.line_items, 1):
        if None in (li.qty, li.unit_price, li.amount):
            new.append(Issue("line_unreadable", f"Line {n} has an unreadable number", "error", ["line_items"]))
        elif abs(li.qty * li.unit_price - li.amount) > tol:
            new.append(Issue("line_math",
                             f"Line {n} '{li.description}': {li.qty} x {li.unit_price} = "
                             f"{li.qty * li.unit_price}, but amount is {li.amount}",
                             "error", ["line_items"]))

    subtotal, tax, total = inv.value("subtotal"), inv.value("tax"), inv.value("total")

    # 3. line items sum to subtotal -----------------------------------------------
    amounts = [li.amount for li in inv.line_items if li.amount is not None]
    if amounts and subtotal is not None:
        s = sum(amounts, Decimal(0))
        if abs(s - subtotal) > tol:
            new.append(Issue("lines_vs_subtotal",
                             f"Line items add up to {s:,.2f} but the subtotal says {subtotal:,.2f}",
                             "error", ["line_items", "subtotal"]))

    # 4. subtotal + tax = total -------------------------------------------------------
    if subtotal is not None and total is not None:
        t = tax if tax is not None else Decimal(0)
        if abs(subtotal + t - total) > tol:
            new.append(Issue("total_math",
                             f"Subtotal {subtotal:,.2f} + tax {t:,.2f} = {subtotal + t:,.2f}, "
                             f"but the total says {total:,.2f}",
                             "error", ["subtotal", "tax", "total"]))

    # 5. date sanity ------------------------------------------------------------------
    idate, ddate = inv.value("invoice_date"), inv.value("due_date")
    if idate is not None:
        if idate > today:
            new.append(Issue("date_future", f"Invoice date {idate} is in the future", "error", ["invoice_date"]))
        elif idate < MIN_PLAUSIBLE_DATE:
            new.append(Issue("date_old", f"Invoice date {idate} is implausibly old", "error", ["invoice_date"]))
    if idate is not None and ddate is not None and ddate < idate:
        new.append(Issue("due_before_issue", f"Due date {ddate} is before invoice date {idate}",
                         "error", ["due_date", "invoice_date"]))

    # 6. negative / zero money ------------------------------------------------------------
    if total is not None and total <= 0:
        new.append(Issue("total_not_positive", f"Total {total} is not positive", "error", ["total"]))

    inv.issues.extend(new)
    for issue in new:                       # downgrade confidence of implicated fields
        for name in issue.fields:
            fv = inv.fields.get(name)
            if fv is not None and fv.confidence != NA:
                fv.confidence = LOW
            if name == "line_items":
                inv.line_items_confidence = LOW
    return inv
