import pytest

from app.schemas.dsl import DSLPlan
from app.schemas.errors import ToolEnvelope
from app.graph.nodes import EXECUTOR_REGISTRY
from app.tools.local_calc import execute_formula_dsl, haversine_km, validate_formula_expression


def test_haversine_distance_is_reasonable_for_kyiv_paris():
    distance = haversine_km(50.4501, 30.5234, 48.8566, 2.3522)
    assert 1900 <= distance <= 2100


def test_dsl_rejects_eval_tokens():
    with pytest.raises(ValueError):
        DSLPlan(type="formula", target_column="x", expression="eval('1 + 1')")


def test_ast_validator_rejects_attribute_access():
    with pytest.raises(ValueError):
        validate_formula_expression("__import__('os').system('echo nope')")


def test_error_envelope_shape():
    envelope = ToolEnvelope.failure("NOT_FOUND", "No fact found", source="unit-test")
    assert envelope.ok is False
    assert envelope.error is not None
    assert envelope.error.code == "NOT_FOUND"
    assert envelope.meta.source == "unit-test"


def test_formula_dsl_executes_safe_expression():
    dsl = DSLPlan(type="formula", target_column="Value", expression="A + B")
    assert execute_formula_dsl([{"A": 2, "B": 3, "_row_index": 0}], dsl) == [5]


def test_executor_registry_exposes_core_dsl_operations():
    assert {"formula", "group_share", "lookup", "distance"}.issubset(EXECUTOR_REGISTRY)


def test_formula_dsl_executes_col_function():
    dsl = DSLPlan(type="formula", target_column="Value", expression="col('A B') + col('C-D')")
    rows = [{"A B": 10, "C-D": 20, "_row_index": 0}]
    assert execute_formula_dsl(rows, dsl) == [30]


def test_formula_dsl_executes_math_helpers():
    dsl = DSLPlan(type="formula", target_column="Value", expression="div(mul(add(col('A'), 10), sub(col('B'), 5)), 2)")
    rows = [{"A": 10, "B": 9, "_row_index": 0}]
    assert execute_formula_dsl(rows, dsl) == [40.0]


def test_extract_coordinates_safety():
    from app.graph.nodes import _extract_coordinates
    assert _extract_coordinates({"lat": 50.45, "lon": 30.52}) == (50.45, 30.52)
    assert _extract_coordinates({"lat": "50.45", "lon": "30.52"}) == (50.45, 30.52)
    assert _extract_coordinates(50.45) is None
    assert _extract_coordinates({"lat": 50.45}) is None
    assert _extract_coordinates({"lat": 50.45, "lon": "invalid"}) is None
    assert _extract_coordinates({"lat": 100.0, "lon": 30.52}) is None
