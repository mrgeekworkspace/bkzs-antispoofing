import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


def test_status_endpoint(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "BKZS Anti-Spoofing System"


def test_snapshot_endpoint(client):
    resp = client.get("/api/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "receiver" in data
    assert "detection" in data
    assert "satellites" in data


def test_attack_start_stop(client):
    resp = client.post("/api/attack/start", json={
        "attack_type": "JAMMING",
        "intensity": 0.8,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = client.post("/api/attack/stop")
    assert resp.status_code == 200
