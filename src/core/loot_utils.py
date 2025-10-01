from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional

# json helpers
def iter_pools(doc: dict) -> Iterable[dict]:
    return doc.get("pools", [])

def iter_entries(pool: dict) -> Iterable[dict]:
    return pool.get("entries", [])

def is_loot_table_entry(e: dict) -> bool:
    return e.get("type") == "loot_table"

def is_item_entry(e: dict, name: Optional[str] = None) -> bool:
    if e.get("type") != "minecraft:item":
        return False
    if name is None:
        return True
    return e.get("name") == name

def is_empty_entry(e: dict) -> bool:
    return is_item_entry(e, "minecraft:air") or is_item_entry(e, "minecraft:empty")

def entry_weight(e: dict) -> float:
    w = e.get("weight", 1.0)
    try:
        return float(w)
    except Exception:
        return 1.0

def set_entry_weight(e: dict, w: float):
    e["weight"] = float(w)

# loot id

def parse_type_and_tier(path: Path):
    """
    Given .../data/academy/loot_table/<type>/<maybe_subdirs>/tX.json -> returns (type, X)
    If no tX.json pattern, tier=None.
    """
    parts = path.parts
    type_name = "unknown"
    tier = None
    if "loot_table" in parts:
        i = parts.index("loot_table")
        if i + 1 < len(parts):
            type_name = parts[i + 1]
    # tier by filename tN.json
    stem = path.stem  # e.g., t7
    if len(stem) >= 2 and stem[0].lower() == "t" and stem[1:].isdigit():
        tier = int(stem[1:])
    return type_name, tier

def loot_table_id_from_path(root: Path, p: Path) -> Optional[str]:
    """Produce namespace:path from data/<ns>/loot_table/.../<file>.json"""
    try:
        rel = p.relative_to(root / "data")
    except Exception:
        return None
    parts = rel.parts
    if len(parts) < 3:  # <ns>/loot_table/<...>
        return None
    ns = parts[0]
    sub = "/".join(parts[2:])
    if sub.endswith(".json"):
        sub = sub[:-5]
    return f"{ns}:{sub}".lower()

# chance calc

def approx_legendary_chance_in_doc(doc: dict, legend_id: str) -> float:
    """
    Approximate chance that any roll yields the legendary subtable in this loot table.
    We assume:
      - Any pool that contains a 'loot_table' entry w/ value==legend_id 'wins' that roll.
      - We compute relative weight per pool (legend weight / sum weights in that pool),
        then combine across pools as 1 - Π(1 - p_pool).
    """
    try:
        pid = legend_id.strip().lower()
    except Exception:
        pid = "academy:myths_and_legends/legendaries"

    p_noloot = 1.0
    for pool in iter_pools(doc):
        total = 0.0
        legend_w = 0.0
        for e in iter_entries(pool):
            w = entry_weight(e)
            total += w
            if is_loot_table_entry(e) and (e.get("value", "").lower() == pid):
                legend_w += w
        if total > 0 and legend_w > 0:
            p_pool = legend_w / total
            p_noloot *= (1.0 - p_pool)
    return 1.0 - p_noloot

def readable_odds(p: float) -> str:
    if p <= 0:
        return "≈ 0% (never)"
    inv = round(1.0 / p) if p > 0 else 0
    return f"≈ 1/{inv:,} ({p*100:.2f}%)"

# edits

def apply_multiplier_to_doc(doc: dict, legend_id: str, mult: float) -> bool:
    """
    Multiply the 'minecraft:air'/'minecraft:empty' weights in any pool that also
    contains the legend loot_table entry `legend_id`. Returns True if changed.
    """
    changed = False
    pid = (legend_id or "").strip().lower()
    for pool in iter_pools(doc):
        has_leg = any(is_loot_table_entry(e) and e.get("value", "").lower() == pid
                      for e in iter_entries(pool))
        if not has_leg:
            continue
        for e in iter_entries(pool):
            if is_empty_entry(e):
                old = entry_weight(e)
                neww = max(0.0, old / max(1e-12, mult))  # multiply chance => divide empty
                if abs(neww - old) > 1e-9:
                    set_entry_weight(e, neww)
                    changed = True
    return changed

def find_legend_empty_weight(doc: dict, legend_id: str):
    """Find the first empty (air/empty) weight in a pool that also contains legend_id."""
    pid = (legend_id or "").strip().lower()
    for pool in iter_pools(doc):
        has_leg = any(is_loot_table_entry(e) and e.get("value", "").lower() == pid
                      for e in iter_entries(pool))
        if not has_leg:
            continue
        for e in iter_entries(pool):
            if is_empty_entry(e):
                return entry_weight(e)
    return None

# walker

def walk_academy_tier_tables(root: Path):
    """
    Return all academy loot table JSON files under data/academy/loot_table/, excluding
    non-target namespaces or stray folders you previously flagged.
    """
    base = root / "data" / "academy" / "loot_table"
    if not base.exists():
        return []
    return sorted(base.rglob("*.json"))
