from pathlib import Path

from fastapi.testclient import TestClient

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings


def test_frontend_index_is_served_at_root(tmp_path) -> None:
    """The production marketing site remains available from the API origin."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Multiscribe · 智能采集" in response.text


def test_frontend_console_is_served_as_a_second_entry(tmp_path) -> None:
    """The built React console is reachable without replacing the marketing home page."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend-console.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/console.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>控制台 | Multiscribe</title>" in response.text


def test_frontend_login_is_served_before_console_access(tmp_path) -> None:
    """The login page is available as the public authentication entry."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend-login.sqlite"))
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/login.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>登录 | Multiscribe</title>" in response.text


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
    css_path = next(assets_dir.glob("*.css"))
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "frontend-css.sqlite"))
    context = ServiceContext(settings)

    with TestClient(create_app(settings, context)) as client:
        response = client.get(f"/assets/{css_path.name}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
