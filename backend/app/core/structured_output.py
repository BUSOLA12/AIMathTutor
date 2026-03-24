from collections.abc import Iterable, Mapping
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def get_text(
    payload: Mapping[str, Any],
    key: str,
    default: str,
    *,
    allowed: set[str] | None = None,
) -> str:
    value = payload.get(key)
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default
    if allowed and text not in allowed:
        return default
    return text


def get_float(
    payload: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = payload.get(key)
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default

    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def get_list(payload: Mapping[str, Any], key: str, default: list[Any] | None = None) -> list[Any]:
    value = payload.get(key)
    if isinstance(value, list):
        return value
    return list(default or [])


def get_string_list(
    payload: Mapping[str, Any],
    key: str,
    default: Iterable[str] | None = None,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return list(default or [])

    cleaned: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            cleaned.append(text)

    if cleaned or not value:
        return cleaned
    return list(default or [])


def get_dict(
    payload: Mapping[str, Any],
    key: str,
    default: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return dict(value)
    return dict(default or {})


from langchain_core.exceptions import OutputParserException  # noqa: E402
from langchain_core.output_parsers import JsonOutputParser  # noqa: E402


class RobustJsonOutputParser(JsonOutputParser):
    """JsonOutputParser that repairs malformed LLM JSON before raising.

    Handles any formatting error the LLM might produce — missing commas,
    trailing commas, single quotes, unquoted keys, extra markdown, etc.
    """

    def parse_result(self, result: list, partial: bool = False) -> Any:
        try:
            return super().parse_result(result, partial=partial)
        except OutputParserException as exc:
            from json_repair import repair_json
            raw = getattr(exc, "llm_output", "") or ""
            repaired = repair_json(raw, return_objects=True)
            if repaired:
                return repaired
            raise
