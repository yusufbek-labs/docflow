"""Regenerate the 6 synthetic sample invoices into samples/invoices/."""
from pathlib import Path

from docflow.samples import generate_samples

if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "invoices"
    for p in generate_samples(out):
        print("wrote", p)
