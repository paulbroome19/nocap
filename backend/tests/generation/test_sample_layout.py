"""Compare our generated package's structural layout to a real EBA sample.

The committed fixture ``sample_xbrl_csv_package.zip`` is a real EBA illustrative
sample (fictional DUMMYLEI, random data) for the PILLAR3 IRRBBDIS module. It is a
different framework than our COREP LCR output, so we compare *structure*, not
bytes: file set, CSV headers, datapoint id format.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from tests.generation._helpers import open_zip
from tests.generation.test_build_package import _build

SAMPLE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "sample_xbrl_csv_package.zip"
)


def _layout(zf: zipfile.ZipFile) -> dict:
    names = zf.namelist()
    root = names[0].split("/")[0]
    rel = {n[len(root) + 1 :] for n in names if n != root + "/"}
    reports = sorted(n for n in rel if n.startswith("reports/") and n.endswith(".csv"))
    template_csvs = [
        n
        for n in reports
        if Path(n).name not in {"parameters.csv", "FilingIndicators.csv"}
    ]

    def header(member: str) -> str:
        return zf.read(f"{root}/{member}").decode().splitlines()[0]

    return {
        "has_report_package": f"{root}/META-INF/reportPackage.json" in names,
        "has_report_json": f"{root}/reports/report.json" in names,
        "params_header": header("reports/parameters.csv"),
        "indicators_header": header("reports/FilingIndicators.csv"),
        "template_headers": {header(m) for m in template_csvs},
        "template_count": len(template_csvs),
    }


def test_our_layout_matches_sample() -> None:
    sample = _layout(open_zip(SAMPLE.read_bytes()))
    ours = _layout(open_zip(_build().content))

    # Same fixed structural anchors.
    assert sample["has_report_package"] and ours["has_report_package"]
    assert sample["has_report_json"] and ours["has_report_json"]

    # Same fixed CSV headers.
    assert ours["params_header"] == sample["params_header"] == "name,value"
    assert (
        ours["indicators_header"]
        == sample["indicators_header"]
        == "templateID,reported"
    )
    # Every template CSV starts with the fixed datapoint,factValue columns.
    for headers in (sample["template_headers"], ours["template_headers"]):
        assert headers
        assert all(h.startswith("datapoint,factValue") for h in headers)

    assert ours["template_count"] >= 1


def test_datapoint_id_format_matches_sample() -> None:
    import re

    sample_csv = None
    zf = open_zip(SAMPLE.read_bytes())
    for n in zf.namelist():
        base = Path(n).name
        if base.endswith(".csv") and base not in {
            "parameters.csv",
            "FilingIndicators.csv",
        }:
            sample_csv = zf.read(n).decode()
            break
    assert sample_csv is not None
    sample_dp = sample_csv.splitlines()[1].split(",")[0]
    ours_dp = (
        open_zip(_build().content)
        .read(f"{_build().filename[:-4]}/reports/c_73.00.a.csv")
        .decode()
        .splitlines()[1]
        .split(",")[0]
    )
    assert re.fullmatch(r"dp\d+", sample_dp)
    assert re.fullmatch(r"dp\d+", ours_dp)
