from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    module_name = f"test_script_{script_name.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load script module: {script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_feed_service_exits_cleanly_on_keyboard_interrupt(monkeypatch, capsys) -> None:
    module = _load_script_module("run_feed_service.py")

    def interrupted(coroutine):
        coroutine.close()
        raise KeyboardInterrupt()

    monkeypatch.setattr(asyncio, "run", interrupted)

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 130
    captured = capsys.readouterr()
    assert captured.err.strip() == "Feed service stopped by operator."


def test_replay_feed_exits_cleanly_on_keyboard_interrupt(monkeypatch, capsys) -> None:
    module = _load_script_module("replay_feed.py")

    def interrupted(coroutine):
        coroutine.close()
        raise KeyboardInterrupt()

    monkeypatch.setattr(asyncio, "run", interrupted)

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 130
    captured = capsys.readouterr()
    assert captured.err.strip() == "Replay stopped by operator."
