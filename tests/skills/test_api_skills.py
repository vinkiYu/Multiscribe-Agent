"""JWT-protected Skill API coverage."""

from __future__ import annotations

import httpx
import pytest

from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.registry import SkillRegistry
from multiscribe_agent.skills.scanner import SkillScanner
from multiscribe_agent.skills.service import SkillService


@pytest.mark.asyncio
async def test_skill_api_crud_and_reload(tmp_path) -> None:
    """JWT routes create, list, get, reload, and delete isolated custom skills."""
    settings = SystemSettings(_env_file=None, db_path=":memory:")
    context = ServiceContext(settings)
    await context.init()
    try:
        context.skill_service = SkillService(
            SkillRegistry(),
            SkillScanner(parse_frontmatter),
            tmp_path / "builtin",
            tmp_path / "custom",
        )
        app = create_app(settings, context)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/skills")).status_code == 401
            token = (await client.post("/api/login", json={"password": "admin123"})).json()[
                "access_token"
            ]
            headers = {"Authorization": f"Bearer {token}"}
            created = await client.post(
                "/api/skills",
                headers=headers,
                json={
                    "id": "api-skill",
                    "frontmatter": {"name": "API", "description": "Created", "bins": []},
                    "instructions": "Use the API skill.",
                },
            )
            listed = await client.get("/api/skills", headers=headers)
            fetched = await client.get("/api/skills/api-skill", headers=headers)
            reloaded = await client.post("/api/skills/reload", headers=headers)
            deleted = await client.delete("/api/skills/api-skill", headers=headers)
        assert created.status_code == 200
        assert listed.json()[0]["id"] == "api-skill"
        assert fetched.json()["instructions"] == "Use the API skill."
        assert reloaded.json() == {"loaded": 1}
        assert deleted.json() == {"status": "deleted"}
    finally:
        await context.close()
