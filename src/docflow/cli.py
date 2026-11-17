"""Command line interface: docflow run | check | demo."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .ai import DEFAULT_MODEL, get_ai_extractor
from .extract import load_config
from .models import Invoice
from .pipeline import find_pdfs, process, write_outputs

ROOT = Path(__file__).resolve().parents[2]       # project root when installed with -e


def _default(rel: str) -> Path:
    """Prefer ./rel (current directory), fall back to the project checkout."""
    p = Path(rel)
    return p if p.exists() else ROOT / rel


def _ai(disabled: bool):
    if disabled:
        return None, "disabled (--no-ai)"
    ai = get_ai_extractor()
    if ai is None:
        return None, "off (ANTHROPIC_API_KEY not set; nothing leaves this machine)"
    return ai, f"ON, model {ai.model} (only fields the rules missed are sent)"


def _line(n: int, total: int, inv: Invoice) -> None:
    num = inv.value("invoice_number") or "?"
    note = ""
    if inv.needs_review:
        note = f"  <- {len(inv.errors)} problem(s), {len(inv.low_confidence_fields)} low-confidence field(s)"
    print(f"[{n}/{total}] {inv.source_file:<34} {(inv.layout or 'unknown'):<8} "
          f"{str(num):<12} {inv.status.upper() if inv.needs_review else 'OK'}{note}")


def _summary(invoices: list[Invoice]) -> None:
    ok = sum(not i.needs_review for i in invoices)
    print()
    print("Summary")
    print(f"  Processed     {len(invoices)}")
    print(f"  Accepted      {ok}")
    print(f"  Needs review  {len(invoices) - ok}")
    for inv in invoices:
        for issue in inv.errors:
            print(f"    - {inv.source_file}: {issue.message}")


def _prepare(args) -> tuple:
    inp = Path(args.input)
    if not inp.is_dir():
        print(f"error: input folder not found: {inp}", file=sys.stderr)
        return None
    pdfs = find_pdfs(inp)
    if not pdfs:
        print(f"error: no PDF files in {inp}", file=sys.stderr)
        return None
    cfg = load_config(args.config or _default("config/layouts.yaml"))
    return inp, pdfs, cfg


def cmd_run(args) -> int:
    prep = _prepare(args)
    if not prep:
        return 2
    inp, pdfs, cfg = prep
    ai, ai_note = _ai(args.no_ai)
    print(f"docflow {__version__}  |  input: {inp}  ({len(pdfs)} PDFs)  |  output: {args.output}")
    print(f"AI fallback: {ai_note}\n")
    invoices = process(inp, cfg, ai, progress=_line)
    template = None if args.no_docx else (args.template or _default("templates/invoice.docx"))
    res = write_outputs(invoices, args.output, template)
    _summary(invoices)
    print("\nOutputs")
    print(f"  Excel      {res.outputs['excel']}")
    print(f"  JSON       {res.outputs['json']}")
    if template:
        print(f"  Documents  {res.outputs['documents']}  ({len(res.docx_files)} .docx)")
    return 0


def cmd_check(args) -> int:
    prep = _prepare(args)
    if not prep:
        return 2
    inp, pdfs, cfg = prep
    ai, ai_note = _ai(args.no_ai)
    print(f"docflow {__version__} check  |  {len(pdfs)} PDFs in {inp}  |  AI fallback: {ai_note}\n")
    invoices = process(inp, cfg, ai, progress=_line)
    _summary(invoices)
    return 1 if any(i.needs_review for i in invoices) else 0


def cmd_demo(args) -> int:
    from .samples import generate_samples
    folder = Path(args.samples)
    made = generate_samples(folder)
    print(f"Generated {len(made)} synthetic sample invoices in {folder}\n")
    args.input = str(folder)
    return cmd_run(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="docflow", description="PDF invoices -> data, Word docs, Excel summary.")
    p.add_argument("--version", action="version", version=f"docflow {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, with_output=True):
        sp.add_argument("--config", help="layout rules (default: config/layouts.yaml)")
        sp.add_argument("--no-ai", action="store_true", help="never use the AI fallback")
        if with_output:
            sp.add_argument("--output", default="out", help="output folder (default: out/)")
            sp.add_argument("--template", help="Word template (default: templates/invoice.docx)")
            sp.add_argument("--no-docx", action="store_true", help="skip Word documents")

    r = sub.add_parser("run", help="extract, validate and write all outputs")
    r.add_argument("--input", required=True, help="folder with PDF invoices")
    common(r)
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("check", help="validate only; exit code 1 if anything needs review")
    c.add_argument("--input", required=True)
    common(c, with_output=False)
    c.set_defaults(func=cmd_check)

    d = sub.add_parser("demo", help="generate synthetic sample invoices and run on them")
    d.add_argument("--samples", default="samples/invoices", help="where to write sample PDFs")
    common(d)
    d.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
