import shutil
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

def clean_directory(dir_path: Path):
    if not dir_path.exists():
        return
    for item in dir_path.iterdir():
        if item.name == ".gitkeep":
            continue
        if item.is_dir():
            print(f"Removing directory: {item}")
            shutil.rmtree(item)
        else:
            print(f"Removing file: {item}")
            item.unlink()

def clean_reports_directory(dir_path: Path):
    if not dir_path.exists():
        return
    for item in dir_path.iterdir():
        if item.name == ".gitkeep":
            continue
        if item.name == "screenshots" and item.is_dir():
            clean_screenshots_directory(item)
            continue
        if item.is_dir():
            print(f"Removing directory: {item}")
            shutil.rmtree(item)
        else:
            print(f"Removing file: {item}")
            item.unlink()

def clean_screenshots_directory(dir_path: Path):
    for item in dir_path.iterdir():
        if item.is_file() and item.suffix.lower() == ".png":
            print(f"Keeping submission screenshot: {item}")
            continue
        if item.is_dir():
            print(f"Removing runtime screenshot directory: {item}")
            shutil.rmtree(item)
        else:
            print(f"Removing runtime screenshot artifact: {item}")
            item.unlink()

def clean_pycache(root_dir: Path):
    for path in root_dir.rglob("__pycache__"):
        if path.is_dir():
            print(f"Removing pycache: {path}")
            shutil.rmtree(path)

def main():
    print("Starting cleanup of runtime artifacts...")

    # Clean data databases & files
    db_path = DATA_DIR / "app.db"
    if db_path.exists():
        print(f"Removing database: {db_path}")
        db_path.unlink()

    strict_test_file = DATA_DIR / "strict_mcp_mountains.xlsx"
    if strict_test_file.exists():
        print(f"Removing strict workbook: {strict_test_file}")
        strict_test_file.unlink()

    # Clean subdirectories in data/
    for sub in ["uploads", "outputs", "cache"]:
        clean_directory(DATA_DIR / sub)
    clean_reports_directory(DATA_DIR / "reports")

    # Clean __pycache__ folders
    clean_pycache(PROJECT_ROOT)

    print("Cleanup complete!")

if __name__ == "__main__":
    main()
