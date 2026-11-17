"""Builds docs/demo-run.png and docs/excel-preview.png from a REAL run.

Runs `docflow run` on samples/invoices, renders its real stdout as a terminal-style
image and draws the generated Invoices sheet as a table. Nothing is typed in by hand.
"""
import os
import subprocess
import sys
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = Path("C:/Windows/Fonts")


def font(name: str, size: int):
    return ImageFont.truetype(str(FONTS / name), size)


def terminal_image(command: str, output: str, dest: Path) -> None:
    mono = font("consola.ttf", 17)
    title = font("segoeuib.ttf", 14)
    lines = [f"PS C:\\docflow> {command}", ""] + output.rstrip().splitlines()
    pad, lh, bar = 22, 24, 40
    width_px = max(int(mono.getlength(ln)) for ln in lines) + 2 * pad
    img = Image.new("RGB", (max(width_px, 900), bar + pad + lh * len(lines) + pad), "#0C0C0C")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, bar], fill="#2D2D2D")
    for i, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        d.ellipse([16 + i * 24, 13, 30 + i * 24, 27], fill=col)
    d.text((110, 10), "docflow - Windows Terminal", font=title, fill="#CCCCCC")
    y = bar + pad
    for ln in lines:
        color = "#CCCCCC"
        if ln.startswith("PS "):
            color = "#F9F1A5"
        elif "NEEDS REVIEW" in ln or ln.strip().startswith("- ") or "Needs review" in ln:
            color = "#F2A65A"
        elif ln.rstrip().endswith(" OK"):
            color = "#16C60C"
        elif ln.strip() in ("Summary", "Outputs"):
            color = "#61D6D6"
        d.text((pad, y), ln, font=mono, fill=color)
        y += lh
    img.save(dest)


def excel_image(xlsx: Path, dest: Path) -> None:
    ws = load_workbook(xlsx)["Invoices"]
    cols = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13]            # skip layout + confidence for width
    rows = []
    for r in ws.iter_rows(values_only=False):
        row = []
        for ci in cols:
            c = r[ci - 1]
            v = c.value
            if hasattr(v, "strftime"):
                v = v.strftime("%Y-%m-%d")
            elif isinstance(v, (int, float)):
                v = f"{v:,.2f}"
            row.append("" if v is None else str(v))
        rows.append(row)
    head, body = rows[0], rows[1:]
    f, fb, ft = font("segoeui.ttf", 15), font("segoeuib.ttf", 15), font("segoeuib.ttf", 20)
    pad, rh = 14, 38
    widths = [max(int(fb.getlength(r[i])) if r is head else int(f.getlength(r[i]))
                  for r in rows) + 2 * pad for i in range(len(cols))]
    numeric = {i for i, ci in enumerate(cols) if ci in (9, 10, 11)}
    top = 62
    img = Image.new("RGB", (sum(widths) + 40, top + rh * len(rows) + 24), "#FFFFFF")
    d = ImageDraw.Draw(img)
    d.text((20, 16), "out/invoices.xlsx  -  sheet \"Invoices\"", font=ft, fill="#1F3864")
    y = top
    for ri, row in enumerate(rows):
        x = 20
        if ri == 0:
            d.rectangle([20, y, 20 + sum(widths), y + rh], fill="#1F3864")
        elif ri % 2 == 0:
            d.rectangle([20, y, 20 + sum(widths), y + rh], fill="#F4F6FA")
        for i, cell in enumerate(row):
            fill, fnt = ("#FFFFFF", fb) if ri == 0 else ("#222222", f)
            if ri > 0 and i == len(row) - 1:
                bad = cell != "OK"
                d.rounded_rectangle([x + 8, y + 7, x + widths[i] - 8, y + rh - 7], 6,
                                    fill="#FCE4D6" if bad else "#E2F0D9")
                fnt, fill = fb, "#9C3D00" if bad else "#2E6B1F"
            tw = int(fnt.getlength(cell))
            tx = x + widths[i] - pad - tw if (i in numeric and ri > 0) else x + pad
            if ri > 0 and i == len(row) - 1:
                tx = x + (widths[i] - tw) // 2
            d.text((tx, y + 9), cell, font=fnt, fill=fill)
            x += widths[i]
        y += rh
    d.line([20, y, 20 + sum(widths), y], fill="#BFBFBF")
    img.save(dest)


def main() -> None:
    out = ROOT / "out"
    cmd = [sys.executable, "-m", "docflow", "run", "--input", "samples/invoices", "--output", "out"]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "ANTHROPIC_API_KEY": ""})
    if res.returncode != 0:
        sys.exit(res.stderr)
    (ROOT / "docs").mkdir(exist_ok=True)
    terminal_image("docflow run --input samples/invoices --output out", res.stdout,
                   ROOT / "docs" / "demo-run.png")
    excel_image(out / "invoices.xlsx", ROOT / "docs" / "excel-preview.png")
    print("wrote docs/demo-run.png and docs/excel-preview.png")


if __name__ == "__main__":
    main()
