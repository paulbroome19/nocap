"""Guard the committed demo files: they must parse cleanly."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.facts.parsers import XlsxIndicatorsParamsParser, parse_fact_xlsx

Normalize = Callable[[str], str]

DEMO = Path(__file__).resolve().parents[3] / "demo"


@pytest.mark.skipif(not DEMO.exists(), reason="demo files not present")
def test_demo_fact_file_parses(normalize: Normalize) -> None:
    data = (DEMO / "fact_sample.xlsx").read_bytes()
    result = parse_fact_xlsx(data, normalize=normalize)
    assert result.errors == []
    assert len(result.facts) == 8
    # mixed input forms all canonicalise to DB form
    assert {f.template_code for f in result.facts} == {
        "C_73.00.a",
        "C_74.00.a",
        "C_76.00.a",
    }
    assert all(len(f.row_code) == 4 for f in result.facts)


@pytest.mark.skipif(not DEMO.exists(), reason="demo files not present")
def test_demo_warnings_and_broken_files_present(normalize: Normalize) -> None:
    warnings = parse_fact_xlsx(
        (DEMO / "fact_sample_warnings.xlsx").read_bytes(), normalize=normalize
    )
    assert warnings.errors == [] and warnings.facts
    # The broken file parses at the shape level (resolution errors surface later).
    broken = parse_fact_xlsx(
        (DEMO / "fact_broken.xlsx").read_bytes(), normalize=normalize
    )
    assert broken.errors == [] and len(broken.facts) == 3


@pytest.mark.skipif(not DEMO.exists(), reason="demo files not present")
def test_demo_indicators_params_parses(normalize: Normalize) -> None:
    data = (DEMO / "indicators_params.xlsx").read_bytes()
    result = XlsxIndicatorsParamsParser().parse(data, normalize=normalize)
    assert result.errors == []
    assert result.params is not None
    assert result.params.base_currency == "EUR"
    assert len(result.params.filing_indicators) == 4
