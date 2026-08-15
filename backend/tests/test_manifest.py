"""
D1-5 gate — data-realism manifest + per-channel synthetic measurement models.

Every number the twin shows comes from ONE of three honest sources (real Z24
replay | modeled synthetic | third-party live feed), and the manifest tells a
viewer which.  Synthetic channels carry the full documented measurement chain
(lowpass -> drift -> spikes -> ADC); real replay channels carry NONE of it.

Run:  python backend/tests/test_manifest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from app import channel_models as cm  # noqa: E402
from app import simulator as sim_mod  # noqa: E402
from app.config import settings  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  [FAIL] {name} {extra}")


def test_real_replay_manifest() -> None:
    print("[manifest] real Z24 replay channels carry NO synthetic effects")
    m = cm.build_manifest(settings, "z24-replay")
    check("data_source labeled z24-replay", m["data_source"] == "z24-replay")
    check("every channel real", all(e["real"] for e in m["channels"].values()))
    for node in settings.nodes:
        e = m["channels"][str(node)]
        check(f"node {node} source z24-replay", e["source"] == "z24-replay",
              e["source"])
        check(f"node {node} no synthetic chain applied",
              e["synthetic_chain_applied"] is False)
        check("node 7 labeled mid-span", (node != 7) or "mid-span" in e["sensor"])
    check("honesty real_channels = all nodes",
          sorted(int(n) for n in m["honesty"]["real_channels"])
          == sorted(settings.nodes))
    check("honesty modeled_channels empty",
          m["honesty"]["modeled_channels"] == [])
    check("honesty note says no effects on real replay",
          "never" in m["honesty"]["note"].lower())
    check("dataset provenance present",
          m["datasets"] and "Z24 benchmark" in m["datasets"][0]["name"])


def test_synthetic_manifest_and_chain() -> None:
    print("[manifest] synthetic channels document + apply the full chain")
    m = cm.build_manifest(settings, "synthetic")
    check("data_source labeled synthetic", m["data_source"] == "synthetic")
    check("no channel claims real", all(not e["real"] for e in m["channels"].values()))
    spec = m["channels"][str(settings.nodes[0])]
    stages = [s["stage"] for s in spec["chain"]]
    for stage in ("anti-alias lowpass", "bias drift", "transient spikes",
                  "ADC quantization"):
        check(f"chain has {stage}", stage in stages, str(stages))
    check("noise documented pink", spec["noise"]["color"] == "pink (1/f)")
    check("transport dropout documented, not applied",
          spec["transport"]["applied"] is False)
    check("honesty modeled = all nodes",
          sorted(int(n) for n in m["honesty"]["modeled_channels"])
          == sorted(settings.nodes))

    # the documented chain is actually what the stream does (never aspirational)
    fs, n = 100, 20_000
    t = np.arange(n) / fs
    base = 0.05 * np.sin(2 * np.pi * 4.0 * t) + 0.02 * np.random.default_rng(0).standard_normal(n)
    y1 = cm.model_measurement_chain(base, 7, fs=fs, duration_s=n // fs, seed=11)
    y2 = cm.model_measurement_chain(base, 7, fs=fs, duration_s=n // fs, seed=11)
    check("chain deterministic per seed", np.allclose(y1, y2))
    lsb = cm.ADC_VREF_MSS2 / (2 ** cm.ADC_BITS - 1)
    check("output ADC-quantized (multiples of LSB)",
          np.allclose(y1 / lsb, np.round(y1 / lsb)))
    check("quantized signal preserved (not zeroed)",
          float(np.std(y1)) > 0.01)
    # two different node seeds -> different drift/spike realization
    y3 = cm.model_measurement_chain(base, 8, fs=fs, duration_s=n // fs, seed=22)
    check("per-channel realization differs (sensor-specific effects)",
          not np.allclose(y1, y3))


def test_live_and_registry() -> None:
    print("[manifest] live-demo feed + simulator registry")
    m = cm.build_manifest(settings, "live-demo", live_active=True)
    check("live feed flagged active",
          m["live_public_feed"]["active"] is True)
    check("live feed never z24", m["live_public_feed"]["bridge"] == "live-demo")
    check("live note says never fused into z24 BHI",
          "never fused" in m["live_public_feed"]["note"])

    # ROADMAP line 58: the channel_models data source is a process-global — this
    # mutation must be restored so it never leaks into other test modules in a
    # shared process (pytest-safe / order-independent).
    prev = cm.get_data_source()
    try:
        cm.set_data_source("synthetic")
        check("registry drives manifest",
              cm.build_manifest(settings)["data_source"] == "synthetic")
        # the simulator records whichever source it actually uses
        sim_syn = sim_mod.Simulator(settings, None, bus=None, synthetic=True)
        check("simulator (synthetic) registers synthetic",
              cm.get_data_source() == "synthetic")
        sim_syn.stop()
        if (settings.data_dir / "inputs.npy").exists():
            sim_real = sim_mod.Simulator(settings, None, bus=None, synthetic=False)
            check("simulator (real data) registers z24-replay",
                  cm.get_data_source() == "z24-replay", cm.get_data_source())
            sim_real.stop()
        else:
            # ROADMAP line 60: on a fresh clone inputs.npy is absent (991 MB,
            # only .gitkeep is committed) — say so instead of silently skipping
            # the real-data replay branch.
            print("  [SKIP] real-data replay branch not exercised: "
                  f"{settings.data_dir / 'inputs.npy'} absent "
                  "(991 MB, gitignored — only .gitkeep is committed)")
    finally:
        cm.set_data_source(prev)


def main() -> int:
    try:
        test_real_replay_manifest()
        test_synthetic_manifest_and_chain()
        test_live_and_registry()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("manifest tests")
        import traceback
        print(f"  [ERROR] manifest tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== manifest gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
