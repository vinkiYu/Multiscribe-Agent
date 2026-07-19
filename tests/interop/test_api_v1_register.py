from fastapi.testclient import TestClient

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


def test_register_returns_one_time_key(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "api.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.post("/api/ai/v1/register", json={"description": "test"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key"].startswith("sk_")
    assert payload["approved"] is True


def test_approval_mode_can_be_approved(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "api.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.post("/api/ai/v1/register", json={"auto_approve": False})
        key_id = response.json()["key_id"]
        assert client.put(f"/api/ai/v1/keys/{key_id}/approve").status_code == 200
