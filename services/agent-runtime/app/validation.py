from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from shared_schemas.actions import PlayerTurn


@dataclass
class ValidationResult:
    valid: bool
    parsed: PlayerTurn | None = None
    errors: list[str] = field(default_factory=list)
    raw_text: str = ""


class OutputValidator:
    def validate_player_turn(self, raw_text: str) -> ValidationResult:
        cleaned = raw_text.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                errors=[f"Invalid JSON: {str(e)}"],
                raw_text=raw_text,
            )

        try:
            turn = PlayerTurn.model_validate(data)
            return ValidationResult(
                valid=True,
                parsed=turn,
                raw_text=raw_text,
            )
        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                errors.append(f"{loc}: {msg}")

            return ValidationResult(
                valid=False,
                errors=errors,
                raw_text=raw_text,
            )

    def extract_json_from_text(self, text: str) -> str | None:
        start_markers = ["{", "```json", "```"]
        end_markers = ["}", "```"]

        text = text.strip()

        json_start = -1
        for marker in ["{", "[{"]:
            idx = text.find(marker)
            if idx != -1 and (json_start == -1 or idx < json_start):
                json_start = idx

        if json_start == -1:
            return None

        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[json_start:], start=json_start):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
            elif char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1

            if brace_count == 0 and bracket_count == 0 and i > json_start:
                return text[json_start : i + 1]

        return None


def get_output_validator() -> OutputValidator:
    return OutputValidator()
