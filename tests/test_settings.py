import importlib

import pytest

from api import settings


def test_default_allowed_origins(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    reloaded = importlib.reload(settings)
    assert reloaded.ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_allowed_origins_are_trimmed_and_empty_values_removed(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        " https://site.example , , http://localhost:3000 ",
    )
    reloaded = importlib.reload(settings)
    assert reloaded.ALLOWED_ORIGINS == [
        "https://site.example",
        "http://localhost:3000",
    ]


def test_numeric_settings_are_loaded_from_environment(monkeypatch):
    for name, value in {
        "SSE_HEARTBEAT_SECONDS": "5.5",
        "MAX_CONCURRENT_RUNS": "3",
        "MAX_STREAM_SECONDS": "90",
        "MAX_SOURCES": "12",
    }.items():
        monkeypatch.setenv(name, value)

    reloaded = importlib.reload(settings)
    assert reloaded.SSE_HEARTBEAT_SECONDS == 5.5
    assert reloaded.MAX_CONCURRENT_RUNS == 3
    assert reloaded.MAX_STREAM_SECONDS == 90
    assert reloaded.MAX_SOURCES == 12
    assert reloaded.CONTRACT_VERSION == 1


def test_invalid_numeric_setting_fails_fast(monkeypatch):
    monkeypatch.setenv("MAX_SOURCES", "not-an-integer")
    with pytest.raises(ValueError):
        importlib.reload(settings)
    monkeypatch.delenv("MAX_SOURCES")
    importlib.reload(settings)
