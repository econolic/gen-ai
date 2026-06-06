from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import get_settings


async def save_upload(file: UploadFile) -> Path:
    settings = get_settings()
    settings.ensure_data_dirs()
    suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
    safe_name = f"{uuid4()}{suffix}"
    destination = settings.uploads_dir / safe_name
    content = await file.read()
    destination.write_bytes(content)
    return destination
