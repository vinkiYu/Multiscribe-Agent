"""Process-wide registry for discovered skill instructions."""

from __future__ import annotations

from builtins import list as builtin_list

from multiscribe_agent.domain.models import SkillEntry


class SkillRegistry:
    """Store skill entries under stable identifiers."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._entries: dict[str, SkillEntry] = {}

    def register(self, entry: SkillEntry) -> None:
        """Register or replace one entry."""
        self._entries[entry.id] = entry

    def unregister(self, skill_id: str) -> None:
        """Remove an entry when present."""
        self._entries.pop(skill_id, None)

    def get(self, skill_id: str) -> SkillEntry:
        """Return one entry, raising KeyError when not loaded."""
        return self._entries[skill_id]

    def list(self) -> builtin_list[SkillEntry]:
        """Return entries in stable identifier order."""
        return [self._entries[skill_id] for skill_id in sorted(self._entries)]

    def clear(self) -> None:
        """Remove all entries for reload or test isolation."""
        self._entries.clear()

    def bulk_load(self, entries: builtin_list[SkillEntry]) -> None:
        """Replace all registry entries with a freshly scanned list."""
        self.clear()
        for entry in entries:
            self.register(entry)


_singleton: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Return the process-wide SkillRegistry singleton."""
    global _singleton
    if _singleton is None:
        _singleton = SkillRegistry()
    return _singleton
