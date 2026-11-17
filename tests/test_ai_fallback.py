"""AI fallback tests use a fake client: no network, no API key."""
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from reportlab.pdfgen import canvas

from docflow import ai as ai_mod
from docflow.ai import ClaudeExtractor, get_ai_extractor
from docflow.extract import extract_invoice
from docflow.pipeline import process
from docflow.validate import validate

TODAY = date(2026, 1, 1)


class FakeMessages:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=ai_mod._result_model()(**self.payload))


class FakeClient:
    def __init__(self, payload):
        self.messages = FakeMessages(payload)


@pytest.fixture
def odd_pdf(tmp_path):
    """An invoice in a layout the config knows nothing about."""
    p = tmp_path / "in" / "odd.pdf"
    p.parent.mkdir()
    c = canvas.Canvas(str(p))
    for i, t in enumerate(["Rechnung fuer Beispiel GmbH", "Nr 77 vom 3 Mai 2025",
                           "2 x Widget a 50.00 = 100.00", "Summe 100.00 + 19.00 MwSt = 119.00"]):
        c.drawString(60, 780 - 20 * i, t)
    c.save()
    return p.parent


GOOD = dict(invoice_number="77", invoice_date="2025-05-03", vendor="Beispiel GmbH",
            customer="Kunde AG", currency="eur", subtotal=100.0, tax=19.0, total=119.0,
            line_items=[dict(description="Widget", qty=2, unit_price=50.0, amount=100.0)])


def test_without_ai_the_unknown_layout_goes_to_review(odd_pdf, cfg):
    inv = process(odd_pdf, cfg, ai=None, today=TODAY)[0]
    assert inv.layout is None and inv.needs_review
    assert {"missing_field", "no_line_items"} <= {i.code for i in inv.issues}


def test_fake_client_fills_missing_fields_as_medium_confidence(odd_pdf, cfg):
    client = FakeClient(GOOD)
    inv = validate(extract_invoice(next(odd_pdf.glob("*.pdf")), cfg, ClaudeExtractor(client=client)),
                   cfg, TODAY)
    assert inv.value("invoice_number") == "77"
    assert inv.value("currency") == "EUR"
    assert inv.value("total") == D("119.0") and inv.value("invoice_date") == date(2025, 5, 3)
    assert inv.fields["total"].source == "ai" and inv.fields["total"].confidence == "medium"
    assert len(inv.line_items) == 1 and inv.line_items[0].source == "ai"
    assert not inv.needs_review                     
    assert "unknown_layout" in {i.code for i in inv.issues}


def test_request_shape_uses_structured_output_and_configured_model(odd_pdf, cfg, monkeypatch):
    monkeypatch.delenv("DOCFLOW_MODEL", raising=False)
    client = FakeClient(GOOD)
    extract_invoice(next(odd_pdf.glob("*.pdf")), cfg, ClaudeExtractor(client=client))
    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_format"].__name__ == "AIResult"
    assert "Nr 77 vom 3 Mai 2025" in call["messages"][0]["content"]


def test_model_comes_from_env(monkeypatch):
    monkeypatch.setenv("DOCFLOW_MODEL", "my-model")
    assert ClaudeExtractor(client=object()).model == "my-model"


def test_ai_values_still_go_through_validation(odd_pdf, cfg):
    bad = dict(GOOD, total=500.0)                      # arithmetic does not add up
    inv = validate(extract_invoice(next(odd_pdf.glob("*.pdf")), cfg, ClaudeExtractor(client=FakeClient(bad))),
                   cfg, TODAY)
    assert inv.needs_review and "total_math" in {i.code for i in inv.issues}


def test_ai_failure_never_breaks_the_batch(odd_pdf, cfg):
    class Boom:
        def extract(self, text, fields):
            raise RuntimeError("api down")
    inv = validate(extract_invoice(next(odd_pdf.glob("*.pdf")), cfg, Boom()), cfg, TODAY)
    assert inv.needs_review and "ai_failed" in {i.code for i in inv.issues}


def test_ai_is_not_called_when_rules_extract_everything(sample_dir, cfg):
    class Spy:
        calls = 0
        def extract(self, text, fields):
            Spy.calls += 1
            return {}
    good = [p for p in sample_dir.glob("*.pdf") if "quillon" not in p.name]
    for p in good:
        extract_invoice(p, cfg, Spy())
    assert Spy.calls == 0


def test_no_key_means_no_extractor():
    assert get_ai_extractor({}) is None
    assert get_ai_extractor({"ANTHROPIC_API_KEY": ""}) is None


def test_key_enables_extractor_with_default_or_custom_model():
    assert get_ai_extractor({"ANTHROPIC_API_KEY": "sk-test"}).model == "claude-haiku-5-5"
    assert get_ai_extractor({"ANTHROPIC_API_KEY": "sk-test", "DOCFLOW_MODEL": "x"}).model == "x"
