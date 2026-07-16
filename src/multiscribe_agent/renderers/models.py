"""Shared digest data models used by pipeline renderers and publishers."""

from __future__ import annotations

from dataclasses import dataclass

from multiscribe_agent.renderers.feishu_card import DigestItem


@dataclass(frozen=True, slots=True)
class CuratedDigest:
    """A dated, scored collection ready for multi-target publishing."""

    date: str
    title: str
    items: list[DigestItem]
    summary: str = ""
    total_scanned: int = 0
