from mcp.server.fastmcp import FastMCP
from pathlib import Path

from app.config import get_settings
from app.schemas.run import CellUpdate
from app.tools.local_excel import preview_rows, profile_workbook, read_rows, write_enriched_workbook

mcp = FastMCP("excel-mcp-server", host="0.0.0.0", port=8101)


def _sandbox_path(file_path: str) -> str:
    data_dir = get_settings().data_dir.resolve()
    path = data_dir.joinpath(file_path).resolve() if not file_path.startswith("/") else Path(file_path).resolve()
    if data_dir != path and data_dir not in path.parents:
        raise ValueError("Excel MCP paths must stay inside DATA_DIR")
    return str(path)


@mcp.tool()
def profile_workbook_tool(file_path: str) -> dict:
    """Read workbook sheets, columns, null counts, and sample rows."""

    return profile_workbook(_sandbox_path(file_path)).model_dump()


@mcp.tool()
def read_rows_tool(file_path: str, sheet_name: str | None = None) -> list[dict]:
    """Read non-empty rows from a workbook sheet."""

    return read_rows(_sandbox_path(file_path), sheet_name)


@mcp.tool()
def preview_rows_tool(file_path: str, limit: int = 20, sheet_name: str | None = None) -> list[dict]:
    """Read a limited preview from a workbook sheet."""

    return preview_rows(_sandbox_path(file_path), limit, sheet_name)


@mcp.tool()
def write_enriched_workbook_tool(
    input_path: str,
    output_path: str,
    updates: list[dict],
    sheet_name: str | None = None,
) -> str:
    """Write target-cell updates into a copy of the workbook."""

    parsed_updates = [CellUpdate.model_validate(update) for update in updates]
    return write_enriched_workbook(
        _sandbox_path(input_path),
        _sandbox_path(output_path),
        parsed_updates,
        sheet_name,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
