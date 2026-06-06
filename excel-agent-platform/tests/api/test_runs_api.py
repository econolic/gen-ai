from pathlib import Path
from shutil import copyfile

from fastapi.responses import FileResponse
from openpyxl import Workbook

from app.api.runs import download_output, download_report, get_plan, get_preview, get_run
from app.config import get_settings
from app.services.run_store import run_store
from app.services.runner import analyze_run, execute_run


ROOT_DIR = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures"


def test_runs_api_status_preview_and_download(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    upload_path = tmp_path / "uploads" / "mountains.xlsx"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    copyfile(FIXTURES_DIR / "mountains.xlsx", upload_path)

    status = run_store.create(
        str(upload_path),
        "add the height of the mountains in meters to the column height",
    )
    execute_run(status.run_id, str(upload_path), status.task_description or "")

    current = get_run(status.run_id)
    assert current.state == "completed"
    assert current.plan is not None
    assert current.plan.operation == "lookup"

    plan = get_plan(status.run_id)
    assert plan.target_column == "height"

    preview = get_preview(status.run_id)
    assert preview["rows"][0]["height"] == 8848

    output_response = download_output(status.run_id)
    report_response = download_report(status.run_id)
    assert isinstance(output_response, FileResponse)
    assert isinstance(report_response, FileResponse)


def test_run_waits_for_clarification_when_task_is_unclear(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    upload_path = tmp_path / "uploads" / "unclear.xlsx"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Name", "Value"])
    sheet.append(["A", None])
    workbook.save(upload_path)

    status = run_store.create(str(upload_path), "make it pretty")
    execute_run(status.run_id, str(upload_path), status.task_description or "")

    current = get_run(status.run_id)
    assert current.state == "awaiting_clarification"
    assert current.clarification_question
    assert current.plan is not None
    assert current.plan.route.route == "CLARIFICATION_REQUIRED"


def test_risky_run_waits_for_approval_then_executes(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MCP_STRICT_TOOLS", "false")
    get_settings.cache_clear()

    upload_path = tmp_path / "uploads" / "mountains.xlsx"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    copyfile(FIXTURES_DIR / "mountains.xlsx", upload_path)

    status = run_store.create(
        str(upload_path),
        "add the height of the mountains in meters to the column height",
    )
    assert analyze_run(status.run_id, str(upload_path), status.task_description or "") is True

    awaiting = get_run(status.run_id)
    assert awaiting.state == "awaiting_approval"
    assert awaiting.plan is not None
    assert awaiting.plan.operation == "lookup"

    execute_run(status.run_id, str(upload_path), status.task_description or "")
    completed = get_run(status.run_id)
    assert completed.state == "completed"
    assert completed.preview[0]["height"] == 8848
