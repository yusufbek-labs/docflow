import json

import docx
from openpyxl import load_workbook

from docflow.cli import main

BROKEN = "invoice_06_quillon.pdf"


def test_only_the_broken_invoice_needs_review(invoices):
    review = [n for n, i in invoices.items() if i.needs_review]
    assert review == [BROKEN]
    codes = {i.code for i in invoices[BROKEN].errors}
    assert codes == {"lines_vs_subtotal", "total_math"}
    assert invoices[BROKEN].fields["total"].confidence == "low"


def test_excel_sheets_and_header_format(run_output):
    out, _ = run_output
    wb = load_workbook(out / "invoices.xlsx")
    assert wb.sheetnames == ["Invoices", "Line items", "Needs review"]
    ws = wb["Invoices"]
    assert [c.value for c in ws[1]][:4] == ["Source file", "Layout", "Invoice #", "Invoice date"]
    assert ws["A1"].font.bold and ws["A1"].fill.fgColor.rgb.endswith("1F3864")
    assert ws.freeze_panes == "A2"
    assert ws.column_dimensions["F"].width >= 28


def test_excel_invoices_rows_and_number_formats(run_output):
    out, _ = run_output
    ws = load_workbook(out / "invoices.xlsx")["Invoices"]
    rows = {r[0].value: r for r in ws.iter_rows(min_row=2)}
    assert len(rows) == 6
    r = rows["invoice_01_brightwave.pdf"]
    assert r[2].value == "INV-1001"
    assert r[10].value == 4082.40 and r[10].number_format == "#,##0.00"
    assert r[3].number_format == "yyyy-mm-dd" and r[3].value.year == 2025
    assert r[12].value == "OK"
    assert rows[BROKEN][12].value == "Needs review"


def test_excel_line_items_sheet(run_output):
    out, _ = run_output
    ws = load_workbook(out / "invoices.xlsx")["Line items"]
    assert ws.max_row - 1 == 18                      # 6 invoices x 3 lines
    first = [c.value for c in ws[2]]
    assert first[0] == "INV-1001" and first[3] == "Brand identity package" and first[6] == 2400.0


def test_excel_needs_review_sheet_lists_only_the_broken_invoice(run_output):
    out, _ = run_output
    ws = load_workbook(out / "invoices.xlsx")["Needs review"]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=2)]
    assert rows and all(r[0] == BROKEN for r in rows)
    assert {r[2] for r in rows} == {"lines_vs_subtotal", "total_math"}
    assert any("1,147.00" in r[4] for r in rows)


def test_one_docx_per_invoice_with_filled_values(run_output):
    out, res = run_output
    files = sorted((out / "documents").glob("*.docx"))
    assert len(files) == 6
    d = docx.Document(out / "documents" / "invoice_03_alpenhorn.docx")
    text = "\n".join(p.text for p in d.paragraphs)
    assert "Invoice AL-2025-0042" in text and "Total: €4,047.79" in text
    assert "NEEDS REVIEW" not in text and "{{" not in text and "{%" not in text
    rows = [[c.text for c in r.cells] for r in d.tables[0].rows]
    assert rows[1] == ["Pallet transport Muenchen-Zuerich", "6", "€480.00", "€2,880.00"]
    assert len(rows) == 4                            # header + 3 lines


def test_docx_for_broken_invoice_carries_review_banner(run_output):
    out, _ = run_output
    d = docx.Document(out / "documents" / "invoice_06_quillon.docx")
    text = "\n".join(p.text for p in d.paragraphs)
    assert "NEEDS REVIEW" in text and "1,147.00" in text


def test_json_export(run_output):
    out, _ = run_output
    data = json.loads((out / "invoices.json").read_text(encoding="utf-8"))
    assert data["summary"] == {"total": 6, "ok": 5, "needs_review": 1}
    inv = next(i for i in data["invoices"] if i["source_file"] == BROKEN)
    assert inv["status"] == "Needs review"
    assert inv["fields"]["total"] == {"value": 1500.0, "confidence": "low", "source": "rule"}
    assert inv["issues"][0]["severity"] == "error"


def test_cli_run_and_check_exit_codes(sample_dir, tmp_path, capsys):
    assert main(["run", "--input", str(sample_dir), "--output", str(tmp_path / "o"), "--no-ai"]) == 0
    out = capsys.readouterr().out
    assert "Processed     6" in out and "Needs review  1" in out
    assert (tmp_path / "o" / "invoices.xlsx").exists()
    assert main(["check", "--input", str(sample_dir), "--no-ai"]) == 1      # something needs review


def test_cli_missing_input_folder(tmp_path):
    assert main(["run", "--input", str(tmp_path / "nope"), "--output", str(tmp_path)]) == 2


def test_corrupt_pdf_does_not_stop_the_batch(sample_dir, cfg, tmp_path):
    import shutil
    from docflow.pipeline import process
    d = tmp_path / "in"
    shutil.copytree(sample_dir, d)
    (d / "zz_garbage.pdf").write_bytes(b"not a pdf")
    invs = process(d, cfg)
    assert len(invs) == 7
    bad = invs[-1]
    assert bad.needs_review and bad.errors[0].code == "unreadable"
