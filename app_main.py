"""Entry point for the Windows .exe (PyInstaller).

`ManheimPrediction.exe --selftest <result-file>` imports everything the app needs, runs one
command against a temporary database and writes OK or the error to <result-file>.
The GitHub build runs this on the finished .exe before publishing it.
"""
import sys
import tempfile
import traceback
from pathlib import Path


def selftest(result_file: str) -> int:
    try:
        import tkinter  # noqa: F401

        import numpy, openpyxl, pandas, pdfplumber  # noqa: E401,F401

        from manheim_pm import app

        with tempfile.TemporaryDirectory() as d:
            out = app.run_captured(["--db", str(Path(d) / "t.db"), "history"])
            assert "Nothing stored yet" in out, out
            assert app.bundled("criteria.toml").exists(), "criteria.toml not bundled"
        Path(result_file).write_text("OK")
        return 0
    except BaseException:
        Path(result_file).write_text("FAILED\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    from manheim_pm.app import main
    main()
