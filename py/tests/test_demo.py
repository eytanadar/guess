"""demo(): every step of the tour runs, in order, on the sample graph."""
from pathlib import Path

import pytest

from guess import Session
from guess.demo import LEVELS, STEPS
from tests.test_gython import Recorder

SAMPLE = Path(__file__).resolve().parents[2] / "gdfs" / "sample.gdf"


def test_every_step_runs_in_order(tmp_path, monkeypatch):
    pytest.importorskip("altair")                    # the Altair step
    (tmp_path / "sample.gdf").write_bytes(SAMPLE.read_bytes())
    monkeypatch.chdir(tmp_path)
    rec = Recorder()
    s = Session(rec)
    for i, step in enumerate(STEPS, 1):
        assert s.run(step["code"]), (i, step["title"], rec.of("error")[-1:])
        if step["title"] == "Mistakes are cheap":
            assert s.run("undo()")                   # as the step tells you to
    assert len(s.graph.nodes) == 402


def test_steps_go_from_basic_to_advanced_and_demo_jumps():
    levels = [s["level"] for s in STEPS]
    assert levels == sorted(levels, key=LEVELS.index) and set(levels) == set(LEVELS)
    for s in STEPS:
        assert s["title"] and s["text"] and s["code"] and s["notice"]
    rec = Recorder()
    s = Session(rec)
    assert s.run("demo()") and rec.of("demo")[-1]["at"] == 0
    assert s.run("demo('advanced')") and STEPS[rec.of("demo")[-1]["at"]]["level"] == "Advanced"
    assert s.run("demo(9)") and rec.of("demo")[-1]["at"] == 8
    assert not s.run("demo(99)") and not s.run("demo('expert')")
