"""Optional AI fallback.

Nothing in this module runs unless ANTHROPIC_API_KEY is set. When it is, only the
fields the rules could not extract are requested, and only that one invoice's
text is sent to the Anthropic API. Everything extracted this way is marked
confidence="medium", source="ai" and still goes through validation.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol

from .extract import missing_fields
from .models import DATE_FIELDS, MEDIUM, MONEY_FIELDS, FieldValue, Invoice, Issue, LineItem

DEFAULT_MODEL = "claude-haiku-5-5"

SYSTEM_PROMPT = (
    "You extract data from the text of a single invoice. Return only values that are "
    "literally present in the text. Use null for anything that is not present - never "
    "guess, never compute a value that is not printed. Dates are ISO YYYY-MM-DD. "
    "Money values are plain numbers without currency symbols or thousands separators. "
    "currency is a 3-letter ISO code."
)


class AIExtractor(Protocol):
    """Anything that can fill in missing invoice fields from raw text."""

    def extract(self, text: str, fields: list[str]) -> dict[str, Any]: ...


@dataclass
class AILine:
    description: str
    qty: float
    unit_price: float
    amount: float


@dataclass
class AIResult:
    """Shape of the structured answer; the stdlib twin of the pydantic model below."""
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    vendor: str | None = None
    customer: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_items: list[AILine] | None = None


class ClaudeExtractor:
    """AIExtractor backed by the `anthropic` SDK (structured output)."""

    def __init__(self, client: Any | None = None, model: str | None = None):
        self.model = model or os.environ.get("DOCFLOW_MODEL") or DEFAULT_MODEL
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError('the "anthropic" package is not installed '
                                   '(pip install "docflow[ai]")') from exc
            self._client = anthropic.Anthropic()      # reads ANTHROPIC_API_KEY
        return self._client

    def extract(self, text: str, fields: list[str]) -> dict[str, Any]:
        wanted = ", ".join(fields)
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content":
                       f"Extract these fields: {wanted}.\n\n<invoice_text>\n{text}\n</invoice_text>"}],
            output_format=_result_model(),
        )
        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            return {}
        data = asdict(parsed) if is_dataclass(parsed) else parsed.model_dump()
        return {k: v for k, v in data.items() if k in fields and v is not None}


def _result_model():
    """The SDK's structured output needs pydantic; without it fall back to AIResult."""
    try:
        return _pydantic_result_model()
    except ImportError:
        return AIResult


def _pydantic_result_model():
    from pydantic import BaseModel

    class AILine(BaseModel):
        description: str
        qty: float
        unit_price: float
        amount: float

    class AIResult(BaseModel):
        invoice_number: str | None = None
        invoice_date: str | None = None
        due_date: str | None = None
        vendor: str | None = None
        customer: str | None = None
        currency: str | None = None
        subtotal: float | None = None
        tax: float | None = None
        total: float | None = None
        line_items: list[AILine] | None = None

    return AIResult


def get_ai_extractor(env: Mapping[str, str] | None = None) -> ClaudeExtractor | None:
    """Return an extractor only when ANTHROPIC_API_KEY is set; otherwise None (offline)."""
    env = os.environ if env is None else env
    if not env.get("ANTHROPIC_API_KEY"):
        return None
    return ClaudeExtractor(model=env.get("DOCFLOW_MODEL") or DEFAULT_MODEL)


def _dec(v: Any) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def apply_ai_fallback(inv: Invoice, text: str, ai: AIExtractor) -> list[str]:
    wanted = missing_fields(inv)
    if not wanted:
        return []
    try:
        result = ai.extract(text, wanted)
    except Exception as exc:       # an API problem must never break the batch
        inv.issues.append(Issue("ai_failed", f"AI fallback failed: {exc}", "warning"))
        return []
    filled: list[str] = []
    for name in wanted:
        val = result.get(name)
        if val is None:
            continue
        if name == "line_items":
            items = [LineItem(str(d.get("description", "")), _dec(d.get("qty")),
                              _dec(d.get("unit_price")), _dec(d.get("amount")),
                              MEDIUM, "ai") for d in val]
            if items:
                inv.line_items, inv.line_items_confidence = items, MEDIUM
                filled.append(name)
            continue
        if name in MONEY_FIELDS:
            val = _dec(val)
        elif name in DATE_FIELDS:
            try:
                val = date.fromisoformat(str(val))
            except ValueError:
                val = None
        elif name == "currency":
            val = str(val).upper()
        else:
            val = str(val).strip()
        if val in (None, ""):
            continue
        inv.fields[name] = FieldValue(val, MEDIUM, "ai")
        filled.append(name)
    return filled
