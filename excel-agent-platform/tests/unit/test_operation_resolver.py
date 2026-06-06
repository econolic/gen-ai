import pytest

from app.services import operation_resolver
from app.services.operation_resolver import OperationResolution, resolve_operations


@pytest.mark.asyncio
async def test_resolves_typo_with_local_fuzzy_matching(monkeypatch):
    async def fail_if_called(labels):
        raise AssertionError(f"LLM should not be needed for {labels}")

    monkeypatch.setattr(operation_resolver, "_classify_with_openrouter", fail_if_called)

    resolutions = await resolve_operations(["additon"])

    assert resolutions["additon"].symbol == "+"
    assert resolutions["additon"].source == "fuzzy"


@pytest.mark.asyncio
async def test_resolves_unknown_language_with_llm_fallback(monkeypatch):
    async def fake_classify(labels):
        assert labels == ["suma"]
        return {
            "suma": OperationResolution(
                symbol="+",
                confidence=0.91,
                source="llm",
                reason="Spanish addition label",
            )
        }

    monkeypatch.setattr(operation_resolver, "_classify_with_openrouter", fake_classify)

    resolutions = await resolve_operations(["suma"])

    assert resolutions["suma"].symbol == "+"
    assert resolutions["suma"].confidence == 0.91
    assert resolutions["suma"].source == "llm"


@pytest.mark.asyncio
async def test_low_confidence_llm_result_is_not_used(monkeypatch):
    async def fake_classify(labels):
        return {
            "combine": OperationResolution(
                symbol=None,
                confidence=0.4,
                source="llm",
                reason="Low-confidence operation classification: could mean several things",
            )
        }

    monkeypatch.setattr(operation_resolver, "_classify_with_openrouter", fake_classify)

    resolutions = await resolve_operations(["combine"])

    assert resolutions["combine"].symbol is None
    assert resolutions["combine"].confidence == 0.4


@pytest.mark.asyncio
async def test_user_clarification_hint_overrides_llm(monkeypatch):
    async def fail_if_called(labels):
        raise AssertionError(f"User clarification should resolve {labels}")

    monkeypatch.setattr(operation_resolver, "_classify_with_openrouter", fail_if_called)

    resolutions = await resolve_operations(["suma"], context_text="User clarification: suma = +")

    assert resolutions["suma"].symbol == "+"
    assert resolutions["suma"].source == "user_clarification"
