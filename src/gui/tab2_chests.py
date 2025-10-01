import os, subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from core.file_utils import load_json, save_json, ensure_backup, short_display_path
from core.loot_utils import iter_pools, iter_entries, entry_weight, set_entry_weight

def build_tab2(app, parent):
    """Chest Loot Tables page — scrollable, expandable rows, apply, open on double-click."""
    header = ttk.Frame(parent, padding=10); header.pack(fill="x")
    ttk.Label(header, text="Chest Loot Tables Root:").grid(row=0, column=0, sticky="w")
    ent_root = ttk.Entry(header, textvariable=app.var_chest_root, width=70)
    ent_root.grid(row=0, column=1, sticky="we", padx=6)
    ttk.Button(header, text="Browse…", command=lambda: _pick_chest_root(app)).grid(row=0, column=2)

    ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=4)

    container = ttk.Frame(parent); container.pack(fill="both", expand=True)
    app._chest_canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
    vsb = ttk.Scrollbar(container, orient="vertical", command=app._chest_canvas.yview)
    app._chest_canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    app._chest_canvas.pack(side="left", fill="both", expand=True)

    app.chest_frame = ttk.Frame(app._chest_canvas)
    app._chest_canvas_window = app._chest_canvas.create_window((0, 0), window=app.chest_frame, anchor="nw")

    def _on_configure(_event=None):
        app._chest_canvas.configure(scrollregion=app._chest_canvas.bbox("all"))
        app._chest_canvas.itemconfigure(app._chest_canvas_window, width=app._chest_canvas.winfo_width())
    app.chest_frame.bind("<Configure>", _on_configure)
    app._chest_canvas.bind("<Configure>", _on_configure)

    def _on_mousewheel(event):
        app._chest_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    app._chest_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    app.chest_rows = {}

    footer = ttk.Frame(parent, padding=10); footer.pack(fill="x")
    ttk.Button(footer, text="Load / Refresh Chest Tables", command=lambda: _refresh_chests(app)).pack(side="left")

    # expose for app toolbar restore callback
    app._refresh_chests = lambda: _refresh_chests(app)

def _pick_chest_root(app):
    d = filedialog.askdirectory(initialdir=app.var_chest_root.get() or os.getcwd(),
                                title="Select datapack root")
    if d:
        app.var_chest_root.set(d)

def _refresh_chests(app):
    for child in app.chest_frame.winfo_children():
        child.destroy()
    app.chest_rows.clear()

    root = Path(app.var_chest_root.get() or os.getcwd()).resolve()
    chests_root = root / "data" / "minecraft" / "loot_table" / "chests"
    if not chests_root.exists():
        messagebox.showerror("Invalid Root", "Expected data/minecraft/loot_table/chests under selected root.")
        return

    for path in sorted(chests_root.glob("*.json")):
        _add_chest_row(app, path, root)

    app._chest_canvas.configure(scrollregion=app._chest_canvas.bbox("all"))

def _add_chest_row(app, path: Path, pack_root: Path):
    outer = ttk.Frame(app.chest_frame, relief="groove", borderwidth=1, padding=4)
    outer.pack(fill="x", pady=2)

    # header
    header = ttk.Frame(outer); header.pack(fill="x")
    parts = path.parts
    try:
        i = next(i for i, part in enumerate(parts) if part.lower() == "chests")
        display_path = "...\\" + "\\".join(parts[i:])
    except StopIteration:
        display_path = str(path)

    folder = os.path.dirname(display_path)
    filename = os.path.basename(display_path)
    ttk.Label(header, text=folder + "\\").pack(side="left", padx=(6, 0))

    fname_lbl = ttk.Label(header, text=filename, font=("Segoe UI", 9, "bold"))
    fname_lbl.pack(side="left")

    def _open_file(_=None, p=path):
        try:
            subprocess.Popen(["notepad.exe", str(p)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open:\n{p}\n\n{e}")
    fname_lbl.bind("<Double-1>", _open_file)

    tbtn = ttk.Button(header, width=3, text="+", command=lambda: _toggle_chest_row(app, path, pack_root))
    tbtn.pack(side="right", padx=4)

    details = ttk.Frame(outer)
    details.pack(fill="x", padx=12, pady=(4, 0))
    details.pack_forget()

    app.chest_rows[str(path)] = {
        "outer": outer,
        "header": header,
        "details": details,
        "expanded": False,
        "toggle_btn": tbtn,
        "root": pack_root,
        "controls": [],
        "path": path,
    }

def _toggle_chest_row(app, path: Path, pack_root: Path):
    key = str(path)
    row = app.chest_rows.get(key)
    if not row:
        return

    if row["expanded"]:
        row["details"].pack_forget()
        row["controls"].clear()
        row["expanded"] = False
        row["toggle_btn"].configure(text="+")
        return

    row["details"].pack(fill="x", padx=12, pady=(4, 0))
    row["controls"].clear()

    doc = load_json(path)
    if not doc:
        ttk.Label(row["details"], text="Failed to parse JSON for this chest.", foreground="red").pack(anchor="w")
        row["expanded"] = True
        return

    for child in row["details"].winfo_children():
        child.destroy()

    pool_idx = -1
    for pool in iter_pools(doc):
        pool_idx += 1
        ttk.Label(row["details"], text=f"Pool {pool_idx + 1}", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
        table = ttk.Frame(row["details"]); table.pack(fill="x", padx=12, pady=(0, 6))

        ttk.Label(table, text="Type", width=20, anchor="w").grid(row=0, column=0, sticky="w", padx=2)
        ttk.Label(table, text="Name / Value", width=60, anchor="w").grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(table, text="Weight", width=12, anchor="w").grid(row=0, column=2, sticky="w", padx=2)

        entry_idx = -1
        for e in iter_entries(pool):
            entry_idx += 1
            e_type = e.get("type", "")
            name = e.get("name") or e.get("value") or ""
            try:
                w = float(entry_weight(e))
            except Exception:
                w = float(e.get("weight", 1.0))

            bg = "#f8f8f8" if entry_idx % 2 == 0 else "#ffffff"
            tk.Label(table, text=e_type, width=20, anchor="w", bg=bg).grid(row=entry_idx + 1, column=0, sticky="w", padx=2)
            tk.Label(table, text=name, width=60, anchor="w", bg=bg).grid(row=entry_idx + 1, column=1, sticky="w", padx=2)
            var = tk.DoubleVar(value=w)
            ttk.Entry(table, textvariable=var, width=12).grid(row=entry_idx + 1, column=2, sticky="w", padx=2)
            row["controls"].append((pool_idx, entry_idx, var))

    ttk.Button(row["details"], text="Apply",
               command=lambda p=path, r=pack_root: _apply_chest(app, p, r)).pack(anchor="e", pady=(4, 2))

    row["expanded"] = True
    row["toggle_btn"].configure(text="-")

def _apply_chest(app, path: Path, pack_root: Path):
    key = str(path)
    row = app.chest_rows.get(key)
    if not row:
        return
    doc = load_json(path)
    if not doc:
        messagebox.showerror("Error", f"Failed to reload JSON:\n{path}")
        return
    controls = row.get("controls", [])
    if not controls:
        messagebox.showinfo("Nothing to Apply", "No editable fields for this chest.")
        return

    changed = False
    pool_list = list(iter_pools(doc))
    for (pool_idx, entry_idx, var) in controls:
        if pool_idx >= len(pool_list): continue
        entries = list(iter_entries(pool_list[pool_idx]))
        if entry_idx >= len(entries): continue
        try:
            new_w = float(var.get())
            if new_w < 0: new_w = 0.0
        except Exception:
            continue
        e = entries[entry_idx]
        try:
            old_w = float(entry_weight(e))
        except Exception:
            old_w = float(e.get("weight", 1.0))
        if abs(new_w - old_w) > 1e-9:
            try:
                set_entry_weight(e, new_w)
            except Exception:
                e["weight"] = new_w
            changed = True

    if not changed:
        messagebox.showinfo("No Changes", "All weights are unchanged.")
        return

    try:
        ensure_backup(path, pack_root, app.backup_root)
    except Exception as be:
        messagebox.showwarning("Backup Warning", f"Could not create backup:\n{be}")

    try:
        save_json(path, doc)
    except Exception as se:
        messagebox.showerror("Save Error", f"Failed to save:\n{se}")
        return

    messagebox.showinfo("Saved", f"Updated weights written to:\n{path}\nBackups in:\n{app.backup_root}")
