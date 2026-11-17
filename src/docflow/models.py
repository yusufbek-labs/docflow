"""Plain data classes shared by every stage of the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

HIGH, MEDIUM, LOW, NA = "high", "medium", "low", "n/a"

SCALAR_FIELDS = [
    "invoice_number", "invoice_date", "due_date", "vendor", "customer",
    "currency", "subtotal", "tax", "total",
]
REQUIRED_FIELDS = [
    "invoice_number", "invoice_date", "vendor", "customer",
    "currency", "subtotal", "total",
]
MONEY_FIELDS = {"subtotal", "tax", "total"}
DATE_FIELDS = {"invoice_date", "due_date"}


@dataclass
class FieldValue:
    """One extracted value plus how much we trust it."""
    value: Any = None
    confidence: str = LOW
    source: str = "missing"      # rule | ai | missing
    raw: str | None = None       # the text the value was parsed from

    def to_json(self) -> dict:
        return {"value": jsonable(self.value), "confidence": self.confidence,
                "source": self.source}


@dataclass
class LineItem:
    description: str
    qty: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    confidence: str = HIGH
    source: str = "rule"

    def to_json(self) -> dict:
        return {"description": self.description, "qty": jsonable(self.qty),
                "unit_price": jsonable(self.unit_price),
                "amount": jsonable(self.amount),
                "confidence": self.confidence, "source": self.source}


@dataclass
class Issue:
    code: str
    message: str
    severity: str = "error"                       # error | warning
    fields: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"code": self.code, "severity": self.severity,
                "message": self.message, "fields": self.fields}


@dataclass
class Invoice:
    source_file: str
    layout: str | None = None
    fields: dict[str, FieldValue] = field(default_factory=dict)
    line_items: list[LineItem] = field(default_factory=list)
    line_items_confidence: str = LOW
    issues: list[Issue] = field(default_factory=list)

    def value(self, name: str) -> Any:
        fv = self.fields.get(name)
        return fv.value if fv else None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def low_confidence_fields(self) -> list[str]:
        names = [n for n, f in self.fields.items() if f.confidence == LOW]
        if self.line_items_confidence == LOW:
            names.append("line_items")
        return names

    @property
    def needs_review(self) -> bool:
        return bool(self.errors or self.low_confidence_fields)

    @property
    def status(self) -> str:
        return "Needs review" if self.needs_review else "OK"

    def to_json(self) -> dict:
        return {
            "source_file": self.source_file,
            "layout": self.layout,
            "status": self.status,
            "fields": {k: v.to_json() for k, v in self.fields.items()},
            "line_items": [li.to_json() for li in self.line_items],
            "issues": [i.to_json() for i in self.issues],
        }


def jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v
