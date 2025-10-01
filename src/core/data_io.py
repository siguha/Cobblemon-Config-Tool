import json
from pathlib import Path

def load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def ensure_backup(path: Path, root: Path, backup_root: Path):
    backup_root.mkdir(parents=True, exist_ok=True)
    rel = path.relative_to(root)
    backup_path = backup_root / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not backup_path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
