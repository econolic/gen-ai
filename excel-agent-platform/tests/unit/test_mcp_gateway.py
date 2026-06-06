from app.services.mcp_gateway import _normalize_rows_result, _normalize_tool_result


def test_normalizes_single_text_json_content_block():
    result = _normalize_tool_result([{"type": "text", "text": '{"value": 8848}'}])

    assert result == {"value": 8848}


def test_normalizes_single_text_scalar_content_block():
    result = _normalize_tool_result([{"type": "text", "text": "plain result"}])

    assert result == "plain result"


def test_normalizes_single_row_dict_result():
    result = _normalize_rows_result({"_row_index": 0, "A": 10})

    assert result == [{"_row_index": 0, "A": 10}]
