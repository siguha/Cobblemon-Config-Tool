from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class TableInfo:
    path: Path
    type_name: str
    tier: int
    chance_value: float
    chance_str: str
    can_edit: bool
    air_weight: Optional[float] = None
    loot_id: Optional[str] = None
