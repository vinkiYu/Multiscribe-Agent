"""Cross-source duplicate detection via normalized title+URL hashing (P64.2 T8).

Promotes the ``_title_key`` helper from scripts/sample_curation_dataset.py into
a formal component.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlparse


def normalize_title(title: str) -> str:
    """Normalize titles enough to discover cross-source duplicate candidates."""
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def normalize_url(url: str) -> str:
    """Reduce a URL to its host + path without tracking noise."""
    parsed = urlparse(url)
    return f"{parsed.netloc.casefold()}{parsed.path.rstrip('/')}"


class DedupHasher:
    """Hash candidates by normalized title and group cross-source duplicates.

    The hash key is the normalized title only: the same story syndicated across
    sources never shares a URL, so a URL-keyed hash cannot detect cross-source
    duplication at all. The URL is kept on the member records for review.
    """

    def hash_candidate(self, title: str, url: str) -> str:
        key = normalize_title(title) or normalize_url(url)
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def find_duplicates(self, fixtures: dict[str, list[dict[str, str]]]) -> list[DuplicateGroup]:
        """Group candidates sharing a hash across different samples or sources.

        ``fixtures`` maps sample_id -> candidate list (fixture JSON shape).
        Only groups spanning more than one entry are returned.
        """
        by_hash: dict[str, list[DuplicateMember]] = {}
        for sample_id, candidates in fixtures.items():
            for candidate in candidates:
                digest = self.hash_candidate(candidate.get("title", ""), candidate.get("url", ""))
                by_hash.setdefault(digest, []).append(
                    DuplicateMember(
                        sample_id=sample_id,
                        candidate_id=candidate.get("id", ""),
                        title=candidate.get("title", ""),
                        source=candidate.get("source", ""),
                    )
                )
        return [
            DuplicateGroup(hash=digest, members=members)
            for digest, members in sorted(by_hash.items())
            if len(members) > 1
        ]


@dataclass(frozen=True, slots=True)
class DuplicateMember:
    sample_id: str
    candidate_id: str
    title: str
    source: str


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    hash: str
    members: list[DuplicateMember]


__all__ = ["DedupHasher", "DuplicateGroup", "DuplicateMember", "normalize_title", "normalize_url"]
