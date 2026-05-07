"""API 스모크 — TestClient."""

from __future__ import annotations


def test_get_config(api_client) -> None:
    r = api_client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["tiling"]["tile_size"] == 1024


def test_create_dataset_and_list(api_client) -> None:
    r = api_client.post(
        "/api/tenants/default/datasets",
        json={"dataset_id": "ds_test", "source_geotiff": None},
    )
    assert r.status_code == 201
    r2 = api_client.get("/api/tenants/default/datasets")
    assert r2.status_code == 200
    ids = [x["dataset_id"] for x in r2.json()]
    assert "ds_test" in ids


def test_export_stub_501(api_client) -> None:
    r = api_client.post("/api/tenants/default/datasets/x/export/unet")
    assert r.status_code == 501
