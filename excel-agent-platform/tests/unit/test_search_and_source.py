import pytest
from app.schemas.evidence import FactRequest, FactResult
from app.tools import local_source
from app.tools.local_search import _extract_typed_value


def test_typed_search_extracts_numeric_units():
    value, unit = _extract_typed_value("Mount Everest is 8,848 meters high", "number", "height", "meters")

    assert value == 8848
    assert unit == "meters"


def test_typed_search_extracts_ceo_names():
    value, unit = _extract_typed_value("The CEO is Jane Smith according to filings", "string", "ceo", "")

    assert value == "Jane Smith"
    assert unit is None


def test_fact_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    request = FactRequest(entity="Demo", attribute="population", unit="people")
    result = FactResult(request=request, value=123, unit="people", confidence=0.9)

    local_source._cache_put(result)

    assert local_source._cache_get(request).value == 123


def test_coordinates_extraction_from_snippets():
    from app.tools.local_search import _extract_coordinates_from_snippet

    coords1 = _extract_coordinates_from_snippet("Latitude: 50.4501 N, Longitude: -30.5234")
    assert coords1 == {"lat": 50.4501, "lon": -30.5234}

    coords2 = _extract_coordinates_from_snippet("Kyiv is located at 50.4501° N, 30.5234° E")
    assert coords2 == {"lat": 50.4501, "lon": 30.5234}

    coords3 = _extract_coordinates_from_snippet("Rio is at 22.9068° S, 43.1729° W")
    assert coords3 == {"lat": -22.9068, "lon": -43.1729}

    coords4 = _extract_coordinates_from_snippet("Coords are (50.450100, 30.523400)")
    assert coords4 == {"lat": 50.4501, "lon": 30.5234}


def test_coordinates_extraction_fails_for_single_float():
    from app.tools.local_search import _extract_coordinates_from_snippet

    assert _extract_coordinates_from_snippet("The height is 8848.0 meters") is None


@pytest.mark.asyncio
async def test_llm_extract_fact_fallback(monkeypatch):
    import httpx
    from app.tools import local_search
    from app.schemas.evidence import FactRequest

    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-key")
    from app.config import get_settings
    get_settings.cache_clear()

    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"value": {"lat": 10.2, "lon": 20.3}, "confidence": 0.85, "reason": "Extracted"}'
                        }
                    }
                ]
            }

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    request = FactRequest(entity="Test", attribute="coordinates")
    result = await local_search._llm_extract_fact(["snippet"], request, "coordinates")

    assert result is not None
    assert result.value == {"lat": 10.2, "lon": 20.3}
    assert result.confidence == 0.85
