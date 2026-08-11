"""Route modules registered by the FastAPI application factory."""

from multiscribe_agent.api.routes import chat as chat_routes
from multiscribe_agent.api.routes import knowledge as knowledge_routes
from multiscribe_agent.api.routes import memory as memory_routes

__all__ = ["chat_routes", "knowledge_routes", "memory_routes"]
