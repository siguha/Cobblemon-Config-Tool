import os, time, shutil, subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from gui.tab1_academy import build_tab1
from gui.tab2_chests import build_tab2

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cobblemon Academy Config Tool — by @sigRao")
        self.geometry("1200x800")
        self.minsize(1000, 650)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.var_root = tk.StringVar(value=os.getcwd())
        self.var_legend = tk.StringVar(value="academy:myths_and_legends/legendaries")

        self.var_mode_global = tk.BooleanVar(value=False)
        self.var_mode_tier = tk.BooleanVar(value=False)
        self.var_mode_specific = tk.BooleanVar(value=False)
        self.var_mode_air = tk.BooleanVar(value=False)

        self.var_global_mult = tk.DoubleVar(value=2.0)
        self.var_tier = tk.IntVar(value=6)
        self.var_tier_mult = tk.DoubleVar(value=2.0)
        self.var_spec_mult = tk.DoubleVar(value=2.0)
        self.filter_var = tk.StringVar(value="")

        # runtime caches for tab 1
        self.tables = []           # list[TableInfo]
        self.iid_to_index = {}     # tree iid -> index in self.tables
        self.references = {}       # loot_id -> [paths]

        self.var_chest_root = tk.StringVar(value=os.getcwd())
        self.chest_rows = {}       # str(path) -> row dict

        # backups
        self.backups_root = Path(os.getcwd()) / "backups"
        self.backups_root.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M")
        self.backup_root = self.backups_root / ts
        self.backup_root.mkdir(parents=True, exist_ok=True)
        all_bk = sorted((d for d in self.backups_root.iterdir() if d.is_dir()),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        for old in all_bk[5:]:
            shutil.rmtree(old, ignore_errors=True)

        self._build_ui()

    # ui scaffold
    def _build_ui(self):
        # persistent toolbar
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="Load from Most Recent Backup", command=self._load_from_backup).pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        tab1 = ttk.Frame(self.nb)
        self.nb.add(tab1, text="Loot Tier Tables")
        build_tab1(self, tab1)

        tab2 = ttk.Frame(self.nb)
        self.nb.add(tab2, text="Chest Loot Tables")
        build_tab2(self, tab2)

    def _load_from_backup(self):
        from tkinter import Toplevel, Listbox
        # list backup folders
        backups = sorted((d for d in self.backups_root.iterdir() if d.is_dir()),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            messagebox.showinfo("No Backups", "No backups found yet.")
            return
        win = Toplevel(self)
        win.title("Restore From Backup")
        win.geometry("420x300")
        ttk.Label(win, text="Choose a backup to restore:", font=("Segoe UI", 10, "bold")).pack(pady=6)
        lb = Listbox(win, height=10)
        for b in backups:
            lb.insert(tk.END, b.name)
        lb.pack(fill="both", expand=True, padx=10, pady=8)
        def do_restore():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("Select one", "Pick a backup folder.")
                return
            folder = backups[sel[0]]
            if not messagebox.askyesno("Confirm", f"Restore JSON files from:\n{folder}?"):
                return
            root = Path(self.var_root.get() or os.getcwd()).resolve()
            for src in folder.rglob("*.json"):
                rel = src.relative_to(folder)
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            messagebox.showinfo("Restored", f"Files restored from:\n{folder}")
            win.destroy()
            # soft refresh both tabs if possible
            if hasattr(self, "_refresh_tables"):
                self._refresh_tables()
            if hasattr(self, "_refresh_chests"):
                self._refresh_chests()
        ttk.Button(win, text="Restore Selected", command=do_restore).pack(pady=6)
        ttk.Button(win, text="Cancel", command=win.destroy).pack()