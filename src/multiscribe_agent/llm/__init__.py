"""Provider-neutral LLM access and concrete LangChain integrations."""

from multiscribe_agent.llm.provider import AIProvider, create_provider

__all__ = ["AIProvider", "create_provider"]
