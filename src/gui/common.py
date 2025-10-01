import tkinter as tk

class Tooltip:
    """Simple hover tooltip."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _=None):
        if self.tip:
            return
        try:
            x, y, _, _ = self.widget.bbox("insert") or (0, 0, 0, 0)
        except Exception:
            x, y = 0, 0
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padx=4, pady=2
        )
        label.pack()

    def _hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class HeaderHoverTip:
    """Header tooltips for a Treeview (column id -> text)."""
    def __init__(self, tree, hints: dict[str, str]):
        self.tree = tree
        self.hints = hints
        tree.bind("<Motion>", self._motion)

    def _motion(self, event):
        col = self.tree.identify_column(event.x)
        text = self.hints.get(col) or self.hints.get(self._col_name(col))
        # Could add popup here like Tooltip; currently only maps column

    def _col_name(self, col):
        # '#0' or '#1'.. map to display names if needed
        return col
