"""BUG-01..BUG-06 regression gate (COMPREHENSIVE-ANALYSIS §2.2).

Each test pins the exact defect the reviewer found so a regression back to the
buggy behaviour FAILS this file:

  * BUG-02  emit() bus fallback fires when publish() itself returns False, not
            only when the broker branch is considered down — otherwise the
            message vanishes between broker branches.
  * BUG-03  malformed accel windows (non-numeric / non-finite samples, garbage
            node id) must be DROPPED WHOLE by the fusion + stiffness consumers —
            never raise through the event bus (ERROR spam) and never partially
            mutate a ring.
  * BUG-05  hero (z24) validate_accel enforces node / finite-rms / flag {0,1} /
            finite-samples — the same honesty the live-demo branch already had.

BUG-01 (MemoryStore bridge-tag isolation) is pinned in test_contract_parity.py
section D; BUG-04/BUG-06 (twin side) are pinned by the twin vitest suites
(config re-discovery + replay auto-advance).

Run:  python backend/tests/test_bugfix_regression.py
"""
from __future__ import annotations

import math
import sys
import threading
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import contract, db, events  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.fusion import FusionService  # noqa: E402
from app.mqtt_client import (  # noqa: E402
    emit,
    _register_subscriber,
    _unregister_subscriber,
)
from app.stiffness import StiffnessTracker  # noqa: E402

_PASS = 0
_FAIL = 0
_FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        _FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


def _samples(n: int = 100, value: float = 0.01) -> list[float]:
    return [value] * n


def _good_hero(**over) -> dict:
    row = {
        "bridge": "z24", "node": 7, "ts": 100.0, "fs": 100,
        "samples": _samples(), "rms": 0.05, "flag": 0,
    }
    row.update(over)
    return row


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------
class FakePublisher:
    """Stand-in publisher whose publish() result the test controls."""

    def __init__(self, ok: bool = True):
        self.connected = threading.Event()
        self.connected.set()
        self._ok = ok
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload: dict, qos: int = 1) -> bool:
        self.published.append((topic, payload))
        return self._ok


class FakeSubscriber:
    """Registered bus->MQTT subscriber whose connected flag gates emit()'s
    broker_delivering decision."""

    def __init__(self, up: bool = True):
        self.connected = threading.Event()
        if up:
            self.connected.set()


# ---------------------------------------------------------------------------
# BUG-02 — emit() must fall back to the bus when publish() fails
# ---------------------------------------------------------------------------
def test_bug02_emit_fallback_on_publish_failure() -> None:
    print("[BUG-02] emit() bus fallback fires when publish() reports failure")
    bus = events.get_bus()
    sub = FakeSubscriber(up=True)
    _register_subscriber(sub)
    try:
        got: list[dict] = []
        tok = bus.subscribe("bridge/z24/status", lambda t, p: got.append(p))

        # broker branch "delivering" (publisher + subscriber both up) but the
        # publish() call itself fails -> message must STILL land on the bus.
        pub_failing = FakePublisher(ok=False)
        ret = emit("bridge/z24/status", {"online": True}, pub_failing, bus=bus)
        check("BUG-02 failed publish falls back to the bus",
              len(got) == 1, f"got {len(got)} on bus")
        check("BUG-02 emit returns True (delivered somewhere)",
              ret is True, f"ret={ret!r}")
        check("BUG-02 no silent drop before the fix (no bus, no MQTT)",
              pub_failing.published == [("bridge/z24/status", {"online": True})],
              str(pub_failing.published))

        # healthy publish -> bus must NOT duplicate (existing behaviour)
        pub_ok = FakePublisher(ok=True)
        emit("bridge/z24/status", {"online": False}, pub_ok, bus=bus)
        check("BUG-02 no bus duplicate when publish succeeds", len(got) == 1)

        bus.unsubscribe(tok)
    finally:
        _unregister_subscriber(sub)


# ---------------------------------------------------------------------------
# BUG-03 — malformed accel windows dropped whole by fusion + stiffness
# ---------------------------------------------------------------------------
def test_bug03_malformed_accel_rejected() -> None:
    print("[BUG-03] fusion + stiffness reject malformed accel without raising")
    bus = events.get_bus()
    store = db.MemoryStore(cache_path=None)
    cfg = settings
    fus = FusionService(cfg, bus, store, FakePublisher())
    init_bhi, init_vib = fus.bhi, fus.vib  # defaults: ~87.1 GREEN, vib_base 0.12

    malformed: list[tuple[str, dict]] = [
        # non-numeric sample in the middle (the historical crash path)
        ("string sample", {"bridge": "z24", "node": 7, "fs": 100,
                           "samples": _samples(value=0.01) + ["boom"]}),
        # every sample non-numeric
        ("all-garbage samples", {"bridge": "z24", "node": 7, "fs": 100,
                                 "samples": ["a", "b"]}),
        # NaN sample
        ("nan sample", {"bridge": "z24", "node": 7, "fs": 100,
                        "samples": _samples() + [float("nan")]}),
        # inf sample
        ("inf sample", {"bridge": "z24", "node": 7, "fs": 100,
                        "samples": _samples() + [float("inf")]}),
        # garbage node id
        ("garbage node", {"bridge": "z24", "node": "six", "fs": 100,
                          "samples": _samples()}),
        # bool node
        ("bool node", {"bridge": "z24", "node": True, "fs": 100,
                       "samples": _samples()}),
        # no node at all
        ("missing node", {"bridge": "z24", "fs": 100, "samples": _samples()}),
    ]

    for name, payload in malformed:
        try:
            fus.on_accel("bridge/z24/accel", payload)
            raised = False
        except Exception as exc:  # noqa: BLE001 — the bug WAS the raise
            raised = True
            print(f"    raised {exc!r}")
        check(f"BUG-03 fusion drops {name} without raising", not raised)

    check("BUG-03 no ring residue after malformed feed",
          len(fus._rings) == 0 or all(len(r) == 0 for r in fus._rings.values()),
          f"rings={ {k: len(v) for k, v in fus._rings.items()} }")
    check("BUG-03 BHI untouched by malformed feed",
          abs(fus.bhi - init_bhi) < 1e-9 and abs(fus.vib - init_vib) < 1e-9,
          f"bhi={fus.bhi} vib={fus.vib}")

    # a VALID window after the junk must still extend the ring (pipeline alive)
    fus.on_accel("bridge/z24/accel",
                 {"bridge": "z24", "node": 7, "fs": 100, "samples": _samples()})
    check("BUG-03 valid window still received after malformed feed",
          len(fus._rings.get(7, ())) == 100,
          f"ring(7) len={len(fus._rings.get(7, ()))}")

    # ---- stiffness tracker -------------------------------------------------
    stiff = StiffnessTracker(settings, bus)
    for name, payload in malformed:
        try:
            stiff.on_accel("bridge/z24/accel", payload)
            raised = False
        except Exception as exc:  # noqa: BLE001
            raised = True
            print(f"    raised {exc!r}")
        check(f"BUG-03 stiffness drops {name} without raising", not raised)
    check("BUG-03 stiffness ring empty after malformed feed",
          all(len(r) == 0 for r in stiff._rings.values()),
          f"rings={ {k: len(v) for k, v in stiff._rings.items()} }")
    stiff.stop()


# ---------------------------------------------------------------------------
# BUG-05 — hero validate_accel enforces node / rms / flag / finite samples
# ---------------------------------------------------------------------------
def test_bug05_hero_validate_accel_strictness() -> None:
    print("[BUG-05] hero (z24) validate_accel strictness")
    check("BUG-05 clean hero row passes",
          contract.validate_accel(_good_hero()) == [],
          str(contract.validate_accel(_good_hero())))
    bad: list[tuple[str, dict]] = [
        ("missing node", _good_hero(node=None)),
        ("garbage node", _good_hero(node="six")),
        ("negative node", _good_hero(node=-1)),
        ("bool node", _good_hero(node=True)),
        ("float node", _good_hero(node=7.0)),
        ("non-finite rms", _good_hero(rms=float("nan"))),
        ("infinite rms", _good_hero(rms=float("inf"))),
        ("string rms", _good_hero(rms="high")),
        ("missing rms", _good_hero(rms=None)),
        ("flag 2", _good_hero(flag=2)),
        ("flag -1", _good_hero(flag=-1)),
        # note: flag=True is ACCEPTED because Python True == 1 — the same
        # semantics as the live-demo branch (JSON true === flag 1).
        ("missing flag", _good_hero(flag=None)),
        ("short samples", _good_hero(samples=_samples(99))),
        ("non-numeric sample", _good_hero(samples=_samples() + ["x"])),
        ("nan sample", _good_hero(samples=_samples() + [float("nan")])),
    ]
    for name, row in bad:
        errs = contract.validate_accel(row)
        check(f"BUG-05 hero rejects {name}", len(errs) > 0, str(errs))
    # the thin live-demo row must still pass its own branch
    demo = {"bridge": "live-demo", "node": 1, "ts": 1.0, "fs": 0,
            "samples": [], "rms": 0.03, "flag": 0}
    check("BUG-05 live-demo thin row still passes its branch",
          contract.validate_accel(demo, bridge="live-demo") == [],
          str(contract.validate_accel(demo, bridge="live-demo")))


if __name__ == "__main__":
    test_bug02_emit_fallback_on_publish_failure()
    test_bug03_malformed_accel_rejected()
    test_bug05_hero_validate_accel_strictness()
    print("\nRESULT", "FAIL" if _FAIL else "PASS",
          f"{_PASS} passed, {_FAIL} failed")
    if _FAILURES:
        for f in _FAILURES:
            print("  FAILED:", f)
    sys.exit(1 if _FAIL else 0)