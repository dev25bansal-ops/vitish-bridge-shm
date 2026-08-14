"""
D2-12 gate — seeded-defect demo grounded in Z24/S101.

The demo's damage scenario is a named, physically-grounded EI loss (Z24
progressive damage: pier settlement -> concrete cracking -> tendon rupture),
evaluated by the SAME continuous 3-span Euler-Bernoulli FEM that drives the
stiffness overlay.  This gate pins the catalog, the staging, the monotone
f1 response, the per-span EI-loss ground truth, and — critically — that the
stream's damage signature sits at the FEM-seeded f1 (NOT the old forced 4 Hz
tonal), so the measured frequency shift honestly matches the seeded physics.

Run:  python backend/tests/test_seeded_defect.py
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

from models.vibration import seeded_defect as sd  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402

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


def test_catalog() -> None:
    print("[seeded-defect] catalog")
    check("four catalogued defects", set(sd.DEFECTS) == {
        "pier_settlement_cracks", "midspan_concrete_cracking",
        "tendon_rupture", "girder_saw_cut"})
    check("Z24 sequence in campaign order",
          sd.Z24_SEQUENCE == ["pier_settlement_cracks",
                              "midspan_concrete_cracking", "tendon_rupture"])
    check("S101 saw-cut catalogued but not in the demo",
          sd.S101_SEQUENCE == ["girder_saw_cut"])
    check("all defect zones fall inside the 58 m superstructure",
          all(0.0 <= d.zone[0] < d.zone[1] <= 58.0 for d in sd.DEFECTS.values()))
    check("all zones touch the main span (14-44 m)",
          all(d.zone[0] < 44.0 and d.zone[1] > 14.0 for d in sd.DEFECTS.values()))
    check("max EI losses in (0, 0.95]",
          all(0.0 < d.max_ei_loss <= 0.95 for d in sd.DEFECTS.values()))
    check("every defect lowers f1 at full severity",
          all(sd.f1_of_progress({k: 1.0}) < physics.F1_REF - 1e-6
              for k in sd.DEFECTS))
    check("every defect is monotone (more severity -> lower f1)",
          all(sd.f1_of_progress({k: 1.0}) <=
              sd.f1_of_progress({k: 0.5}) <= physics.F1_REF
              for k in sd.DEFECTS))


def test_progress_staging() -> None:
    print("[seeded-defect] alpha staging")
    check("alpha <= 0 -> no defects", sd.progress_from_alpha(0.0) == {})
    check("alpha < 0 clamps to 0", sd.progress_from_alpha(-1.0) == {})
    a33 = sd.progress_from_alpha(0.33)
    check("alpha .33 -> settlement staged in",
          a33["pier_settlement_cracks"] > 0.9
          and a33["midspan_concrete_cracking"] == 0.0
          and a33["tendon_rupture"] == 0.0)
    a67 = sd.progress_from_alpha(0.65)
    check("alpha .65 -> cracking staged in, tendon untouched",
          a67["pier_settlement_cracks"] == 1.0
          and a67["midspan_concrete_cracking"] > 0.9
          and a67["tendon_rupture"] == 0.0)
    a100 = sd.progress_from_alpha(1.0)
    check("alpha 1.0 -> full Z24 sequence",
          all(abs(a100[k] - 1.0) < 1e-9 for k in sd.Z24_SEQUENCE))
    # monotonic: alpha2 > alpha1 => every defect progress non-decreasing
    prev: dict = {}
    for a in np.linspace(0.0, 1.0, 21):
        cur = sd.progress_from_alpha(a)
        for k in sd.Z24_SEQUENCE:
            if k in prev and prev[k] > cur[k] + 1e-9:
                check(f"alpha {a:.2f}: {k} non-decreasing", False,
                      f"{prev[k]:.3f} -> {cur[k]:.3f}")
                return
        prev = cur
    check("all progress values monotone non-decreasing in alpha", True)
    # staged f1 follows the physics: settlement subtle, tendon deep
    f33, f67, f100 = (sd.f1_of_progress(sd.progress_from_alpha(a))
                      for a in (0.33, 0.67, 1.0))
    check("settlement alone is subtle (<1.5% drift)",
          -1.5 <= 100.0 * (f33 / physics.F1_REF - 1.0) < 0.0, f"{f33:.3f}")
    check("full sequence is the deep damage state (Z24 deepest ~ -15%)",
          -18.0 <= 100.0 * (f100 / physics.F1_REF - 1.0) <= -12.0,
          f"{f100:.3f}")
    check("f1 monotone non-increasing across the staged alpha sweep",
          f100 <= f67 <= f33 <= physics.F1_REF,
          f"{f33:.3f} / {f67:.3f} / {f100:.3f}")


def test_fem_consistency() -> None:
    print("[seeded-defect] seeded f1 == FEM first mode")
    for p in (sd.progress_from_alpha(0.33), sd.progress_from_alpha(0.67),
              sd.progress_from_alpha(1.0)):
        fem_f1 = float(physics.fem_modes(sd.ei_profile(p), n_modes=1)[0][0])
        sd_f1 = sd.f1_of_progress(p)
        check(f"progress {len(p)} defects: f1_of_progress == fem_modes",
              abs(fem_f1 - sd_f1) < 1e-6, f"{fem_f1:.4f} vs {sd_f1:.4f}")
    check("healthy (no progress) f1 ~ F1_REF (FEM calibration)",
          abs(sd.f1_of_progress({}) - physics.F1_REF) < 1e-3,
          f"{sd.f1_of_progress({}):.5f} vs {physics.F1_REF}")


def test_per_span_loss() -> None:
    print("[seeded-defect] per-span EI-loss ground truth")
    check("alpha 0 -> no EI loss in any span",
          sd.per_span_loss_pct({}) == [0.0, 0.0, 0.0])
    full = sd.per_span_loss_pct(sd.progress_from_alpha(1.0))
    check("left span (0-14) untouched", abs(full[0]) < 0.5, f"{full[0]}")
    check("right span (44-58) untouched", abs(full[2]) < 0.5, f"{full[2]}")
    check("main span (14-44) carries the seeded loss",
          18.0 <= full[1] <= 30.0, f"{full[1]:.1f}%")
    d = sd.describe(sd.progress_from_alpha(1.0))
    check("worst-span loss reported as ei_loss_pct",
          abs(d["ei_loss_pct"] - max(full)) < 1e-6,
          f"{d['ei_loss_pct']} vs {max(full):.1f}")
    # each defect's own full-severity loss lands in its zone (main span)
    for k in sd.Z24_SEQUENCE:
        p = sd.per_span_loss_pct({k: 1.0})
        check(f"{k} loss confined to main span",
              abs(p[0]) < 0.5 and abs(p[2]) < 0.5 and p[1] > 0.5,
              f"{p}")


def test_describe_honesty() -> None:
    print("[seeded-defect] describe payload honesty")
    healthy = sd.describe({})
    check("healthy label 'none'", healthy["label"] == "none")
    check("healthy no active defects", healthy["active"] == [])
    check("healthy source None", healthy["source"] is None)
    check("healthy f1 == f1_ref == F1_REF",
          abs(healthy["f1"] - physics.F1_REF) < 1e-6
          and abs(healthy["f1_ref"] - physics.F1_REF) < 1e-6)
    check("model names the z24 box girder",
          "z24" in healthy["model"] and "box girder" in healthy["model"])
    check("note says seeded, not certified",
          "seeded" in healthy["note"] and "not a certified" in healthy["note"])

    full = sd.describe(sd.progress_from_alpha(1.0))
    check("full: 3 active defects in campaign order",
          [a["key"] for a in full["active"]] == sd.Z24_SEQUENCE)
    check("full: dominant = tendon rupture (deepest EI loss)",
          full["dominant_key"] == "tendon_rupture"
          and full["dominant"]["ei_loss_pct"] == 45.0)
    check("full: latest (narrative position) = tendon rupture",
          full["latest"]["key"] == "tendon_rupture")
    check("full: source is the Z24 benchmark",
          full["source"] == "Z24 benchmark")
    check("full: sequence == Z24_SEQUENCE",
          full["sequence"] == sd.Z24_SEQUENCE)
    check("full: f1 drift matches describe f1",
          abs(100.0 * (full["f1"] / full["f1_ref"] - 1.0)
              - full["f1_drift_pct"]) < 0.01,
          f"{full['f1_drift_pct']}")
    check("full: every active defect has a zone + source",
          all(a["zone"] and a["source"] for a in full["active"]))


def test_simulator_wiring() -> None:
    print("[seeded-defect] simulator wiring (no forced 4 Hz tonal)")
    from app import simulator as sim_mod

    # default rupture f1_provider == fully-seeded Z24 f1 (~3.2 Hz), NOT 4 Hz
    class _FakeBase:
        nodes = [6, 7, 8]
        fs = 100

        def current_window(self, node: int) -> np.ndarray:
            return np.zeros(1024)

        def tick(self) -> None:
            pass

    rp = sim_mod.Z24RupturePlayer(_FakeBase(), fs=100, healthy_rms=1e-4)
    f1_default = float(rp.f1_provider())
    check("rupture default f1 ~ fully-seeded Z24 (~3.2 Hz)",
          3.05 <= f1_default <= 3.40, f"{f1_default:.3f}")
    check("rupture default f1 is NOT the old forced 4 Hz tonal",
          abs(f1_default - 4.0) > 0.3, f"{f1_default:.3f}")

    # the modal resonance window peaks at the FEM-seeded f1
    full_f1 = float(sd.f1_of_progress(sd.progress_from_alpha(1.0)))
    mp = sim_mod.ModalResonancePlayer(_FakeBase(), amp=0.5, fs=100,
                                      f1_provider=lambda: full_f1)
    win = mp.current_window(7)
    rms = float(np.sqrt(np.mean(win ** 2)))
    # theoretical RMS of the normalised 3-harmonic sum = 0.4714 x amp
    # (sum of sin harmonics, weights 1/1.2.3, divided by 1.75)
    check("resonance window RMS ~ 0.47 x amp (normalised harmonics)",
          0.19 <= rms <= 0.28, f"{rms:.3f}")
    fft = np.abs(np.fft.rfft(win * np.hanning(win.size)))
    freqs = np.fft.rfftfreq(win.size, 1.0 / 100.0)
    peak_hz = float(freqs[np.argmax(fft)])
    check("resonance peak sits at the seeded f1",
          abs(peak_hz - full_f1) < 0.15, f"{peak_hz:.3f} vs {full_f1:.3f}")
    check("no 4 Hz forced tonal in the seeded damage stream",
          abs(peak_hz - 4.0) > 0.3, f"{peak_hz:.3f}")

    # SyntheticPlayer rupture proxies f1_provider through to its player
    sp = sim_mod.SyntheticPlayer("rupture", nodes=[6, 7, 8], fs=100)
    sp.f1_provider = lambda: 3.333
    check("SyntheticPlayer proxies f1_provider",
          abs(sp.f1_provider() - 3.333) < 1e-9)
    # phase accumulator advances per window (f1 can slide without jumps)
    p0 = mp._phase.get(7)
    mp.current_window(7)
    p1 = mp._phase.get(7)
    check("phase accumulator advances (sliding f1 supported)",
          p1 is not None and abs(p1 - p0 - 1024 / 100.0) < 1e-9)


def main() -> int:
    try:
        test_catalog()
        test_progress_staging()
        test_fem_consistency()
        test_per_span_loss()
        test_describe_honesty()
        test_simulator_wiring()
    except Exception as exc:
        global FAIL
        FAIL += 1
        FAILURES.append("seeded-defect tests")
        import traceback
        print(f"  [ERROR] seeded-defect tests raised: {exc}")
        traceback.print_exc()
    print()
    print(f"== seeded-defect gate: {PASS} passed, {FAIL} failed ==")
    if FAILURES:
        print("failures:", ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
