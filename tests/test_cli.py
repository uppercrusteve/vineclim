from __future__ import annotations

from pathlib import Path

import pytest

from vineclim.cli import main
from vineclim.plot import setup_chinese_font

from .conftest import write_csv


@pytest.fixture
def input_path(tmp_path: Path) -> Path:
    rows = [(f"2024-05-{day:02d}", 8.0 + day / 2, 18.0 + day / 3, 0.0) for day in range(1, 6)]
    return write_csv(tmp_path / "station_2024.csv", rows)


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "vineclim" in capsys.readouterr().out


def test_compute_writes_all_outputs(input_path, tmp_path, capsys):
    out = tmp_path / "out"
    code = main(
        [
            "compute",
            str(input_path),
            "--lat",
            "28.55",
            "--year",
            "2024",
            "-o",
            str(out),
        ]
    )
    assert code == 0
    for name in ("indices.json", "indices.csv", "report.md", "climatology.png", "annual-gdd.png", "frost-calendar.png"):
        assert (out / name).is_file()
    captured = capsys.readouterr().out
    assert "完成" in captured
    assert "数据性质" in captured


def test_compute_with_correction_shows_both_values(input_path, tmp_path):
    out = tmp_path / "corrected"
    code = main(
        [
            "compute",
            str(input_path),
            "--lat",
            "28.55",
            "--station-elev",
            "2200",
            "--grid-elev",
            "3879.6",
            "-o",
            str(out),
        ]
    )
    assert code == 0
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "未订正" in report
    assert "订正（示意）" in report


def test_report_subcommand_works(input_path, tmp_path):
    out = tmp_path / "report"
    code = main(["report", str(input_path), "--lat", "28.55", "-o", str(out), "--no-plots"])
    assert code == 0
    assert (out / "report.md").is_file()
    assert not (out / "climatology.png").exists()


def test_compute_bad_latitude(input_path, tmp_path, capsys):
    code = main(["compute", str(input_path), "--lat", "91", "-o", str(tmp_path / "x")])
    assert code == 2
    assert "纬度" in capsys.readouterr().err


def test_compute_requires_both_elevations(input_path, tmp_path, capsys):
    code = main(
        ["compute", str(input_path), "--lat", "28", "--station-elev", "2200", "-o", str(tmp_path / "x")]
    )
    assert code == 2
    assert "同时" in capsys.readouterr().err


def test_compute_rejects_conflicting_year_options(input_path, tmp_path, capsys):
    code = main(
        [
            "compute",
            str(input_path),
            "--lat",
            "28",
            "--year",
            "2024",
            "--start-year",
            "2020",
            "--end-year",
            "2024",
            "-o",
            str(tmp_path / "x"),
        ]
    )
    assert code == 2
    assert "--year" in capsys.readouterr().err


def test_compute_missing_csv(tmp_path, capsys):
    code = main(["compute", str(tmp_path / "nope.csv"), "--lat", "28", "-o", str(tmp_path / "x")])
    assert code == 2
    assert "不存在" in capsys.readouterr().err


def test_fetch_refuses_existing_without_force(tmp_path, capsys):
    output = tmp_path / "data.csv"
    output.write_text("x", encoding="utf-8")
    code = main(
        ["fetch", "--lat", "28", "--lon", "98", "--start", "2024", "--end", "2024", "-o", str(output)]
    )
    assert code == 3
    assert "--force" in capsys.readouterr().err


def test_chinese_font_is_selected():
    chosen = setup_chinese_font()
    assert chosen != ""
