"""Rule-based extraction driven by config/layouts.yaml (pdfplumber for text)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .models import (DATE_FIELDS, HIGH, LOW, MONEY_FIELDS, NA, REQUIRED_FIELDS,
                     SCALAR_FIELDS, FieldValue, Invoice, Issue, LineItem)

RX = re.I | re.M


@dataclass
class Config:
    layouts: dict[str, dict] = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)

    @property
    def amount_tolerance(self) -> Decimal:
        return Decimal(str(self.defaults.get("amount_tolerance", "0.01")))


def load_config(path: str | Path) -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Config(layouts=data.get("layouts", {}), defaults=data.get("defaults", {}))


def read_pdf_text(path: str | Path) -> str:
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def parse_money(raw: str | None, decimal: str = ".") -> Decimal | None:
    if raw is None:
        return None
    s = re.sub(r"[^\d,.\-]", "", raw)
    if not re.search(r"\d", s):
        return None
    s = s.replace(".", "").replace(",", ".") if decimal == "," else s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date(raw: str | None, formats: list[str]) -> date | None:
    if raw is None:
        return None
    raw = raw.strip()
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def detect_layout(text: str, cfg: Config) -> str | None:
    for name, rule in cfg.layouts.items():
        pats = rule.get("detect", [])
        if pats and all(re.search(p, text, RX) for p in pats):
            return name
    return None


def _resolve(spec: dict, text: str, lines: list[str]) -> str | None:
    if "regex" in spec:
        m = re.search(spec["regex"], text, RX)
        return m.group(1).strip() if m else None
    if "line" in spec:
        n = int(spec["line"]) - 1
        return lines[n] if 0 <= n < len(lines) else None
    if "after" in spec:
        off = int(spec.get("offset", 1))
        for i, ln in enumerate(lines):
            if re.search(spec["after"], ln, RX):
                return lines[i + off] if i + off < len(lines) else None
    return None


def extract_text(text: str, source_file: str, cfg: Config) -> Invoice:
    """Run the layout rules over already-extracted PDF text."""
    inv = Invoice(source_file=source_file)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name = detect_layout(text, cfg)
    inv.layout = name
    rule = cfg.layouts.get(name or "", {})
    decimal = rule.get("decimal", ".")
    formats = rule.get("date_formats", ["%Y-%m-%d"])
    specs = rule.get("fields", {})

    for fname in SCALAR_FIELDS:
        raw = _resolve(specs[fname], text, lines) if fname in specs else None
        inv.fields[fname] = _make_field(fname, raw, decimal, formats)

    # currency: explicit rule first, else a known symbol found in the text
    if inv.fields["currency"].value is None:
        for sym, code in rule.get("currency_symbols", {}).items():
            if sym in text:
                inv.fields["currency"] = FieldValue(code, HIGH, "rule", sym)
                break
    if inv.fields["currency"].value:
        inv.fields["currency"].value = str(inv.fields["currency"].value).upper()

    if name:
        _extract_line_items(inv, lines, rule, decimal)
    return inv


def _make_field(fname: str, raw: str | None, decimal: str, formats: list[str]) -> FieldValue:
    optional = fname not in REQUIRED_FIELDS
    if raw is None:
        return FieldValue(None, NA if optional else LOW, "missing")
    if fname in MONEY_FIELDS:
        val: Any = parse_money(raw, decimal)
    elif fname in DATE_FIELDS:
        val = parse_date(raw, formats)
    else:
        val = raw
    if val is None:                       # matched, but unreadable -> low confidence
        return FieldValue(None, LOW, "rule", raw)
    return FieldValue(val, HIGH, "rule", raw)


def _extract_line_items(inv: Invoice, lines: list[str], rule: dict, decimal: str) -> None:
    spec = rule.get("line_items")
    if not spec:
        return
    start = end = None
    for i, ln in enumerate(lines):
        if start is None and re.search(spec["start"], ln, RX):
            start = i + 1
        elif start is not None and re.search(spec["end"], ln, RX):
            end = i
            break
    if start is None:
        return
    unparsed = []
    for ln in lines[start:end]:
        m = re.search(spec["row"], ln)
        if not m:
            unparsed.append(ln)
            continue
        g = m.groupdict()
        item = LineItem(g["description"].strip(), parse_money(g["qty"], decimal),
                        parse_money(g["unit_price"], decimal), parse_money(g["amount"], decimal))
        if None in (item.qty, item.unit_price, item.amount):
            item.confidence = LOW
        inv.line_items.append(item)
    if unparsed:
        inv.issues.append(Issue("line_unparsed",
                                f"{len(unparsed)} table row(s) did not match the layout: {unparsed[0]!r}",
                                "error", ["line_items"]))
    inv.line_items_confidence = HIGH if inv.line_items else LOW
    if any(li.confidence == LOW for li in inv.line_items):
        inv.line_items_confidence = LOW


def missing_fields(inv: Invoice) -> list[str]:
    """Fields the rules could not extract (candidates for the AI fallback)."""
    out = [n for n, f in inv.fields.items() if f.value is None]
    if not inv.line_items:
        out.append("line_items")
    return out


def extract_invoice(path: str | Path, cfg: Config, ai: Any | None = None) -> Invoice:
    """PDF -> Invoice. `ai` is an optional AIExtractor used for missing fields only."""
    path = Path(path)
    try:
        text = read_pdf_text(path)
    except Exception as exc:  # corrupt / encrypted / not a PDF
        inv = Invoice(source_file=path.name)
        inv.issues.append(Issue("unreadable", f"Could not read PDF: {exc}", "error"))
        for n in SCALAR_FIELDS:
            inv.fields[n] = FieldValue(None, NA if n not in REQUIRED_FIELDS else LOW, "missing")
        return inv
    inv = extract_text(text, path.name, cfg)
    if not text.strip():
        inv.issues.append(Issue("no_text", "PDF has no text layer (scanned image?). OCR is not included.", "error"))
    elif inv.layout is None:
        inv.issues.append(Issue("unknown_layout", "No layout in config/layouts.yaml matches this PDF.", "warning"))
    if ai is not None and text.strip():
        from .ai import apply_ai_fallback
        apply_ai_fallback(inv, text, ai)
    return inv
