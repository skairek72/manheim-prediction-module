"""Windows window app: buttons for the weekly routine, no typing commands.

Everything lives in Documents/Manheim Prediction:
    manheim.db       history of every pre-sale and post-sale imported
    criteria.toml    your buying rules (opened with Notepad from the app)
    reports/         every Excel report the app makes
"""
import contextlib
import io
import os
import queue
import shutil
import subprocess
import sys
import threading
import traceback
from datetime import date
from pathlib import Path

from . import cli

APP_NAME = "Manheim Prediction"


def home() -> Path:
    base = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents" / APP_NAME
    (base / "reports").mkdir(parents=True, exist_ok=True)
    crit = base / "criteria.toml"
    if not crit.exists():
        shutil.copy(bundled("criteria.toml"), crit)
    return base


def bundled(name: str) -> Path:
    """A file shipped inside the .exe (PyInstaller) or next to the source checkout."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / name


def report_path(kind: str) -> str:
    return str(home() / "reports" / f"{kind}_{date.today():%Y-%m-%d}.xlsx")


# Each action: (button label, function returning the command arguments, or None if cancelled)
def actions(ask):
    h = home()
    db = ["--db", str(h / "manheim.db")]
    crit = ["--criteria", str(h / "criteria.toml")]
    return [
        ("1. Import PRE-SALE PDF(s)", lambda: (f := ask("pdfs")) and db + ["import", *f]),
        ("2. Pre-sale report", lambda: db + ["presale", "--excel", report_path("presale")]),
        ("3. Make SHORTLIST", lambda: db + ["shortlist", *crit, "--excel", report_path("shortlist")]),
        ("4. Import POST-SALE folder", lambda: (d := ask("folder")) and db + ["postsale", d, "--excel",
                                                                              report_path("market_patterns")]),
        ("Post-sale workbook", lambda: db + ["postsale-report", "--excel", report_path("market_patterns")]),
        ("5. Scorecard (after post-sale)", lambda: (s := ask("date")) and db + ["scorecard", "--sale", s, *crit,
                                                                                "--excel", report_path("scorecard")]),
        ("What's stored", lambda: db + ["history"]),
    ]


def run_captured(argv: list[str]) -> str:
    """Run one command and return everything it printed (used by the window and by tests)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            cli.run(argv)
        except SystemExit:
            pass
        except Exception as e:  # show the problem in the window instead of crashing
            print(f"\nPROBLEM: {e}\n")
            traceback.print_exc(limit=1)
    return buf.getvalue()


def open_path(p: Path) -> None:
    if sys.platform == "win32":
        os.startfile(p)  # noqa: S606 - opens Explorer / Notepad on the user's own files
    else:
        subprocess.run(["xdg-open", str(p)], check=False)


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, scrolledtext, simpledialog

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("1100x700")
    out = scrolledtext.ScrolledText(root, font=("Consolas", 9), wrap="none")
    results: queue.Queue = queue.Queue()
    buttons = []

    def ask(kind):
        if kind == "pdfs":
            return list(filedialog.askopenfilenames(title="Choose pre-sale PDF(s)", filetypes=[("PDF", "*.pdf")]))
        if kind == "folder":
            return filedialog.askdirectory(title="Choose the folder with this sale's post-sale PDFs")
        return simpledialog.askstring(APP_NAME, "Sale date to score (YYYY-MM-DD):", parent=root)

    def start(make_args, label):
        argv = make_args()
        if not argv:
            return
        for b in buttons:
            b.config(state="disabled")
        out.insert("end", f"\n===== {label} =====\nWorking... (big folders can take a minute)\n")
        out.see("end")
        threading.Thread(target=lambda: results.put(run_captured(argv)), daemon=True).start()

    def poll():
        try:
            text = results.get_nowait()
        except queue.Empty:
            pass
        else:
            out.insert("end", text + "\n")
            out.see("end")
            for b in buttons:
                b.config(state="normal")
        root.after(200, poll)

    bar = tk.Frame(root)
    bar.pack(fill="x", padx=8, pady=6)
    for label, make_args in actions(ask):
        b = tk.Button(bar, text=label, command=lambda m=make_args, l=label: start(m, l), padx=6, pady=4)
        b.pack(side="left", padx=3)
        buttons.append(b)
    bar2 = tk.Frame(root)
    bar2.pack(fill="x", padx=8)
    tk.Button(bar2, text="Open reports folder", command=lambda: open_path(home() / "reports")).pack(side="left", padx=3)
    tk.Button(bar2, text="Edit my criteria", command=lambda: open_path(home() / "criteria.toml")).pack(side="left", padx=3)
    tk.Label(bar2, text=f"Your data: {home()}", fg="gray").pack(side="left", padx=12)
    out.pack(fill="both", expand=True, padx=8, pady=8)
    out.insert("end", f"{APP_NAME}\n\nWeekly routine:\n"
                      "  Before the sale: 1 -> 2 -> 3   (import the newest pre-sale, then make the shortlist)\n"
                      "  After the sale:  4 -> 5        (import the post-sale folder, then score the predictions)\n"
                      "Reports open from 'Open reports folder'.\n")
    root.after(200, poll)
    root.mainloop()


if __name__ == "__main__":
    main()
