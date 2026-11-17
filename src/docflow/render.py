"""Fill the Word template (docxtpl) and write the JSON export."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .models import Invoice

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def money(value, currency: str | None) -> str:
    if value is None:
        return ""
    sym = SYMBOLS.get(currency or "", "")
    return f"{sym}{value:,.2f}" if sym else f"{value:,.2f} {currency or ''}".strip()


def docx_context(inv: Invoice) -> dict:
    cur = inv.value("currency")
    v = inv.value
    return {
        "source_file": inv.source_file,
        "layout": inv.layout or "unknown",
        "invoice_number": v("invoice_number") or "(missing)",
        "invoice_date": v("invoice_date").isoformat() if v("invoice_date") else "",
        "due_date": v("due_date").isoformat() if v("due_date") else "",
        "vendor": v("vendor") or "(missing)",
        "customer": v("customer") or "(missing)",
        "currency": cur or "",
        "subtotal": money(v("subtotal"), cur),
        "tax": money(v("tax"), cur),
        "total": money(v("total"), cur),
        "needs_review": inv.needs_review,
        "review_notes": [i.message for i in inv.errors]
        + [f"Low confidence: {n}" for n in inv.low_confidence_fields
           if n not in {f for i in inv.errors for f in i.fields}],
        "line_items": [
            {"description": li.description,
             "qty": f"{li.qty:,.2f}".rstrip("0").rstrip(".") if li.qty is not None else "",
             "unit_price": money(li.unit_price, cur),
             "amount": money(li.amount, cur)}
            for li in inv.line_items
        ],
    }


def safe_name(inv: Invoice) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(inv.source_file).stem)


def write_docx(inv: Invoice, template: str | Path, out_dir: str | Path) -> Path:
    from docxtpl import DocxTemplate
    tpl = DocxTemplate(str(template))
    tpl.render(docx_context(inv))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe_name(inv)}.docx"
    tpl.save(str(path))
    return path


def write_json(invoices: list[Invoice], path: str | Path) -> Path:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "docflow_version": __version__,
        "summary": {
            "total": len(invoices),
            "ok": sum(not i.needs_review for i in invoices),
            "needs_review": sum(i.needs_review for i in invoices),
        },
        "invoices": [i.to_json() for i in invoices],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
