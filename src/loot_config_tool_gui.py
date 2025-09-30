#!/usr/bin/env python3
"""
Cobblemon Academy Config Tool

Designed and written to be used by those with zero config background to help customize their servers
and tailor their experience to what they need.

Written by Reese, @sigRao for the Cobblemon Academy community Discord.

Edit this tool however you see fit.

Use
----
With Python installed, you can either directly run the source (this script), or you can run the pre-packaged
executable included in the repository (packed via pyinstaller). Select the base of your datapacks file
(...\datapacks\Acadamey\) and load the tables.

By default, the script will commit the 5 most recent backups. It'll prune any more than that on loadup.
If you need to keep more, you can configure that here. 

Tabs
----
By default, this config tool offers two ways to customize your 

1) Loot Tiers
   - Global / Tier / Specific multipliers
    - E.g: Applying a multiplier of 2 to a tier that has a 1/300 chance of containing a legenadry will result in a 1/150 chance.
   - Direct "Air Weight" editing (in pools that contain the legend subtable)
   - Live preview of odds (old → new)
   - Filter bar, resizable columns, tooltips
   - Apply Changes Globally (included backups)

2) Chest Loot Tables
   - Scrollable, collapsible per-file editor
   - Pools always expanded (per request)
   - Editable weights for every entry
   - Per-chest "Apply" button + backups

Notes
-----
- For some reason, the config files use both minecraft:air and minecraft:empty for void space when weighting
legendary chances. "Empty" in this GUI refers to both, and both are able to be adjusted via this script.
    * {"type": "minecraft:item", "name": "minecraft:air"|"minecraft:empty", "weight": ...}
    * {"type": "minecraft:air"|"minecraft:empty", "weight": ...}
- Multipliers increase legendary odds by dividing the competing "empty" weight
  within pools that ALSO contain the legendary subtable.
- Odds are approximated assuming fixed roll count if uniform(min == max), otherwise 1 roll.

Backups
-------
Saved under ./backups/YYYYMMDD-HHMM/...
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Establishing data types

JSON = Dict[str, Any]

@dataclass
class TableInfo:
    path: Path
    type_name: str
    tier: int
    chance_value: float
    chance_str: str
    can_edit: bool
    air_weight: Optional[float] = None

# Directories under academy/loot_table(s) to exclude ( for some reason I was fetching these and CBA to figure out why :D )
EXCLUDED_TYPE_DIRS = {"cobblemon", "megashowdown", "numismaticoverhaul", "simpletms"}


# File Helpers

def load_json(path: Path) -> Optional[JSON]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to parse JSON: {path} ({e})")
        return None

def save_json(path: Path, data: JSON) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

def ensure_backup(src_path: Path, root: Path, backup_root: Path) -> Path:
    """Copy src_path to mirrored location under backup_root and returns our backup path."""
    rel = src_path.resolve().relative_to(root.resolve())
    dest = backup_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest)
    return dest

def walk_academy_tier_tables(root: Path) -> List[Path]:
    """Return all academy tier JSON files (t*.json) skipping excluded type dirs."""
    out: List[Path] = []
    candidates = [root / "data" / "academy" / "loot_table",
                  root / "data" / "academy" / "loot_tables"]
    for base in candidates:
        if not base.exists():
            continue
        for type_dir in base.iterdir():
            if not type_dir.is_dir():
                continue
            if type_dir.name.lower() in EXCLUDED_TYPE_DIRS:
                continue
            out.extend(sorted(type_dir.glob("t*.json")))
    return out

def parse_type_and_tier(path: Path) -> Tuple[str, int]:
    tname = path.parent.name
    tier = -1
    st = path.stem
    if st.startswith("t"):
        try:
            tier = int(st[1:])
        except ValueError:
            tier = -1
    return tname, tier

def short_display_path(p: Path, anchor: str = "academy") -> str:
    """Return ..\\academy\\...-anchored display path where possible."""
    parts = p.parts
    for i, part in enumerate(parts):
        if part.lower() == anchor:
            return "...\\" + "\\".join(parts[i:])
    # Fallback to last components
    tail = "\\".join(parts[-3:]) if len(parts) >= 3 else str(p)
    return "...\\" + tail


# Loot helpers

def iter_pools(doc: JSON) -> Iterable[JSON]:
    if isinstance(doc.get("pools"), list):
        for p in doc["pools"]:
            if isinstance(p, dict):
                yield p
    elif isinstance(doc.get("entries"), list):
        yield {"entries": doc["entries"], "rolls": doc.get("rolls", 1.0)}

def iter_entries(pool: JSON) -> Iterable[JSON]:
    entries = pool.get("entries")
    if isinstance(entries, list):
        for e in entries:
            if isinstance(e, dict):
                yield e

def is_loot_table_entry(e: JSON) -> bool:
    return e.get("type") == "loot_table" and "value" in e

def is_item_entry(e: JSON, name: Optional[str] = None) -> bool:
    if e.get("type") != "minecraft:item":
        return False
    return (name is None) or (e.get("name") == name)

def is_empty_entry(e: JSON) -> bool:
    """
    True if this entry represents the 'empty' choice competing with legendaries.
    Supports both schemas because for some reason we use both:
      - {"type": "minecraft:item", "name": "minecraft:air"|"minecraft:empty", "weight": ...}
      - {"type": "minecraft:air"|"minecraft:empty", "weight": ...}
    """
    t = e.get("type")
    if t == "minecraft:item":
        return e.get("name") in ("minecraft:air", "minecraft:empty")
    return t in ("minecraft:air", "minecraft:empty")

def entry_weight(e: JSON) -> float:
    try:
        return float(e.get("weight", 1))
    except Exception:
        return 1.0

def set_entry_weight(e: JSON, new_w: float) -> None:
    new_w = max(0.0, float(new_w))
    as_int = int(round(new_w))
    e["weight"] = as_int if abs(new_w - as_int) < 1e-9 else new_w

def extract_rolls_scalar(rolls: Any) -> float:
    """Return a fixed roll count if uniform(min==max), else 1.0 as safe default."""
    if isinstance(rolls, (int, float)):
        return float(rolls)
    if isinstance(rolls, dict) and rolls.get("type") == "minecraft:uniform":
        mn, mx = rolls.get("min"), rolls.get("max")
        if isinstance(mn, (int, float)) and isinstance(mx, (int, float)) and abs(mn - mx) < 1e-9:
            return float(mn)
    return 1.0

def approx_legendary_chance_in_doc(doc: JSON, legend_id: str) -> float:
    """
    Approximate chance of seeing the legendary table at least once across all pools.
    We treat rolls as a fixed scalar when uniform(min==max), otherwise we assume 1 roll.
    """
    combined_nohit, found_any = 1.0, False
    for pool in iter_pools(doc):
        es = list(iter_entries(pool))
        if not es:
            continue
        total = sum(entry_weight(e) for e in es)
        if total <= 0:
            continue
        rolls = extract_rolls_scalar(pool.get("rolls", 1.0))
        direct_w = sum(entry_weight(e) for e in es if is_loot_table_entry(e) and e.get("value") == legend_id)
        p = (direct_w / total) if direct_w > 0 else 0.0
        if p > 0:
            found_any = True
        # clamp rolls >= 0
        r = max(0.0, float(rolls))
        combined_nohit *= (1.0 - p) ** r
    return 0.0 if not found_any else (1.0 - combined_nohit)

def readable_odds(p: float) -> str:
    if p <= 0:
        return "≈ 0, 0%"
    inv = 1.0 / p
    return f"≈ 1/{inv:.0f}, {p*100:.3f}%"

def has_legend_and_empty_pool(doc: JSON, legend_id: str) -> bool:
    """Does any pool contain BOTH the legend subtable and an empty entry?"""
    for pool in iter_pools(doc):
        es = list(iter_entries(pool))
        if not es:
            continue
        if any(is_loot_table_entry(e) and e.get("value") == legend_id for e in es) and \
           any(is_empty_entry(e) for e in es):
            return True
    return False

def find_legend_empty_weight(doc: JSON, legend_id: str) -> Optional[float]:
    """Return 'empty' weight from a pool that also contains the legend subtable, or none if it's missing."""
    for pool in iter_pools(doc):
        es = list(iter_entries(pool))
        if not es:
            continue
        has_legend = any(is_loot_table_entry(e) and str(e.get("value")) == legend_id for e in es)
        if not has_legend:
            continue
        empty_entry = next((e for e in es if is_empty_entry(e)), None)
        if empty_entry is not None:
            return entry_weight(empty_entry)
    return None

def apply_multiplier_to_doc(doc: JSON, legend_id: str, mult: float) -> bool:
    """
    For each pool containing the legend subtable and an empty entry, divide empty's weight by 'mult' therefor increasing chances.
    """
    if mult is None or mult == 1:
        return False
    changed = False
    for pool in iter_pools(doc):
        es = list(iter_entries(pool))
        if not es:
            continue
        if any(is_loot_table_entry(e) and e.get("value") == legend_id for e in es):
            for e in es:
                if is_empty_entry(e):
                    old = entry_weight(e)
                    if mult != 0:
                        new = old / mult
                        if abs(new - old) > 1e-9:
                            set_entry_weight(e, new)
                            changed = True
    return changed


# Tooltips

class Tooltip:
    def __init__(self, widget, text, delay_ms=400):
        self.widget, self.text, self.delay_ms = widget, text, delay_ms
        self.tipwindow = None
        self._after_id = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)

    def _enter(self, _):
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _leave(self, _):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self.text, justify="left", relief="solid", borderwidth=1,
            background="#ffffe0", foreground="#000", font=("Segoe UI", 9)
        ).pack(ipadx=6, ipady=4)

    def _hide(self):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

class HeaderHoverTip:
    """Hover tooltips for Treeview headings."""
    def __init__(self, tree: ttk.Treeview, hints: Dict[str, str]):
        self.tree = tree
        self.hints = hints
        self.tip = None
        self._lbl: Optional[tk.Label] = None
        self._bind()

    def _bind(self):
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", self._on_leave)

    def _on_motion(self, event):
        if self.tree.identify_region(event.x, event.y) != "heading":
            self._hide()
            return
        col = self.tree.identify_column(event.x)
        key = "#0" if col == "#0" else "path" if col == "#1" else "chance" if col == "#2" else "editcol" if col == "#3" else None
        if not key or key not in self.hints:
            self._hide()
            return
        self._show(event.x_root + 12, event.y_root + 8, self.hints[key])

    def _on_leave(self, _):
        self._hide()

    def _show(self, x, y, text: str):
        if self.tip:
            self.tip.geometry(f"+{x}+{y}")
            self._lbl.config(text=text)
            return
        self.tip = tk.Toplevel(self.tree)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        self._lbl = tk.Label(
            self.tip, text=text, justify=tk.LEFT, relief=tk.SOLID, borderwidth=1,
            background="#ffffe0", foreground="#000", font=("Segoe UI", 9)
        )
        self._lbl.pack(ipadx=6, ipady=4)

    def _hide(self):
        if self.tip:
            try:
                self.tip.destroy()
            finally:
                self.tip = None
                self._lbl = None


# App logic

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Config Tool for Cobblemon Academy | by @sigRao")
        self.minsize(1200, 820)

        # shared state
        self.var_root = tk.StringVar(value=os.getcwd())
        self.var_chest_root = tk.StringVar(value=os.getcwd())
        self.var_legend = tk.StringVar(value="academy:myths_and_legends/legendaries") # default myths and legends legendary item, exists in case for some reaosn this ever changes

        # our backup folders
        self.backups_root = Path(os.getcwd()) / "backups"
        self.backups_root.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d-%H%M")
        self.backup_root = self.backups_root / ts
        self.backup_root.mkdir(parents=True, exist_ok=True)

        # pruning so we only keep 5 at a time for sake of storage
        all_backups = sorted([d for d in self.backups_root.iterdir() if d.is_dir()],
                            key=lambda d: d.stat().st_mtime, reverse=True)
        for old in all_backups[5:]:
            shutil.rmtree(old, ignore_errors=True)

        # modes (tab1)
        self.var_mode_global = tk.BooleanVar(value=False)
        self.var_mode_tier = tk.BooleanVar(value=False)
        self.var_mode_specific = tk.BooleanVar(value=False)
        self.var_mode_air = tk.BooleanVar(value=False)

        # multipliers (tab1)
        self.var_global_mult = tk.DoubleVar(value=2.0)
        self.var_tier = tk.IntVar(value=6)
        self.var_tier_mult = tk.DoubleVar(value=2.0)
        self.var_spec_mult = tk.DoubleVar(value=2.0)

        # filter (tab1)
        self.filter_var = tk.StringVar(value="")

        # data (tab1)
        self.tables: List[TableInfo] = []
        self.iid_to_index: Dict[str, int] = {}

        # data (tab2)
        self.chest_rows: Dict[str, Dict[str, Any]] = {}

        self._build_ui()

    # UI comps

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Load from Most Recent Backup",
        command=self._load_from_backup).pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # Tab 1
        tab1 = ttk.Frame(self.nb)
        self.nb.add(tab1, text="Loot Tier Tables")
        self._build_tab1(tab1)

        # Tab 2
        tab2 = ttk.Frame(self.nb)
        self.nb.add(tab2, text="Chest Loot Tables")
        self._build_tab2(tab2)

        # Styles for Tab 2 row shading
        style = ttk.Style(self)
        style.configure("RowOdd.TFrame", background="#f9f9f9")
        style.configure("RowEven.TFrame", background="#ffffff")

    # Tab 1

    def _load_from_backup(self):
        """Prompt user to pick a backup folder and restore its contents into the datapack root."""
        if not self.backups_root.exists():
            messagebox.showerror("No Backups", "No backups directory found.")
            return

        backup_dirs = sorted([d for d in self.backups_root.iterdir() if d.is_dir()],
                            key=lambda d: d.stat().st_mtime, reverse=True)
        if not backup_dirs:
            messagebox.showerror("No Backups", "No backup folders found.")
            return

        # let the user chose a version they want
        choice_win = tk.Toplevel(self)
        choice_win.title("Select Backup to Restore")
        choice_win.geometry("400x250")
        ttk.Label(choice_win, text="Select a backup to restore:", font=("Segoe UI", 10, "bold")).pack(pady=8)

        lb = tk.Listbox(choice_win, height=8)
        for d in backup_dirs:
            lb.insert(tk.END, d.name)
        lb.pack(fill="both", expand=True, padx=12, pady=6)

        def do_restore():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("No Selection", "Please select a backup folder.")
                return
            folder = backup_dirs[sel[0]]
            if not messagebox.askyesno("Confirm Restore", f"Restore files from:\n{folder}?"):
                return
            for src in folder.rglob("*.json"):
                rel = src.relative_to(folder)
                dest = Path(self.var_root.get()).resolve() / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
            messagebox.showinfo("Restore Complete", f"Restored files from:\n{folder}")
            choice_win.destroy()
            # refreshing on load
            self._refresh_tables()
            self._load_chests()

        ttk.Button(choice_win, text="Restore Selected Backup", command=do_restore).pack(pady=6)
        ttk.Button(choice_win, text="Cancel", command=choice_win.destroy).pack()
    
    def _build_tab1(self, parent):
        # header section
        header = ttk.Frame(parent, padding=10)
        header.pack(fill="x")

        ttk.Label(header, text="Datapack Root Folder:").grid(row=0, column=0, sticky="w")
        ent_root = ttk.Entry(header, textvariable=self.var_root, width=70)
        ent_root.grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(header, text="Browse…", command=self._pick_root).grid(row=0, column=2)
        Tooltip(ent_root, "Typically .../datapacks/Academy--we want the ROOT folder, not the data folder.")

        ttk.Label(header, text="Legendary Loot Table ID:").grid(row=1, column=0, sticky="w")
        ent_leg = ttk.Entry(header, textvariable=self.var_legend, width=70)
        ent_leg.grid(row=1, column=1, sticky="we", padx=6, columnspan=2)
        Tooltip(ent_leg, "This is default correct. Don't change this.")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=4)

        # modes section
        controls = ttk.Frame(parent, padding=(10, 6))
        controls.pack(fill="x")

        # global change section
        frm_global = ttk.Frame(controls)
        frm_global.grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(
            frm_global,
            text="Adjust All Tiers and Variations",
            variable=self.var_mode_global,
            command=lambda: self._set_mode("global"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(frm_global, text="Multiplier:").grid(row=0, column=1, padx=(12, 4))
        self.ent_gm = ttk.Entry(frm_global, textvariable=self.var_global_mult, width=8, state="disabled")
        self.ent_gm.grid(row=0, column=2)
        self.ent_gm.bind("<KeyRelease>", lambda e: self._update_dynamic_chances())
        Tooltip(frm_global, "Multiplies all existing weights by X amount. CAREFUL-Changes might not be balanced.")

        # tier section
        frm_tier = ttk.Frame(controls)
        frm_tier.grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(
            frm_tier,
            text="Adjust by Tier",
            variable=self.var_mode_tier,
            command=lambda: self._set_mode("tier"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(frm_tier, text="Tier:").grid(row=0, column=1, padx=(12, 4))
        self.cbo_tier = ttk.Combobox(frm_tier, values=[str(i) for i in range(0, 11)],
                                     width=5, state="disabled", textvariable=self.var_tier)
        self.cbo_tier.grid(row=0, column=2)
        self.cbo_tier.bind("<<ComboboxSelected>>", lambda e: self._update_dynamic_chances())
        ttk.Label(frm_tier, text="Multiplier:").grid(row=0, column=3, padx=(12, 4))
        self.ent_tm = ttk.Entry(frm_tier, textvariable=self.var_tier_mult, width=8, state="disabled")
        self.ent_tm.grid(row=0, column=4)
        self.ent_tm.bind("<KeyRelease>", lambda e: self._update_dynamic_chances())
        Tooltip(frm_tier, "Multiplies all existing weights for a specific tier, across all table variations.")

        # specific tables
        frm_spec = ttk.Frame(controls)
        frm_spec.grid(row=2, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(
            frm_spec,
            text="Adjust Specific Tables (Ctrl+Click to select rows)",
            variable=self.var_mode_specific,
            command=lambda: self._set_mode("specific"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(frm_spec, text="Multiplier:").grid(row=0, column=1, padx=(12, 4))
        self.ent_sm = ttk.Entry(frm_spec, textvariable=self.var_spec_mult, width=8, state="disabled")
        self.ent_sm.grid(row=0, column=2)
        self.ent_sm.bind("<KeyRelease>", lambda e: self._update_dynamic_chances())
        Tooltip(frm_spec, "Multiplies all selected weights by X amount.")

        # fine-tuning air weight options
        frm_air = ttk.Frame(controls)
        frm_air.grid(row=3, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(
            frm_air,
            text="Fine-tune Air Weights",
            variable=self.var_mode_air,
            command=lambda: self._set_mode("air"),
        ).grid(row=0, column=0, sticky="w")
        Tooltip(frm_air, "Allows you to edit the literal chance of a legendary occuring by replacing the multiplier column on the right.")
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)

        # filter
        fbar = ttk.Frame(parent, padding=(10, 4))
        fbar.pack(fill="x")
        ttk.Label(fbar, text="Filter:").pack(side="left")
        ent_filter = ttk.Entry(fbar, textvariable=self.filter_var, width=40)
        ent_filter.pack(side="left", padx=4)
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        ttk.Button(fbar, text="Reset Multipliers", command=self._reset_multipliers).pack(side="right")

        # tree
        body = ttk.Frame(parent, padding=(10, 6))
        body.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(body, columns=("path", "chance", "editcol"),
                                 show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Type")
        self.tree.heading("path", text="Loot Table Path")
        self.tree.heading("chance", text="Chance (≈ 1/N, %)")
        self.tree.heading("editcol", text="Multiplier")  # becomes "Air Weight" in air mode

        self.tree.column("#0", width=180, anchor="w")
        self.tree.column("path", width=600, anchor="w")
        self.tree.column("chance", width=260, anchor="w")
        self.tree.column("editcol", width=140, anchor="w")

        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        # bolding selected entries for readability
        self.tree.tag_configure("changed", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("selected_for_specific", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("tier_target", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("global_target", font=("Segoe UI", 9, "bold"))

        # bindings
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_selection_changed())
        self.tree.bind("<Double-1>", self._on_tree_double_click)  # edit Air/Empty cell in Air mode
        self.tree.bind("<Control-Button-1>", lambda e: None)      # native Ctrl+Click multi-select

        # footer
        footer = ttk.Frame(parent, padding=10)
        footer.pack(fill="x")
        ttk.Button(footer, text="Load / Refresh Tables", command=self._refresh_tables).pack(side="left")
        ttk.Button(footer, text="Apply Changes", command=self._apply_changes).pack(side="right")

        # header tooltips
        HeaderHoverTip(self.tree, hints={
            "#0": "Type (basic, basic_gym, etc.)",
            "path": "Path to the loot table JSON (truncated for readability)",
            "chance": "Current odds (old → preview if pending changes)",
            "editcol": "Multiplier (default) or Air/Empty Weight (in Air mode)",
        })

        # NOTE: Don't auto-load on init to avoid invalid-root popups

    # Tab 1 helpers / interactions

    def _pick_root(self):
        d = filedialog.askdirectory(
            initialdir=self.var_root.get() or os.getcwd(),
            title="Select datapack root (folder containing 'data')",
        )
        if d:
            self.var_root.set(d)

    def _on_tree_selection_changed(self):
        self._update_dynamic_chances()

    def _set_mode(self, which: str):
        modes = ("global", "tier", "specific", "air")
        vals = {m: (m == which) for m in modes}
        self.var_mode_global.set(vals["global"])
        self.var_mode_tier.set(vals["tier"])
        self.var_mode_specific.set(vals["specific"])
        self.var_mode_air.set(vals["air"])

        self.ent_gm.configure(state=("normal" if vals["global"] else "disabled"))
        self.cbo_tier.configure(state=("readonly" if vals["tier"] else "disabled"))
        self.ent_tm.configure(state=("normal" if vals["tier"] else "disabled"))
        self.ent_sm.configure(state=("normal" if vals["specific"] else "disabled"))

        self.tree.heading("editcol", text=("Air Weight" if vals["air"] else "Multiplier"))

        if vals["air"]:
            for iid, idx in self.iid_to_index.items():
                ti = self.tables[idx]
                self.tree.set(iid, "editcol", "" if ti.air_weight is None else str(ti.air_weight))
                self.tree.item(iid, tags=())
        else:
            # Leaving air edit
            for iid in list(self.iid_to_index.keys()):
                if self.tree.exists(iid):
                    self.tree.set(iid, "editcol", "")

        self._update_dynamic_chances()

    def _refresh_tables(self):
        """Load Academy tables, compute baseline chances, populate tree."""
        self.tree.delete(*self.tree.get_children())
        self.tables.clear()
        self.iid_to_index.clear()

        root = Path(self.var_root.get()).resolve()
        if not (root / "data").exists():
            return  # wait for user to pick a root

        legend = (self.var_legend.get() or "").strip() or "academy:myths_and_legends/legendaries"
        paths = walk_academy_tier_tables(root)

        groups: Dict[str, List[TableInfo]] = {}
        for p in paths:
            doc = load_json(p)
            if not doc:
                continue
            tname, tier = parse_type_and_tier(p)
            chance = approx_legendary_chance_in_doc(doc, legend)
            chance_str = readable_odds(chance)
            empty_w = find_legend_empty_weight(doc, legend)
            editable = empty_w is not None
            info = TableInfo(path=p, type_name=tname, tier=tier,
                             chance_value=chance, chance_str=chance_str,
                             can_edit=editable, air_weight=empty_w)
            groups.setdefault(tname, []).append(info)

        for tname in sorted(groups.keys()):
            parent_iid = f"type:{tname}"
            self.tree.insert("", "end", iid=parent_iid, text=tname.title(),
                             values=("", "", ""), open=True)
            for info in sorted(groups[tname], key=lambda ti: (ti.tier, str(ti.path))):
                idx = len(self.tables)
                self.tables.append(info)
                iid = f"row:{idx}"
                self.iid_to_index[iid] = idx
                edit_val = str(info.air_weight) if (self.var_mode_air.get() and info.air_weight is not None) else ""
                self.tree.insert(parent_iid, "end", iid=iid, text="",
                                 values=(short_display_path(info.path), info.chance_str, edit_val))

        self.tree.heading("editcol", text=("Air Weight" if self.var_mode_air.get() else "Multiplier"))

        self._apply_filter(rebuild=False)
        self._update_dynamic_chances()

    def _apply_filter(self, rebuild: bool = True):
        """Filter visible rows and preserve Air/Empty edits and selection."""
        text = (self.filter_var.get() or "").lower()

        existing_edit_vals: Dict[int, str] = {}
        existing_selection = set(self.tree.selection())
        for iid, idx in list(self.iid_to_index.items()):
            if self.tree.exists(iid):
                existing_edit_vals[idx] = self.tree.set(iid, "editcol")

        self.tree.delete(*self.tree.get_children())
        self.iid_to_index.clear()

        grouped: Dict[str, List[int]] = {}
        for idx, ti in enumerate(self.tables):
            path_s = str(ti.path).lower()
            type_s = ti.type_name.lower()
            if (not text) or (text in path_s) or (text in type_s):
                grouped.setdefault(ti.type_name, []).append(idx)

        for tname in sorted(grouped.keys()):
            parent_iid = f"type:{tname}"
            self.tree.insert("", "end", iid=parent_iid, text=tname.title(),
                             values=("", "", ""), open=True)
            for idx in grouped[tname]:
                ti = self.tables[idx]
                row_iid = f"row:{idx}"
                self.iid_to_index[row_iid] = idx

                # prefer edited value if exists else baseline in Air mode
                edit_val = existing_edit_vals.get(idx, "")
                if not edit_val and self.var_mode_air.get() and ti.air_weight is not None:
                    edit_val = str(ti.air_weight)

                self.tree.insert(parent_iid, "end", iid=row_iid, text="",
                                 values=(short_display_path(ti.path), ti.chance_str, edit_val))

        for iid in existing_selection:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

        self.tree.heading("editcol", text=("Air Weight" if self.var_mode_air.get() else "Multiplier"))

    def _update_dynamic_chances(self):
        """Recompute live previews and highlight targets."""
        for iid in list(self.iid_to_index.keys()):
            if self.tree.exists(iid):
                self.tree.item(iid, tags=())

        legend = (self.var_legend.get() or "").strip() or "academy:myths_and_legends/legendaries"

        def preview_for_doc(path: Path,
                            apply_mult: Optional[float] = None,
                            override_empty: Optional[float] = None) -> Optional[str]:
            doc = load_json(path)
            if not doc:
                return None
            if override_empty is not None:
                for pool in iter_pools(doc):
                    es = list(iter_entries(pool))
                    if any(is_loot_table_entry(e) and str(e.get("value")) == legend for e in es):
                        for e in es:
                            if is_empty_entry(e):
                                set_entry_weight(e, override_empty)
            if apply_mult is not None and apply_mult > 0:
                apply_multiplier_to_doc(doc, legend, apply_mult)
            newp = approx_legendary_chance_in_doc(doc, legend)
            return readable_odds(newp)

        mode = ("air" if self.var_mode_air.get() else
                "specific" if self.var_mode_specific.get() else
                "tier" if self.var_mode_tier.get() else
                "global" if self.var_mode_global.get() else
                None)

        try: gmult = float(self.var_global_mult.get())
        except Exception: gmult = None
        try: tmult = float(self.var_tier_mult.get())
        except Exception: tmult = None
        try: smult = float(self.var_spec_mult.get())
        except Exception: smult = None

        selected_iids = set(self.tree.selection())

        for iid, idx in self.iid_to_index.items():
            if not self.tree.exists(iid):
                continue
            ti = self.tables[idx]
            old_str = ti.chance_str
            new_str = None
            tags: List[str] = []

            if mode == "global" and gmult and gmult > 0:
                new_str = preview_for_doc(ti.path, apply_mult=gmult)
                tags.append("global_target")
            elif mode == "tier" and tmult and tmult > 0 and ti.tier == self.var_tier.get():
                new_str = preview_for_doc(ti.path, apply_mult=tmult)
                tags.append("tier_target")
            elif mode == "specific" and smult and smult > 0 and iid in selected_iids:
                new_str = preview_for_doc(ti.path, apply_mult=smult)
                tags.append("selected_for_specific")
            elif mode == "air":
                val = self.tree.set(iid, "editcol")
                if val:
                    try:
                        ew = float(val)
                        new_str = preview_for_doc(ti.path, override_empty=ew)
                        if ti.air_weight is None or abs(ti.air_weight - ew) > 1e-9:
                            tags.append("changed")
                    except Exception:
                        pass

            self.tree.set(iid, "chance", f"{old_str} → {new_str}" if new_str else old_str)

            if tags:
                self.tree.item(iid, tags=tuple(tags))

        self.tree.heading("editcol", text=("Air Weight" if mode == "air" else "Multiplier"))

    def _on_tree_double_click(self, event):
        """In Air mode, edit the 'Air/Empty Weight' cell inline."""
        if not self.var_mode_air.get():
            return
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#3":  # editcol
            return
        iid = self.tree.identify_row(event.y)
        if not iid or iid.startswith("type:"):
            return
        bbox = self.tree.bbox(iid, column="#3")
        if not bbox:
            return
        x, y, w, h = bbox
        cur = self.tree.set(iid, "editcol")
        entry = ttk.Entry(self.tree, width=max(6, int(w / 8)))
        entry.insert(0, cur)
        entry.select_range(0, tk.END)
        entry.focus()
        entry.place(x=x, y=y, width=w, height=h)

        def finish(ok: bool):
            val = entry.get().strip()
            entry.destroy()
            if not ok or not val:
                return
            try:
                f = float(val)
                f = max(0.0, f)
                self.tree.set(iid, "editcol", str(f))
                # mark as changed for visibility
                self.tree.item(iid, tags=("changed",))
            except Exception:
                pass
            self._update_dynamic_chances()

        entry.bind("<Return>", lambda e: finish(True))
        entry.bind("<Escape>", lambda e: finish(False))
        entry.bind("<FocusOut>", lambda e: finish(True))

    def _reset_multipliers(self):
        """Clear selection, edit column, and restore baseline chance text."""
        for iid in self.tree.selection():
            self.tree.selection_remove(iid)
        for iid in list(self.iid_to_index.keys()):
            if self.tree.exists(iid):
                self.tree.set(iid, "editcol", "")
        for iid, idx in self.iid_to_index.items():
            if self.tree.exists(iid):
                self.tree.set(iid, "chance", self.tables[idx].chance_str)
                self.tree.item(iid, tags=())
        self._update_dynamic_chances()

    def _apply_changes(self):
        """Write changes per mode and always backups first."""
        root = Path(self.var_root.get()).resolve()
        legend = (self.var_legend.get() or "").strip() or "academy:myths_and_legends/legendaries"
        if not (root / "data").exists():
            messagebox.showerror("Invalid Root", "Please select a datapack root that contains a 'data' folder.")
            return

        mode = ("air" if self.var_mode_air.get() else
                "specific" if self.var_mode_specific.get() else
                "tier" if self.var_mode_tier.get() else
                "global" if self.var_mode_global.get() else
                None)
        if not mode:
            messagebox.showinfo("Nothing to Apply", "Choose a mode: Global / Tier / Specific / Air Weight.")
            return

        changed = False

        # global changes
        if mode == "global":
            try:
                mult = float(self.var_global_mult.get())
            except Exception:
                mult = None
            if not mult or mult <= 0:
                messagebox.showerror("Invalid", "Global multiplier must be > 0.")
                return
            if not messagebox.askyesno("Confirm Global",
                                       f"Apply global multiplier {mult} to ALL Academy loot tables?"):
                return
            for p in walk_academy_tier_tables(root):
                doc = load_json(p)
                if doc and apply_multiplier_to_doc(doc, legend, mult):
                    ensure_backup(p, root, self.backup_root)
                    save_json(p, doc)
                    changed = True

        # tier changes
        elif mode == "tier":
            try:
                mult = float(self.var_tier_mult.get())
            except Exception:
                mult = None
            tier_sel = self.var_tier.get()
            if not mult or mult <= 0:
                messagebox.showerror("Invalid", "Tier multiplier must be > 0.")
                return
            if not messagebox.askyesno("Confirm Tier",
                                       f"Apply multiplier {mult} to Tier {tier_sel}?"):
                return
            for p in walk_academy_tier_tables(root):
                _, t = parse_type_and_tier(p)
                if t == tier_sel:
                    doc = load_json(p)
                    if doc and apply_multiplier_to_doc(doc, legend, mult):
                        ensure_backup(p, root, self.backup_root)
                        save_json(p, doc)
                        changed = True

        # spec changes
        elif mode == "specific":
            try:
                mult = float(self.var_spec_mult.get())
            except Exception:
                mult = None
            if not mult or mult <= 0:
                messagebox.showerror("Invalid", "Specific multiplier must be > 0.")
                return
            sel = list(self.tree.selection())
            if not sel:
                messagebox.showinfo("No Selection", "Ctrl+Click to select one or more rows first.")
                return
            if not messagebox.askyesno("Confirm Specific",
                                       f"Apply multiplier {mult} to {len(sel)} selected row(s)?"):
                return
            for iid in sel:
                idx = self.iid_to_index.get(iid)
                if idx is None:
                    continue
                ti = self.tables[idx]
                doc = load_json(ti.path)
                if doc and apply_multiplier_to_doc(doc, legend, mult):
                    ensure_backup(ti.path, root, self.backup_root)
                    save_json(ti.path, doc)
                    changed = True

        # air weight editing
        elif mode == "air":
            targets: List[Tuple[str, int, float]] = []
            for iid, idx in self.iid_to_index.items():
                val = self.tree.set(iid, "editcol")
                if not val:
                    continue
                try:
                    ew = max(0.0, float(val))
                except Exception:
                    continue
                targets.append((iid, idx, ew))
            if not targets:
                messagebox.showinfo("No Edits", "No Air/Empty Weight values were entered.")
                return
            if not messagebox.askyesno("Confirm Air/Empty Weights",
                                       f"Apply edits to {len(targets)} row(s)?"):
                return

            for _, idx, ew in targets:
                ti = self.tables[idx]
                doc = load_json(ti.path)
                if not doc:
                    continue
                touched = False
                for pool in iter_pools(doc):
                    es = list(iter_entries(pool))
                    if any(is_loot_table_entry(e) and str(e.get("value")) == legend for e in es):
                        for e in es:
                            if is_empty_entry(e):
                                if abs(entry_weight(e) - ew) > 1e-9:
                                    set_entry_weight(e, ew)
                                    touched = True
                if touched:
                    ensure_backup(ti.path, root, self.backup_root)
                    save_json(ti.path, doc)
                    changed = True

        messagebox.showinfo("Done" if changed else "No Changes",
                            ("Changes applied.\nBackups saved to:\n" + str(self.backup_root)) if changed
                            else "Nothing to update.")
        self._refresh_tables()

    # Tab 2 for chest editing

    def _build_tab2(self, parent):
        # header
        header = ttk.Frame(parent, padding=(10, 10, 10, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Chest Loot Tables Root:").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(header, textvariable=self.var_chest_root, width=70)
        ent.grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(header, text="Browse…", command=self._pick_chest_root).grid(row=0, column=2)

        # scroll box
        container = ttk.Frame(parent, padding=(10, 4))
        container.pack(fill="both", expand=True)
        self.chest_canvas = tk.Canvas(container, highlightthickness=0)
        self.chest_scroll = ttk.Scrollbar(container, orient="vertical", command=self.chest_canvas.yview)
        self.chest_canvas.configure(yscrollcommand=self.chest_scroll.set)
        self.chest_canvas.pack(side="left", fill="both", expand=True)
        self.chest_scroll.pack(side="right", fill="y")

        self.chest_frame = ttk.Frame(self.chest_canvas)
        self.chest_window = self.chest_canvas.create_window((0, 0), window=self.chest_frame, anchor="nw")

        self.chest_frame.bind("<Configure>",
            lambda e: self.chest_canvas.configure(scrollregion=self.chest_canvas.bbox("all")))
        self.chest_canvas.bind("<Configure>",
            lambda e: self.chest_canvas.itemconfigure(self.chest_window, width=e.width))

        # footer buttons
        footer = ttk.Frame(parent, padding=10)
        footer.pack(fill="x")
        ttk.Button(footer, text="Load Chest Tables", command=self._load_chests).pack(side="left")

    def _pick_chest_root(self):
        d = filedialog.askdirectory(
            initialdir=self.var_chest_root.get() or os.getcwd(),
            title="Select datapack root for chests",
        )
        if d:
            self.var_chest_root.set(d)

    def _load_chests(self):
        for child in self.chest_frame.winfo_children():
            child.destroy()
        self.chest_rows.clear()

        root = Path(self.var_chest_root.get()).resolve()
        chest_dir = root / "data" / "minecraft" / "loot_table" / "chests"
        alt_dir   = root / "data" / "minecraft" / "loot_tables" / "chests"  # plural fallback
        base = chest_dir if chest_dir.exists() else alt_dir
        if not base.exists():
            messagebox.showerror("No Chest Folder",
                                 "Couldn't find data/minecraft/loot_table(s)/chests in the selected datapack.")
            return

        for p in sorted(base.glob("*.json")):
            self._add_chest_row(p, root)

    def _add_chest_row(self, path: Path, pack_root: Path):
        outer = ttk.Frame(self.chest_frame, relief="groove", borderwidth=1, padding=4)
        outer.pack(fill="x", pady=4)

        header = ttk.Frame(outer)
        header.pack(fill="x")

        # truncating the file path to make things a bit more readable
        parts = path.parts
        try:
            i = next(i for i, part in enumerate(parts) if part.lower() == "chests")
            display_path = "...\\" + "\\".join(parts[i:])
        except StopIteration:
            display_path = str(path)

        folder = os.path.dirname(display_path)
        filename = os.path.basename(display_path)

        # bolding the file name for additional readability
        lbl = ttk.Label(header, text=folder + "\\")
        lbl.pack(side="left", padx=(6, 0))
        lbl_file = ttk.Label(header, text=filename, font=("Segoe UI", 9, "bold"))
        lbl_file.pack(side="left")

        toggle_btn = ttk.Button(header, width=3, text="+",
                                command=lambda: self._toggle_chest_row(path, pack_root))
        toggle_btn.pack(side="right", padx=4)

        details = ttk.Frame(outer)
        details.pack(fill="x", padx=12, pady=(4, 0))
        details.pack_forget()  # start collapsed

        self.chest_rows[str(path)] = {
            "outer": outer,
            "details": details,
            "expanded": False,
            "toggle_btn": toggle_btn,
            "root": pack_root,
            "controls": [],   # list of (pool_index, entry_index, weight_var)
            "path": path,
        }


    def _toggle_chest_row(self, path: Path, pack_root: Path):
        row = self.chest_rows.get(str(path))
        if not row:
            return
        if row["expanded"]:
            row["details"].pack_forget()
            row["toggle_btn"].configure(text="+")
            row["expanded"] = False
            return

        # expand and rebuild UI
        for child in row["details"].winfo_children():
            child.destroy()
        row["controls"].clear()

        doc = load_json(path)
        if doc is None:
            ttk.Label(row["details"], text="(Failed to parse JSON)").pack(anchor="w")
        else:
            pool_list = list(iter_pools(doc))
            if not pool_list:
                ttk.Label(row["details"], text="(No pools / entries)").pack(anchor="w")
            else:
                hdr = ttk.Frame(row["details"])
                hdr.pack(fill="x", pady=(2, 2))
                ttk.Label(hdr, text="Pool", width=6).grid(row=0, column=0, sticky="w")
                ttk.Label(hdr, text="Type", width=12).grid(row=0, column=1, sticky="w")
                ttk.Label(hdr, text="ID (value/name)", width=40).grid(row=0, column=2, sticky="w")
                ttk.Label(hdr, text="Weight", width=10).grid(row=0, column=3, sticky="w")

                # alternative shading for style here again, for readability
                for pi, pool in enumerate(pool_list):
                    entries = list(iter_entries(pool))
                    for ei, e in enumerate(entries):
                        style = "RowOdd.TFrame" if (ei % 2 == 0) else "RowEven.TFrame"
                        line = ttk.Frame(row["details"], style=style)
                        line.pack(fill="x", pady=1)
                        etype = e.get("type", "")
                        eid = e.get("value") if etype == "loot_table" else e.get("name", "")
                        w = entry_weight(e)
                        ttk.Label(line, text=str(pi), width=6).grid(row=0, column=0, sticky="w")
                        ttk.Label(line, text=str(etype), width=12).grid(row=0, column=1, sticky="w")
                        ttk.Label(line, text=str(eid), width=40).grid(row=0, column=2, sticky="w")
                        wvar = tk.StringVar(value=str(w))
                        ttk.Entry(line, textvariable=wvar, width=10).grid(row=0, column=3, sticky="w")
                        row["controls"].append((pi, ei, wvar))

        btn_bar = ttk.Frame(row["details"])
        btn_bar.pack(fill="x", pady=(6, 2))
        ttk.Button(btn_bar, text="Apply", command=lambda: self._apply_chest(path)).pack(side="right")

        row["details"].pack(fill="x")
        row["toggle_btn"].configure(text="–")
        row["expanded"] = True

    def _apply_chest(self, path: Path):
        """Apply weight edits to one chest JSON, with backup and inline refresh."""
        row = self.chest_rows.get(str(path))
        if not row:
            return

        doc = load_json(path)
        if doc is None:
            messagebox.showerror("Error", f"Failed to parse {path}")
            return

        if isinstance(doc.get("pools"), list):
            pools_ref = doc["pools"]   # type: ignore
        elif isinstance(doc.get("entries"), list):
            pools_ref = [{"entries": doc.get("entries")}]
        else:
            pools_ref = []

        changed = False
        for (pi, ei, wvar) in row["controls"]:
            try:
                new_w = max(0.0, float(wvar.get().strip()))
            except Exception:
                continue
            try:
                entry = pools_ref[pi]["entries"][ei]
            except Exception:
                continue
            if abs(entry_weight(entry) - new_w) > 1e-9:
                set_entry_weight(entry, new_w)
                changed = True

        if not changed:
            messagebox.showinfo("No Changes", "No weight changes detected for this chest.")
            return

        if not messagebox.askyesno("Confirm Apply",
                                   f"Apply changes to:\n{path}\n\nThis will write the JSON (backup will be created)."):
            return

        ensure_backup(path, row["root"], self.backup_root)
        save_json(path, doc)

        # Refresh only this row
        if row["expanded"]:
            self._toggle_chest_row(path, row["root"])
            self._toggle_chest_row(path, row["root"])

        messagebox.showinfo("Done", f"Saved changes for:\n{path}\nBackup in:\n{self.backup_root}")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()