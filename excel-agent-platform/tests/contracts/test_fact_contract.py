from pydantic import ValidationError

from app.schemas.evidence import (
    CoordinatesValue,
    FactRequest,
    FactResult,
    NumberValue,
    fact_value_to_python,
)


def test_coordinates_lookup_never_normalizes_to_number():
    request = FactRequest(entity="Kyiv", attribute="coordinates")
    result = FactResult(request=request, value={"lat": 50.45, "lon": 30.52}, unit="degrees")

    assert result.value_type == "coordinates"
    assert isinstance(result.value, CoordinatesValue)
    assert fact_value_to_python(result.value) == {"lat": 50.45, "lon": 30.52}


def test_number_lookup_never_normalizes_to_coordinates():
    request = FactRequest(entity="Everest", attribute="height", unit="meters")
    result = FactResult(request=request, value=8848, unit="meters")

    assert result.value_type == "number"
    assert isinstance(result.value, NumberValue)
    assert fact_value_to_python(result.value) == 8848


def test_invalid_coordinates_payload_is_rejected():
    request = FactRequest(entity="Broken", attribute="coordinates")

    try:
        FactResult(request=request, value={"lat": 1000, "lon": "bad"})
    except ValidationError as exc:
        assert "value" in str(exc)
    else:
        raise AssertionError("invalid coordinate payload was accepted")
