"""Facts ingestion endpoints (normaliser wired by the app composition root)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.facts._xlsx import fact_xlsx, indicators_params_xlsx

_ENTITY = "5299001234567890ABCD"
_REF_DATE = "2025-12-31"


def _post_facts(client: TestClient, run_id: int, data: bytes, entity: str = _ENTITY):
    return client.post(
        f"/api/facts/runs/{run_id}/fact-file",
        data={"entity": entity, "reference_date": _REF_DATE},
        files={"file": ("facts.xlsx", data, "application/octet-stream")},
    )


def test_attach_fact_file_persists_facts(client: TestClient) -> None:
    data = fact_xlsx(
        [
            ("C_67_00", "0010", "0010", 100000),
            ("C 74.00.a", "0020", "0010", 250000),
        ]
    )
    resp = _post_facts(client, 1, data)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["fact_count"] == 2
    assert body["run_file"]["role"] == "fact_input"

    facts = client.get("/api/facts/runs/1/facts").json()
    assert len(facts) == 2
    assert facts[0]["template_code"] == "C_67.00"
    assert facts[0]["entity"] == _ENTITY
    assert facts[0]["reference_date"] == _REF_DATE

    files = client.get("/api/facts/runs/1/files").json()
    assert [f["role"] for f in files] == ["fact_input"]


def test_fact_file_rejection_returns_row_details(client: TestClient) -> None:
    data = fact_xlsx(
        [
            ("C_67_00", "0010", "0010", 100000),
            ("bad-code", "0020", "0010", 200000),
        ]
    )
    resp = _post_facts(client, 2, data)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "file_rejected"
    assert error["details"][0]["row"] == 3
    # nothing persisted on rejection
    assert client.get("/api/facts/runs/2/facts").json() == []


def test_malformed_entity_rejected(client: TestClient) -> None:
    data = fact_xlsx([("C_67_00", "0010", "0010", 100000)])
    resp = _post_facts(client, 3, data, entity="SHORT")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_attach_indicators_params(client: TestClient) -> None:
    data = indicators_params_xlsx(
        [
            ("entity_lei", _ENTITY),
            ("reference_date", "2025-12-31"),
            ("base_currency", "EUR"),
            ("decimals", -3),
        ],
        [("C_73.00.a", True), ("C_74.00.a", True)],
    )
    resp = client.post(
        "/api/facts/runs/5/indicators-params-file",
        files={"file": ("ip.xlsx", data, "application/octet-stream")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["run_file"]["role"] == "indicators_params"
    assert body["params"]["entity_lei"] == _ENTITY
    assert len(body["params"]["filing_indicators"]) == 2
