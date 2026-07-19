from fastapi.testclient import TestClient

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


def test_execute_authenticates_and_dispatches_tool(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "api.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        issued = client.post("/api/ai/v1/register", json={}).json()
        response = client.post(
            "/api/ai/v1/execute",
            headers={"X-API-Key": issued["api_key"]},
            json={"name": "list_sources", "arguments": {}},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True


def test_execute_rejects_missing_or_unknown_key(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "api.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        assert client.post("/api/ai/v1/execute", json={}).status_code == 401
        assert (
            client.post(
                "/api/ai/v1/execute",
                headers={"X-API-Key": "sk_missing"},
                json={"name": "list_sources"},
            ).status_code
            == 401
        )
