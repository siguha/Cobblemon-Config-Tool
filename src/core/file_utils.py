import json, os
from pathlib import Path

def load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def ensure_backup(path: Path, pack_root: Path, backup_root: Path):
    """Copy the original file to backup_root/<rel> if not already backed up for this run."""
    rel = path.relative_to(pack_root)
    dest = backup_root / rel
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

def short_display_path(p: Path) -> str:
    parts = p.parts
    try:
        idx = next(i for i, part in enumerate(parts) if part.lower() in ("loot_table", "loot_tables"))
        return f"...\\{os.path.join(*parts[idx:])}"
    except StopIteration:
        return str(p)
