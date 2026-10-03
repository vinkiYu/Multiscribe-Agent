from fastapi.testclient import TestClient

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from tests.db import get_test_database_url


def test_tools_use_openai_function_schema(tmp_path) -> None:
    settings = SystemSettings(_env_file=None, database_url=get_test_database_url())
    context = ServiceContext(settings)
    with TestClient(create_app(settings, context)) as client:
        response = client.get("/api/ai/v1/tools")
    assert response.status_code == 200
    tools = response.json()["tools"]
    names = {tool["function"]["name"] for tool in tools}
    assert {"list_sources", "kb_search", "list_publishers"} <= names
