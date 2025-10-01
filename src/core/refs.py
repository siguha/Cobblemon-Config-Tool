from pathlib import Path

ALLOWED_DIRS = {
    "basic",
    "basic_underground",
    "basic_gym",
    "basic_meteor",
}

def walk_academy_tier_tables(root: Path):
    """
    Return only academy loot tables under the allowed dirs.
    """
    academy_root = root / "data" / "academy" / "loot_table"
    results = []
    for sub in ALLOWED_DIRS:
        subdir = academy_root / sub
        if subdir.exists():
            results.extend(subdir.rglob("*.json"))
    return results

def parse_type_and_tier(path: Path):
    parts = path.parts
    try:
        idx = parts.index("loot_table")
        type_name = parts[idx+1]
        tier = None
        if parts[-1].startswith("t") and parts[-1][1].isdigit():
            tier = int(parts[-1][1])
        return type_name, tier
    except Exception:
        return "unknown", None

def approx_legendary_chance_in_doc(doc, legend_id: str):
    # Very simplified placeholder
    return 0.001

def readable_odds(prob: float):
    if prob <= 0:
        return "0%"
    return f"1/{int(1/prob):,} ({prob*100:.2f}%)"
