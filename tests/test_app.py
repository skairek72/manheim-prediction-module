"""The window's buttons run the same commands; check them without opening a window."""
from manheim_pm import app


def test_app_folder_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    h = app.home()
    assert (h / "criteria.toml").exists() and (h / "reports").is_dir()
    labels = [label for label, _ in app.actions(lambda kind: None)]
    assert labels[0].startswith("1.") and "SHORTLIST" in labels[2]
    out = app.run_captured(["--db", str(h / "manheim.db"), "history"])
    assert "Nothing stored yet" in out


def test_cancelled_dialog_runs_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    first = app.actions(lambda kind: [] if kind == "pdfs" else None)[0][1]
    assert not first()


def test_problems_are_shown_not_crashed(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    out = app.run_captured(["--db", str(tmp_path / "x.db"), "shortlist", "--criteria", str(app.home() / "criteria.toml")])
    assert "PROBLEM" in out


def test_database_file_is_released_after_each_command(tmp_path, monkeypatch):
    # Windows cannot delete or replace a file that is still open; the build's .exe self-test caught this
    from manheim_pm import store
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    app.run_captured(["--db", str(tmp_path / "t.db"), "history"])
    assert store._OPEN == []
