"""Excel summary: Invoices, Line items and Needs review sheets."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import Invoice

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
OK_FILL = PatternFill("solid", fgColor="E2F0D9")
REVIEW_FILL = PatternFill("solid", fgColor="FCE4D6")
THIN = Side(style="thin", color="BFBFBF")
MONEY = "#,##0.00"
DATE = "yyyy-mm-dd"
RANK = {"high": 3, "medium": 2, "n/a": 3, "low": 1}


def _header(ws, headers: list[str], widths: list[int]) -> None:
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(bottom=THIN)
    ws.row_dimensions[1].height = 24
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def min_confidence(inv: Invoice) -> str:
    levels = [f.confidence for f in inv.fields.values() if f.confidence != "n/a"]
    levels.append(inv.line_items_confidence)
    return min(levels, key=lambda c: RANK[c])


def write_workbook(invoices: list[Invoice], path: str | Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"
    cols = ["Source file", "Layout", "Invoice #", "Invoice date", "Due date", "Vendor",
            "Customer", "Currency", "Subtotal", "Tax", "Total", "Lowest confidence", "Status"]
    _header(ws, cols, [30, 10, 16, 13, 13, 28, 28, 9, 13, 12, 13, 12, 14])
    for inv in invoices:
        v = inv.value
        ws.append([inv.source_file, inv.layout or "unknown", v("invoice_number"),
                   v("invoice_date"), v("due_date"), v("vendor"), v("customer"),
                   v("currency"), _num(v("subtotal")), _num(v("tax")), _num(v("total")),
                   min_confidence(inv), inv.status])
        r = ws.max_row
        for col in (4, 5):
            ws.cell(r, col).number_format = DATE
        for col in (9, 10, 11):
            ws.cell(r, col).number_format = MONEY
        ws.cell(r, 13).fill = REVIEW_FILL if inv.needs_review else OK_FILL
        ws.cell(r, 13).font = Font(bold=True)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(ws.max_row, 1)}"

    li = wb.create_sheet("Line items")
    _header(li, ["Invoice #", "Source file", "Line", "Description", "Qty", "Unit price",
                 "Amount", "Currency"], [16, 30, 6, 44, 9, 13, 13, 9])
    for inv in invoices:
        for n, item in enumerate(inv.line_items, 1):
            li.append([inv.value("invoice_number"), inv.source_file, n, item.description,
                       _num(item.qty), _num(item.unit_price), _num(item.amount),
                       inv.value("currency")])
            r = li.max_row
            li.cell(r, 5).number_format = "#,##0.##"
            li.cell(r, 6).number_format = MONEY
            li.cell(r, 7).number_format = MONEY
    li.auto_filter.ref = f"A1:H{max(li.max_row, 1)}"

    rv = wb.create_sheet("Needs review")
    _header(rv, ["Source file", "Invoice #", "Problem", "Fields", "Detail"],
            [30, 16, 22, 28, 90])
    for inv in invoices:
        if not inv.needs_review:
            continue
        for issue in inv.errors:
            rv.append([inv.source_file, inv.value("invoice_number"), issue.code,
                       ", ".join(issue.fields), issue.message])
        covered = {f for i in inv.errors for f in i.fields}
        for name in inv.low_confidence_fields:
            if name not in covered:
                rv.append([inv.source_file, inv.value("invoice_number"), "low_confidence",
                           name, f"'{name}' could not be extracted with enough confidence"])
    for row in rv.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    rv.auto_filter.ref = f"A1:E{max(rv.max_row, 1)}"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _num(x):
    return float(x) if x is not None else None
