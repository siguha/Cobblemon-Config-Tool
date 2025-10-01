import os, subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Dict, List, Optional

from gui.common import Tooltip, HeaderHoverTip
from core.model import TableInfo
from core.file_utils import load_json, save_json, ensure_backup, short_display_path
from core.loot_utils import (
    iter_pools, iter_entries, is_item_entry, is_loot_table_entry, is_empty_entry,
    entry_weight, set_entry_weight, parse_type_and_tier,
    loot_table_id_from_path, approx_legendary_chance_in_doc,
    readable_odds, apply_multiplier_to_doc, find_legend_empty_weight
)
from core.refs import walk_academy_tier_tables


def build_tab1(app, parent):
    """Tab 1: Loot Tier Tables (IDENTICAL behavior/format to your working monolith)."""
    # --- Header ---
    header = ttk.Frame(parent, padding=10)
    header.pack(fill="x")

    ttk.Label(header, text="Datapack Root Folder:").grid(row=0, column=0, sticky="w")
    ent_root = ttk.Entry(header, textvariable=app.var_root, width=70)
    ent_root.grid(row=0, column=1, sticky="we", padx=6)
    ttk.Button(header, text="Browse…", command=lambda: _pick_root(app)).grid(row=0, column=2)
    Tooltip(ent_root, "Typically .../datapacks/Academy — select the ROOT that contains 'data'.")

    ttk.Label(header, text="Legendary Loot Table ID:").grid(row=1, column=0, sticky="w")
    ent_leg = ttk.Entry(header, textvariable=app.var_legend, width=70)
    ent_leg.grid(row=1, column=1, sticky="we", padx=6, columnspan=2)
    Tooltip(ent_leg, "Default is correct: academy:myths_and_legends/legendaries")

    ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=4)

    # --- Modes / Controls ---
    controls = ttk.Frame(parent, padding=(10, 6))
    controls.pack(fill="x")

    # Global
    frm_global = ttk.Frame(controls)
    frm_global.grid(row=0, column=0, sticky="w", padx=4, pady=2)
    ttk.Checkbutton(frm_global, text="Adjust All Tiers and Variations",
                    variable=app.var_mode_global,
                    command=lambda: _set_mode(app, "global")).grid(row=0, column=0, sticky="w")
    ttk.Label(frm_global, text="Multiplier:").grid(row=0, column=1, padx=(12, 4))
    app.ent_gm = ttk.Entry(frm_global, textvariable=app.var_global_mult, width=8, state="disabled")
    app.ent_gm.grid(row=0, column=2)
    app.ent_gm.bind("<KeyRelease>", lambda e: _update_dynamic_chances(app))
    Tooltip(frm_global, "Multiply odds everywhere by this factor (2.0 ≈ doubles odds).")

    # Tier
    frm_tier = ttk.Frame(controls)
    frm_tier.grid(row=1, column=0, sticky="w", padx=4, pady=2)
    ttk.Checkbutton(frm_tier, text="Adjust by Tier",
                    variable=app.var_mode_tier,
                    command=lambda: _set_mode(app, "tier")).grid(row=0, column=0, sticky="w")
    ttk.Label(frm_tier, text="Tier:").grid(row=0, column=1, padx=(12, 4))
    app.cbo_tier = ttk.Combobox(frm_tier, values=[str(i) for i in range(0, 11)],
                                width=5, state="disabled", textvariable=app.var_tier)
    app.cbo_tier.grid(row=0, column=2)
    app.cbo_tier.bind("<<ComboboxSelected>>", lambda e: _update_dynamic_chances(app))
    ttk.Label(frm_tier, text="Multiplier:").grid(row=0, column=3, padx=(12, 4))
    app.ent_tm = ttk.Entry(frm_tier, textvariable=app.var_tier_mult, width=8, state="disabled")
    app.ent_tm.grid(row=0, column=4)
    app.ent_tm.bind("<KeyRelease>", lambda e: _update_dynamic_chances(app))
    Tooltip(frm_tier, "Multiply odds for just this tier across all variants.")

    # Specific
    frm_spec = ttk.Frame(controls)
    frm_spec.grid(row=2, column=0, sticky="w", padx=4, pady=2)
    ttk.Checkbutton(frm_spec, text="Adjust Specific Tables (Ctrl+Click select rows)",
                    variable=app.var_mode_specific,
                    command=lambda: _set_mode(app, "specific")).grid(row=0, column=0, sticky="w")
    ttk.Label(frm_spec, text="Multiplier:").grid(row=0, column=1, padx=(12, 4))
    app.ent_sm = ttk.Entry(frm_spec, textvariable=app.var_spec_mult, width=8, state="disabled")
    app.ent_sm.grid(row=0, column=2)
    app.ent_sm.bind("<KeyRelease>", lambda e: _update_dynamic_chances(app))
    Tooltip(frm_spec, "Multiplier applied to all selected rows.")

    # Air/Empty direct weight mode
    frm_air = ttk.Frame(controls)
    frm_air.grid(row=3, column=0, sticky="w", padx=4, pady=2)
    ttk.Checkbutton(frm_air, text="Fine-tune Air/Empty Weights",
                    variable=app.var_mode_air,
                    command=lambda: _set_mode(app, "air")).grid(row=0, column=0, sticky="w")
    Tooltip(frm_air, "Replaces the Multiplier column with a direct Air/Empty weight editor.")

    ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=6)

    # --- Filter ---
    fbar = ttk.Frame(parent, padding=(10, 4))
    fbar.pack(fill="x")
    ttk.Label(fbar, text="Filter:").pack(side="left")
    ent_filter = ttk.Entry(fbar, textvariable=app.filter_var, width=40)
    ent_filter.pack(side="left", padx=4)
    app.filter_var.trace_add("write", lambda *_: _apply_filter(app))
    ttk.Button(fbar, text="Reset Multipliers", command=lambda: _reset_multipliers(app)).pack(side="right")

    # --- Body: PanedWindow (Tree + References panel) ---
    app.body_pane = ttk.Panedwindow(parent, orient="horizontal")
    app.body_pane.pack(fill="both", expand=True, padx=6, pady=6)

    left = ttk.Frame(app.body_pane)
    app.tree = ttk.Treeview(left, columns=("path", "chance", "editcol"),
                            show="tree headings", selectmode="extended")
    app.tree.heading("#0", text="Type")
    app.tree.heading("path", text="Loot Table Path")
    app.tree.heading("chance", text="Chance (≈ 1/N, %)")
    app.tree.heading("editcol", text="Multiplier")  # toggles to Air/Empty Weight

    app.tree.column("#0", width=180, anchor="w")
    app.tree.column("path", width=600, anchor="w")
    app.tree.column("chance", width=260, anchor="w")
    app.tree.column("editcol", width=140, anchor="w")

    vsb = ttk.Scrollbar(left, orient="vertical", command=app.tree.yview)
    hsb = ttk.Scrollbar(left, orient="horizontal", command=app.tree.xview)
    app.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
    app.tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    left.rowconfigure(0, weight=1)
    left.columnconfigure(0, weight=1)

    app.body_pane.add(left, weight=3)

    # Right references panel (hidden until selection has refs)
    app.refs_panel = ttk.Frame(app.body_pane, relief="sunken", padding=6)
    app.refs_label = ttk.Label(app.refs_panel, text="References:", font=("Segoe UI", 10, "bold"))
    app.refs_label.pack(anchor="w")
    app.refs_list = tk.Listbox(app.refs_panel)
    app.refs_list.pack(fill="both", expand=True, pady=4)
    app.refs_list_paths = []

    def open_selected(_):
        sel = app.refs_list.curselection()
        if not sel: return
        full_path = app.refs_list_paths[sel[0]]
        try:
            subprocess.Popen(["notepad.exe", full_path])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open {full_path}\n{e}")
    app.refs_list.bind("<Double-1>", open_selected)

    # tags + bindings
    app.tree.tag_configure("changed", font=("Segoe UI", 9, "bold"))
    app.tree.tag_configure("selected_for_specific", font=("Segoe UI", 9, "bold"))
    app.tree.tag_configure("tier_target", font=("Segoe UI", 9, "bold"))
    app.tree.tag_configure("global_target", font=("Segoe UI", 9, "bold"))

    app.tree.bind("<<TreeviewSelect>>", lambda e: _on_tree_selection_changed(app))
    app.tree.bind("<Double-1>", lambda e: _on_tree_double_click(app, e))
    app.tree.bind("<Control-Button-1>", lambda e: None)

    # --- Footer ---
    footer = ttk.Frame(parent, padding=10)
    footer.pack(fill="x")
    ttk.Button(footer, text="Load / Refresh Tables", command=lambda: _refresh_tables(app)).pack(side="left")
    ttk.Button(footer, text="Apply Changes", command=lambda: _apply_changes(app)).pack(side="right")

    HeaderHoverTip(app.tree, hints={
        "#0": "Type (basic, basic_gym, etc.)",
        "path": "Path to loot table JSON (truncated)",
        "chance": "Current odds (old → preview if pending changes)",
        "editcol": "Multiplier (default) or Air/Empty Weight (Air mode)",
    })

    # do NOT auto-load: avoid early invalid-root popups

# ===== Tab 1 helpers =====

def _pick_root(app):
    d = filedialog.askdirectory(initialdir=app.var_root.get() or os.getcwd(),
                                title="Select datapack root (contains 'data')")
    if d:
        app.var_root.set(d)

def _set_mode(app, which: str):
    modes = ("global", "tier", "specific", "air")
    val = {m: (m == which) for m in modes}
    app.var_mode_global.set(val["global"])
    app.var_mode_tier.set(val["tier"])
    app.var_mode_specific.set(val["specific"])
    app.var_mode_air.set(val["air"])
    app.ent_gm.configure(state=("normal" if val["global"] else "disabled"))
    app.cbo_tier.configure(state=("readonly" if val["tier"] else "disabled"))
    app.ent_tm.configure(state=("normal" if val["tier"] else "disabled"))
    app.ent_sm.configure(state=("normal" if val["specific"] else "disabled"))
    app.tree.heading("editcol", text=("Air/Empty Weight" if val["air"] else "Multiplier"))
    # clear edit column when leaving air mode
    if not val["air"]:
        for iid in list(app.iid_to_index.keys()):
            if app.tree.exists(iid):
                app.tree.set(iid, "editcol", "")
    _update_dynamic_chances(app)

def _apply_filter(app, rebuild=True):
    text = (app.filter_var.get() or "").lower()
    # selection preserve
    selected = set(app.tree.selection())
    app.tree.delete(*app.tree.get_children())
    grouped: Dict[str, List[int]] = {}
    for idx, ti in enumerate(app.tables):
        if not text or (text in str(ti.path).lower()) or (text in ti.type_name.lower()):
            grouped.setdefault(ti.type_name, []).append(idx)
    for tname in sorted(grouped.keys()):
        pid = f"type:{tname}"
        app.tree.insert("", "end", iid=pid, text=tname.title(), values=("", "", ""), open=True)
        for idx in grouped[tname]:
            ti = app.tables[idx]
            iid = f"row:{idx}"
            app.iid_to_index[iid] = idx
            app.tree.insert(pid, "end", iid=iid, text="",
                            values=(short_display_path(ti.path), ti.chance_str, ""))
    for iid in selected:
        if app.tree.exists(iid):
            app.tree.selection_add(iid)

def _reset_multipliers(app):
    for iid in app.tree.selection():
        app.tree.selection_remove(iid)
    for iid in list(app.iid_to_index.keys()):
        if app.tree.exists(iid):
            app.tree.set(iid, "editcol", "")
    for iid, idx in app.iid_to_index.items():
        if app.tree.exists(iid):
            app.tree.set(iid, "chance", app.tables[idx].chance_str)
            app.tree.item(iid, tags=())
    _update_dynamic_chances(app)

def _on_tree_double_click(app, event):
    if not app.var_mode_air.get():
        return
    region = app.tree.identify("region", event.x, event.y)
    if region != "cell": return
    col = app.tree.identify_column(event.x)
    if col != "#3": return
    iid = app.tree.identify_row(event.y)
    if not iid or iid.startswith("type:"): return
    bbox = app.tree.bbox(iid, column=col)
    if not bbox: return
    x, y, w, h = bbox
    cur = app.tree.set(iid, "editcol")
    entry = ttk.Entry(app.tree, width=max(6, int(w/8)))
    entry.insert(0, cur)
    entry.select_range(0, tk.END)
    entry.focus()
    entry.place(x=x, y=y, width=w, height=h)
    def finish(ok: bool):
        val = entry.get().strip()
        entry.destroy()
        if not ok or not val: return
        try:
            f = float(val)
            if f < 0: f = 0.0
            app.tree.set(iid, "editcol", str(f))
            app.tree.item(iid, tags=("changed",))
        except Exception:
            pass
        _update_dynamic_chances(app)
    entry.bind("<Return>", lambda e: finish(True))
    entry.bind("<Escape>", lambda e: finish(False))
    entry.bind("<FocusOut>", lambda e: finish(True))

def _refresh_tables(app):
    app.tree.delete(*app.tree.get_children())
    app.tables.clear()
    app.iid_to_index.clear()
    app.references.clear()

    root = Path(app.var_root.get()).resolve()
    if not (root / "data").exists():
        return

    legend = (app.var_legend.get() or "academy:myths_and_legends/legendaries").strip()
    paths = walk_academy_tier_tables(root)

    # reference scan: all loot_table JSONs
    for json_file in (root / "data").rglob("*.json"):
        if "loot_table" not in str(json_file).lower():
            continue
        doc = load_json(json_file)
        if not doc:
            continue
        for pool in iter_pools(doc):
            for e in iter_entries(pool):
                if is_loot_table_entry(e) and e.get("value"):
                    target = e["value"]
                    # normalize (allow missing ns -> minecraft:)
                    if ":" not in target:
                        target = "minecraft:" + target
                    if target.endswith(".json"):
                        target = target[:-5]
                    selfkey = target.lower()
                    app.references.setdefault(selfkey, []).append(json_file)

    groups: Dict[str, List[TableInfo]] = {}
    for p in paths:
        doc = load_json(p)
        if not doc: continue
        tname, tier = parse_type_and_tier(p)
        chance = approx_legendary_chance_in_doc(doc, legend)
        chance_str = readable_odds(chance)
        empty_w = find_legend_empty_weight(doc, legend)
        editable = empty_w is not None
        loot_id = loot_table_id_from_path(root, p)
        info = TableInfo(path=p, type_name=tname, tier=tier, chance_value=chance,
                         chance_str=chance_str, can_edit=editable, air_weight=empty_w,
                         loot_id=loot_id)
        groups.setdefault(tname, []).append(info)

    for tname in sorted(groups.keys()):
        pid = f"type:{tname}"
        app.tree.insert("", "end", iid=pid, text=tname.title(), values=("", "", ""), open=True)
        for info in sorted(groups[tname], key=lambda ti: (ti.tier, str(ti.path))):
            idx = len(app.tables)
            app.tables.append(info)
            iid = f"row:{idx}"
            app.iid_to_index[iid] = idx
            edit_val = str(info.air_weight) if (app.var_mode_air.get() and info.air_weight is not None) else ""
            app.tree.insert(pid, "end", iid=iid, text="",
                            values=(short_display_path(info.path), info.chance_str, edit_val))
    app.tree.heading("editcol", text=("Air/Empty Weight" if app.var_mode_air.get() else "Multiplier"))

    _apply_filter(app, rebuild=False)
    _update_dynamic_chances(app)

# dynamic preview + bolding
def _update_dynamic_chances(app):
    for iid in list(app.iid_to_index.keys()):
        if app.tree.exists(iid):
            app.tree.item(iid, tags=())

    legend = (app.var_legend.get() or "academy:myths_and_legends/legendaries").strip()

    def preview(path: Path, mult: Optional[float]=None, override_air: Optional[float]=None) -> Optional[str]:
        doc = load_json(path)
        if not doc: return None
        if override_air is not None:
            for pool in iter_pools(doc):
                for e in iter_entries(pool):
                    if is_empty_entry(e):
                        set_entry_weight(e, override_air)
        if mult is not None and mult > 0:
            apply_multiplier_to_doc(doc, legend, mult)
        newp = approx_legendary_chance_in_doc(doc, legend)
        return readable_odds(newp)

    mode = ("air" if app.var_mode_air.get() else
            "specific" if app.var_mode_specific.get() else
            "tier" if app.var_mode_tier.get() else
            "global" if app.var_mode_global.get() else None)

    try: gmult = float(app.var_global_mult.get())
    except: gmult = None
    try: tmult = float(app.var_tier_mult.get())
    except: tmult = None
    try: smult = float(app.var_spec_mult.get())
    except: smult = None
    selected = set(app.tree.selection())

    for iid, idx in app.iid_to_index.items():
        if not app.tree.exists(iid): continue
        ti = app.tables[idx]
        old = ti.chance_str
        new = None
        tags = []
        if mode == "global" and gmult and gmult > 0:
            new = preview(ti.path, mult=gmult)
            tags.append("global_target")
        elif mode == "tier" and tmult and tmult > 0 and ti.tier == app.var_tier.get():
            new = preview(ti.path, mult=tmult)
            tags.append("tier_target")
        elif mode == "specific" and smult and smult > 0 and iid in selected:
            new = preview(ti.path, mult=smult)
            tags.append("selected_for_specific")
        elif mode == "air":
            val = app.tree.set(iid, "editcol")
            if val:
                try:
                    aw = float(val)
                    new = preview(ti.path, override_air=aw)
                    tags.append("changed")
                except Exception:
                    pass

        app.tree.set(iid, "chance", f"{old} → {new}" if new else old)
        if tags: app.tree.item(iid, tags=tuple(tags))

    app.tree.heading("editcol", text=("Air/Empty Weight" if mode == "air" else "Multiplier"))

def _on_tree_selection_changed(app):
    _update_dynamic_chances(app)
    sel = app.tree.selection()
    # hide panel when nothing
    if not sel:
        if app.refs_panel.winfo_ismapped():
            app.body_pane.forget(app.refs_panel)
        return
    iid = sel[0]
    if iid not in app.iid_to_index:
        if app.refs_panel.winfo_ismapped():
            app.body_pane.forget(app.refs_panel)
        return
    ti = app.tables[app.iid_to_index[iid]]
    loot_id = (ti.loot_id or "").lower()
    if not loot_id:
        if app.refs_panel.winfo_ismapped():
            app.body_pane.forget(app.refs_panel)
        return

    refs = app.references.get(loot_id, [])
    app.refs_list.delete(0, tk.END)
    app.refs_list_paths = []
    for ref in refs:
        app.refs_list.insert(tk.END, Path(ref).name)
        app.refs_list_paths.append(str(ref))

    if refs and not app.refs_panel.winfo_ismapped():
        app.body_pane.add(app.refs_panel, weight=1)
    elif not refs and app.refs_panel.winfo_ismapped():
        app.body_pane.forget(app.refs_panel)

def _apply_changes(app):
    root = Path(app.var_root.get()).resolve()
    legend = (app.var_legend.get() or "academy:myths_and_legends/legendaries").strip()
    mode = ("air" if app.var_mode_air.get() else
            "specific" if app.var_mode_specific.get() else
            "tier" if app.var_mode_tier.get() else
            "global" if app.var_mode_global.get() else None)
    if not mode:
        messagebox.showinfo("Nothing to Apply", "Choose a mode: Global / Tier / Specific / Air.")
        return

    changed = False

    if mode == "global":
        try: mult = float(app.var_global_mult.get())
        except: mult = None
        if not mult or mult <= 0:
            messagebox.showerror("Invalid", "Global multiplier must be > 0.")
            return
        if not messagebox.askyesno("Confirm Global", f"Apply global multiplier {mult} to ALL Academy loot tables?"):
            return
        for p in walk_academy_tier_tables(root):
            doc = load_json(p)
            if doc and apply_multiplier_to_doc(doc, legend, mult):
                ensure_backup(p, root, app.backup_root)
                save_json(p, doc)
                changed = True

    elif mode == "tier":
        try: mult = float(app.var_tier_mult.get())
        except: mult = None
        tsel = app.var_tier.get()
        if not mult or mult <= 0:
            messagebox.showerror("Invalid", "Tier multiplier must be > 0.")
            return
        if not messagebox.askyesno("Confirm Tier", f"Apply multiplier {mult} to Tier {tsel}?"):
            return
        for p in walk_academy_tier_tables(root):
            _, t = parse_type_and_tier(p)
            if t == tsel:
                doc = load_json(p)
                if doc and apply_multiplier_to_doc(doc, legend, mult):
                    ensure_backup(p, root, app.backup_root)
                    save_json(p, doc)
                    changed = True

    elif mode == "specific":
        try: mult = float(app.var_spec_mult.get())
        except: mult = None
        if not mult or mult <= 0:
            messagebox.showerror("Invalid", "Specific multiplier must be > 0.")
            return
        sel = list(app.tree.selection())
        if not sel:
            messagebox.showinfo("No Selection", "Ctrl+Click to select one or more rows first.")
            return
        if not messagebox.askyesno("Confirm Specific", f"Apply multiplier {mult} to {len(sel)} selected row(s)?"):
            return
        for iid in sel:
            idx = app.iid_to_index.get(iid)
            if idx is None: continue
            ti = app.tables[idx]
            doc = load_json(ti.path)
            if doc and apply_multiplier_to_doc(doc, legend, mult):
                ensure_backup(ti.path, root, app.backup_root)
                save_json(ti.path, doc)
                changed = True

    elif mode == "air":
        targets = []
        for iid, idx in app.iid_to_index.items():
            val = app.tree.set(iid, "editcol")
            if not val: continue
            try:
                aw = float(val)
                if aw < 0: aw = 0.0
            except Exception:
                continue
            targets.append((iid, idx, aw))
        if not targets:
            messagebox.showinfo("No Edits", "No Air/Empty weights were entered.")
            return
        if not messagebox.askyesno("Confirm Air/Empty", f"Apply Air/Empty edits to {len(targets)} row(s)?"):
            return
        for _, idx, aw in targets:
            ti = app.tables[idx]
            doc = load_json(ti.path)
            if not doc: continue
            touched = False
            for pool in iter_pools(doc):
                for e in iter_entries(pool):
                    if is_empty_entry(e):
                        if abs(entry_weight(e) - aw) > 1e-9:
                            set_entry_weight(e, aw)
                            touched = True
            if touched:
                ensure_backup(ti.path, root, app.backup_root)
                save_json(ti.path, doc)
                changed = True

    if changed:
        messagebox.showinfo("Done", f"Changes applied. Backups saved to:\n{app.backup_root}")
    else:
        messagebox.showinfo("No Changes", "Nothing to update.")
    _refresh_tables(app)
