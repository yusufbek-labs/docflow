"""Batch orchestration: folder of PDFs -> Invoice objects -> output files."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .excel import write_workbook
from .extract import Config, extract_invoice
from .models import Invoice
from .render import write_docx, write_json
from .validate import validate

ProgressFn = Callable[[int, int, Invoice], None]


@dataclass
class RunResult:
    invoices: list[Invoice] = field(default_factory=list)
    outputs: dict[str, Path] = field(default_factory=dict)
    docx_files: list[Path] = field(default_factory=list)

    @property
    def ok(self) -> list[Invoice]:
        return [i for i in self.invoices if not i.needs_review]

    @property
    def review(self) -> list[Invoice]:
        return [i for i in self.invoices if i.needs_review]


def find_pdfs(input_dir: str | Path) -> list[Path]:
    return sorted(p for p in Path(input_dir).iterdir() if p.suffix.lower() == ".pdf")


def process(input_dir: str | Path, cfg: Config, ai: Any | None = None,
            today: date | None = None, progress: ProgressFn | None = None) -> list[Invoice]:
    """Extract + validate every PDF. One bad file never stops the batch."""
    pdfs = find_pdfs(input_dir)
    out: list[Invoice] = []
    for n, pdf in enumerate(pdfs, 1):
        inv = validate(extract_invoice(pdf, cfg, ai), cfg, today)
        out.append(inv)
        if progress:
            progress(n, len(pdfs), inv)
    return out


def write_outputs(invoices: list[Invoice], output_dir: str | Path,
                  template: str | Path | None) -> RunResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    res = RunResult(invoices=invoices)
    res.outputs["excel"] = write_workbook(invoices, out / "invoices.xlsx")
    res.outputs["json"] = write_json(invoices, out / "invoices.json")
    if template:
        for inv in invoices:
            res.docx_files.append(write_docx(inv, template, out / "documents"))
        res.outputs["documents"] = out / "documents"
    return res
