from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

import httpx

from app.config import get_settings


OperationSymbol = Literal["+", "-", "*", "/"]


@dataclass(frozen=True)
class OperationResolution:
    """Normalized arithmetic operation selected from free-form cell text."""

    symbol: OperationSymbol | None
    confidence: float
    source: str
    reason: str

    @property
    def is_supported(self) -> bool:
        return self.symbol is not None


CANONICAL_OPERATIONS: dict[str, OperationSymbol] = {
    "add": "+",
    "addition": "+",
    "plus": "+",
    "sum": "+",
    "subtract": "-",
    "subtraction": "-",
    "minus": "-",
    "difference": "-",
    "multiply": "*",
    "multiplication": "*",
    "times": "*",
    "product": "*",
    "divide": "/",
    "division": "/",
    "quotient": "/",
}

SYMBOL_OPERATIONS: dict[str, OperationSymbol] = {
    "+": "+",
    "-": "-",
    "*": "*",
    "x": "*",
    "×": "*",
    "/": "/",
    "÷": "/",
}

LLM_CONFIDENCE_THRESHOLD = 0.72


def normalize_operation_text(value: Any) -> str:
    """Return a stable comparison key for a free-form operation value."""
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _resolve_locally(label: str, hints: dict[str, OperationSymbol] | None = None) -> OperationResolution | None:
    if not label:
        return OperationResolution(None, 1.0, "local", "Missing operation")
    if hints and label in hints:
        return OperationResolution(hints[label], 1.0, "user_clarification", "Matched user clarification")
    if label in SYMBOL_OPERATIONS:
        return OperationResolution(SYMBOL_OPERATIONS[label], 1.0, "local", "Matched arithmetic symbol")
    if label in CANONICAL_OPERATIONS:
        return OperationResolution(CANONICAL_OPERATIONS[label], 1.0, "local", "Matched canonical operation")

    compact_label = re.sub(r"[^a-z]+", "", label)
    if len(compact_label) >= 4:
        best_name = ""
        best_score = 0.0
        for candidate in CANONICAL_OPERATIONS:
            score = SequenceMatcher(None, compact_label, candidate).ratio()
            if score > best_score:
                best_name = candidate
                best_score = score
        if best_score >= 0.86:
            return OperationResolution(
                CANONICAL_OPERATIONS[best_name],
                best_score,
                "fuzzy",
                f"Closest canonical operation: {best_name}",
            )

    return None


def _extract_operation_hints(context_text: str | None) -> dict[str, OperationSymbol]:
    if not context_text:
        return {}

    hints: dict[str, OperationSymbol] = {}
    text = unicodedata.normalize("NFKC", context_text)
    patterns = [
        r"([^\s,;:]+)\s*(?:=|->|=>|means|mean|означає|означает|це|это|is)\s*([^\s,;:.]+)",
        r"([^\s,;:]+)\s+(?:as|как|як)\s+([^\s,;:.]+)",
    ]
    for pattern in patterns:
        for left, right in re.findall(pattern, text, flags=re.IGNORECASE):
            label = normalize_operation_text(left)
            operation_name = normalize_operation_text(right)
            symbol = SYMBOL_OPERATIONS.get(operation_name) or CANONICAL_OPERATIONS.get(operation_name)
            if label and symbol:
                hints[label] = symbol
    return hints


def _parse_llm_response(content: str) -> dict[str, OperationResolution]:
    payload = json.loads(content)
    items = payload.get("operations", payload if isinstance(payload, list) else [])
    resolutions: dict[str, OperationResolution] = {}
    for item in items:
        label = normalize_operation_text(item.get("label"))
        operation = normalize_operation_text(item.get("operation"))
        confidence = float(item.get("confidence", 0.0))
        reason = str(item.get("reason", "OpenRouter classification"))
        symbol = CANONICAL_OPERATIONS.get(operation)
        if operation in {"unsupported", "ambiguous", "unknown"}:
            symbol = None
        if confidence < LLM_CONFIDENCE_THRESHOLD:
            symbol = None
            reason = f"Low-confidence operation classification: {reason}"
        if label:
            resolutions[label] = OperationResolution(symbol, confidence, "llm", reason)
    return resolutions


async def _classify_with_openrouter(labels: list[str]) -> dict[str, OperationResolution]:
    settings = get_settings()
    if not labels or not settings.openrouter_api_key:
        return {}

    prompt = {
        "task": (
            "Classify each free-form spreadsheet operation label into exactly one "
            "arithmetic operation: add, subtract, multiply, divide, unsupported, or ambiguous. "
            "Labels may contain typos or be written in any human language. "
            "Use unsupported for non-arithmetic text. Use ambiguous when direction matters "
            "and the label does not clearly define A op B."
        ),
        "labels": labels,
        "output_schema": {
            "operations": [
                {
                    "label": "original label",
                    "operation": "add|subtract|multiply|divide|unsupported|ambiguous",
                    "confidence": "number from 0 to 1",
                    "reason": "short explanation",
                }
            ]
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. Do not calculate row values.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 600,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _parse_llm_response(content)


async def resolve_operations(
    labels: Iterable[Any],
    context_text: str | None = None,
) -> dict[str, OperationResolution]:
    """Resolve unique operation labels once, using local matching then LLM fallback."""
    normalized_labels = sorted({normalize_operation_text(label) for label in labels})
    hints = _extract_operation_hints(context_text)
    resolutions: dict[str, OperationResolution] = {}
    unresolved: list[str] = []

    for label in normalized_labels:
        local_resolution = _resolve_locally(label, hints)
        if local_resolution is None:
            unresolved.append(label)
        else:
            resolutions[label] = local_resolution

    if unresolved:
        try:
            resolutions.update(await _classify_with_openrouter(unresolved))
        except (httpx.HTTPError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            for label in unresolved:
                resolutions[label] = OperationResolution(
                    None,
                    0.0,
                    "llm_error",
                    f"Operation classification failed: {exc.__class__.__name__}",
                )

    for label in unresolved:
        resolutions.setdefault(
            label,
            OperationResolution(None, 0.0, "unresolved", "Unsupported or ambiguous operation"),
        )
    return resolutions
