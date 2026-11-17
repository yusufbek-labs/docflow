from datetime import date
from pathlib import Path

import pytest

from docflow.extract import load_config
from docflow.pipeline import process, write_outputs
from docflow.samples import generate_samples

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 1, 1)          # fixed so tests never depend on the real clock


@pytest.fixture(scope="session")
def cfg():
    return load_config(ROOT / "config" / "layouts.yaml")


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("invoices")
    generate_samples(d)
    return d


@pytest.fixture(scope="session")
def invoices(sample_dir, cfg):
    return {i.source_file: i for i in process(sample_dir, cfg, today=TODAY)}


@pytest.fixture(scope="session")
def run_output(sample_dir, cfg, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    invs = process(sample_dir, cfg, today=TODAY)
    res = write_outputs(invs, out, ROOT / "templates" / "invoice.docx")
    return out, res
