from __future__ import annotations

import json

import pytest

from vineclim.fetch import (
    FetchError,
    build_params,
    fetch_power,
    parse_power_json,
    write_csv,
    write_metadata,
    year_bounds,
)


def payload() -> dict:
    dates = ["20240103", "20240101", "20240102"]
    return {
        "geometry": {"type": "Point", "coordinates": [98.86, 28.55, 3879.61]},
        "header": {"fill_value": -999.0, "api": {"version": "v2.10.3"}, "sources": ["MERRA2"]},
        "properties": {
            "parameter": {
                "T2M_MAX": dict.fromkeys(dates, 10.0) | {"20240102": -999.0},
                "T2M_MIN": dict.fromkeys(dates, 1.0),
                "PRECTOTCORR": {"20240101": 0.0, "20240102": 2.5, "20240103": 0.0},
            }
        },
    }


def test_parse_power_payload_sorts_and_maps_fill():
    frame, metadata = parse_power_json(payload())
    assert list(frame["date"].astype(str)) == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert frame.loc[1, "tmax_c"] != frame.loc[1, "tmax_c"]  # NaN
    assert frame.loc[0, "tmax_c"] == pytest.approx(10.0)
    assert frame.loc[1, "precip_mm"] == pytest.approx(2.5)
    assert metadata["grid_elevation_m"] == pytest.approx(3879.61)
    assert metadata["n_days"] == 3


def test_parse_power_rejects_missing_parameter():
    data = payload()
    del data["properties"]["parameter"]["T2M_MIN"]
    with pytest.raises(FetchError, match="缺少参数"):
        parse_power_json(data)


def test_parse_power_rejects_inconsistent_dates():
    data = payload()
    data["properties"]["parameter"]["T2M_MIN"]["20240104"] = 3.0
    with pytest.raises(FetchError, match="日期不一致"):
        parse_power_json(data)


def test_parse_power_rejects_bad_date():
    data = payload()
    data["properties"]["parameter"]["T2M_MAX"] = {"2024-01-01": 1.0}
    data["properties"]["parameter"]["T2M_MIN"] = {"2024-01-01": 1.0}
    data["properties"]["parameter"]["PRECTOTCORR"] = {"2024-01-01": 1.0}
    with pytest.raises(FetchError, match="日期格式"):
        parse_power_json(data)


def test_build_params_contains_api_contract():
    params = build_params(28.55, 98.86, "20150101", "20151231")
    assert params["parameters"] == "T2M_MAX,T2M_MIN,PRECTOTCORR"
    assert params["community"] == "AG"
    assert params["latitude"] == "28.5500"
    assert params["start"] == "20150101"


def test_build_params_validates_coordinates():
    with pytest.raises(FetchError):
        build_params(91, 0, "20150101", "20150102")
    with pytest.raises(FetchError):
        build_params(0, 181, "20150101", "20150102")


def test_year_bounds():
    assert year_bounds(2015, 2025) == ("20150101", "20251231")
    with pytest.raises(FetchError):
        year_bounds(2025, 2015)
    with pytest.raises(FetchError):
        year_bounds(1970, 2015)


def test_write_csv_marks_missing_as_empty(tmp_path):
    frame, _ = parse_power_json(payload())
    path = write_csv(frame, tmp_path / "out.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "date,tmin_c,tmax_c,precip_mm"
    assert lines[2] == "2024-01-02,1.00,,2.50"
    assert lines[1] == "2024-01-01,1.00,10.00,0.00"


def test_write_metadata_roundtrips(tmp_path):
    path = write_metadata({"grid_elevation_m": 100.0}, tmp_path / "meta.json")
    assert json.loads(path.read_text(encoding="utf-8"))["grid_elevation_m"] == 100.0


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_fetch_power_offline_with_fake_response(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(payload())

    monkeypatch.setattr("vineclim.fetch.requests.get", fake_get)
    frame, metadata = fetch_power(28.55, 98.86, 2024, 2024)
    assert len(frame) == 3
    assert metadata["n_days"] == 3
    assert captured["url"].startswith("https://power.larc.nasa.gov/")
    assert captured["params"]["start"] == "20240101"


def test_fetch_power_retries_then_fails(monkeypatch):
    calls = {"n": 0}

    def failing_get(*args, **kwargs):
        calls["n"] += 1
        raise ValueError("boom")

    monkeypatch.setattr("vineclim.fetch.requests.get", failing_get)
    monkeypatch.setattr("vineclim.fetch.time.sleep", lambda _: None)
    with pytest.raises(FetchError, match="下载失败"):
        fetch_power(28.55, 98.86, 2024, 2024, attempts=2)
    assert calls["n"] == 2
