"""검수 큐 API."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.tiling import tile_index


def _seed_tile(api_client, dataset_id: str, tile_id: str) -> None:
    with Session(api_client.app.state.engine) as s:
        tile_index.upsert_tile(
            s,
            tenant_id="default",
            dataset_id=dataset_id,
            tile_id=tile_id,
            status="labeled",
            metadata_json="{}",
        )


def test_review_queue_empty(api_client) -> None:
    r = api_client.get("/api/tenants/default/review/queue")
    assert r.status_code == 200
    assert r.json() == []


def test_review_approve_and_list(api_client) -> None:
    ds = "ds_review_approve"
    assert api_client.post("/api/tenants/default/datasets", json={"dataset_id": ds, "source_geotiff": None}).status_code == 201
    _seed_tile(api_client, ds, "t1")
    r = api_client.post(f"/api/tenants/default/datasets/{ds}/tiles/t1/review/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    pending = api_client.get("/api/tenants/default/review/queue")
    assert pending.json() == []

    approved = api_client.get("/api/tenants/default/review/queue?status=approved")
    data = approved.json()
    assert len(data) == 1
    assert data[0]["tile_id"] == "t1"
    assert data[0]["dataset_id"] == ds
    assert data[0]["status"] == "approved"


def test_review_reject_with_note(api_client) -> None:
    ds = "ds_review_reject"
    assert api_client.post("/api/tenants/default/datasets", json={"dataset_id": ds, "source_geotiff": None}).status_code == 201
    _seed_tile(api_client, ds, "t2")
    r = api_client.post(
        f"/api/tenants/default/datasets/{ds}/tiles/t2/review/reject",
        json={"note": "품질 불충분"},
    )
    assert r.status_code == 200
    rej = api_client.get("/api/tenants/default/review/queue?status=rejected")
    data = rej.json()
    assert len(data) == 1
    assert data[0]["note"] == "품질 불충분"


def test_review_approve_tile_missing_404(api_client) -> None:
    r = api_client.post("/api/tenants/default/datasets/missing_ds/tiles/ghost/review/approve")
    assert r.status_code == 404
