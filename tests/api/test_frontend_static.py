from pathlib import Path

from fastapi.testclient import TestClient

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


def test_frontend_index_is_served_at_root(tmp_path) -> None:
    """The production frontend bundle is available from the API origin."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Multiscribe</title>" in response.text


def test_frontend_assets_do_not_override_api_routes(tmp_path) -> None:
    """Static mounting must not shadow the health endpoint."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend-api.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_css_uses_browser_compatible_content_type(tmp_path) -> None:
    """Windows MIME defaults must not cause Chromium to reject the stylesheet."""
    assets_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "assets"
    css_path = next(assets_dir.glob("index-*.css"))
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend-css.sqlite"))
    context = ServiceContext(settings)

    with TestClient(create_app(settings, context)) as client:
        response = client.get(f"/assets/{css_path.name}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
