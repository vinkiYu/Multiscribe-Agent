"""SQL placeholder generation and translation utilities for database backends."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaceholderGenerator:
    """Generate SQL parameter placeholders for one database dialect."""

    style: str

    def for_count(self, count: int) -> str:
        """Return a comma-separated list of ``count`` placeholders.

        Raises:
            ValueError: If ``count`` is negative or the dialect is unsupported.
        """
        if count < 0:
            raise ValueError("Placeholder count cannot be negative")
        if self.style == "question_mark":
            return ", ".join("?" for _ in range(count))
        if self.style == "dollar":
            return ", ".join(f"${index}" for index in range(1, count + 1))
        if self.style == "percent":
            return ", ".join("%s" for _ in range(count))
        raise ValueError(f"Unknown placeholder style: {self.style!r}")

    def for_one(self) -> str:
        """Return a single parameter placeholder for this dialect."""
        return self.for_count(1)


QUESTION_MARK = PlaceholderGenerator("question_mark")
DOLLAR = PlaceholderGenerator("dollar")
PERCENT = PlaceholderGenerator("percent")


def translate_question_marks(sql: str, target: str = "dollar") -> str:
    """Translate bind placeholders outside quoted SQL literals.

    Single- and double-quoted values are copied verbatim, including their SQL
    doubled-quote escapes. This keeps literal question marks out of the bind
    parameter sequence during future backend migrations.

    Raises:
        ValueError: If the target dialect is unsupported or a quoted literal is unclosed.
    """
    generators = {
        "question_mark": QUESTION_MARK,
        "dollar": DOLLAR,
        "percent": PERCENT,
    }
    generator = generators.get(target)
    if generator is None:
        raise ValueError(f"Unsupported target dialect: {target!r}")
    if target == "question_mark" or not sql:
        return sql

    parts: list[str] = []
    quote: str | None = None
    placeholder_count = 0
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote is not None:
            parts.append(character)
            if character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    parts.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            parts.append(character)
        elif character == "?":
            placeholder_count += 1
            if target == "dollar":
                parts.append(f"${placeholder_count}")
            else:
                parts.append(generator.for_one())
        else:
            parts.append(character)
        index += 1

    if quote is not None:
        raise ValueError("SQL contains an unclosed quoted literal")
    return "".join(parts)
