"""Builds templates/invoice.docx (docxtpl / Jinja tags inside a normal Word file).

You rarely need to run this: open the .docx in Word and edit it directly. Keep the
{{ tags }} intact. This script exists so the template is reproducible.
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

OUT = Path(__file__).resolve().parents[1] / "templates" / "invoice.docx"


def main() -> None:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)

    banner = doc.add_paragraph()
    r = banner.add_run("{%p if needs_review %}")
    note = doc.add_paragraph()
    r = note.add_run("NEEDS REVIEW - do not file until checked")
    r.bold, r.font.color.rgb = True, RGBColor(0xC0, 0x39, 0x2B)
    for text in ("{%p for n in review_notes %}", "- {{ n }}", "{%p endfor %}", "{%p endif %}"):
        doc.add_paragraph().add_run(text)

    h = doc.add_paragraph()
    r = h.add_run("Invoice {{ invoice_number }}")
    r.bold, r.font.size = True, Pt(20)
    doc.add_paragraph("Vendor: {{ vendor }}")
    doc.add_paragraph("Customer: {{ customer }}")
    doc.add_paragraph("Invoice date: {{ invoice_date }}    Due date: {{ due_date }}    Currency: {{ currency }}")

    t = doc.add_table(rows=4, cols=4)
    t.style = "Light Grid Accent 1"
    for i, head in enumerate(("Description", "Qty", "Unit price", "Amount")):
        t.cell(0, i).text = head
    t.cell(1, 0).text = "{%tr for li in line_items %}"
    for i, tag in enumerate(("{{ li.description }}", "{{ li.qty }}", "{{ li.unit_price }}", "{{ li.amount }}")):
        t.cell(2, i).text = tag
        if i:
            t.cell(2, i).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    t.cell(3, 0).text = "{%tr endfor %}"

    doc.add_paragraph()
    for label, tag in (("Subtotal", "{{ subtotal }}"), ("Tax", "{{ tax }}"), ("Total", "{{ total }}")):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rr = p.add_run(f"{label}: {tag}")
        rr.bold = label == "Total"

    foot = doc.add_paragraph()
    rr = foot.add_run("Source: {{ source_file }} (layout: {{ layout }}). Extracted automatically by docflow.")
    rr.italic, rr.font.size = True, Pt(8)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
