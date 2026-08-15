"""tools/hbta_retrain/verify_hbta.py — measure trained-envelope separation on
the HBTA per-structure retrain, the same honest way gate 10 / gate 16 measure
the Z24 retrain.

Loads the retrained AnomalyDetector from <weights>, warms the healthy envelope
on held-out healthy (UDS) windows, then reports trained_deviation on healthy
vs damaged, per severity DS1..DS8.  Deterministic: torch/numpy seeded; healthy
envelope windows are drawn in fixed order.

Reports three levels of evidence:
  1. score-level table   — trained_deviation (the shipped envelope-floor+push
     score), the same honest way gate 10 / gate 16 measure the Z24 retrain.
  2. feature-level table — raw rms/peak_freq per sensor family with healthy-2σ
     marks, when prep's channel provenance is present.
  3. RMS reference monitor — a minimal feature-level detector (healthy-p5 RMS
     lower envelope per family): % damaged windows below it vs. the held-out
     healthy false-alarm floor. Measured rates only; NOT the trained path and
     not the gate — the exit code is driven by level 1.

Honest expectation: healthy dev stays ~0; damaged dev rises with severity.  If
it does NOT separate, that is the finding — report it, do not massage it.

Usage:
  python verify_hbta.py --weights hbta_weights \
      --healthy hbta_windows/healthy_windows.npy \
      --damaged hbta_windows/damaged_windows.npy \
      --labels hbta_windows/labels_damaged.npy
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Locate the repo root / tar root that actually contains models/vibration
# (works both in-repo and in the extracted tar layout).
_here = Path(__file__).resolve()
for _cand in (_here.parent, _here.parents[1], _here.parents[2], _here.parents[3]):
    if (_cand / "models" / "vibration").exists():
        sys.path.insert(0, str(_cand))
        break
from models.vibration.infer import AnomalyDetector  # noqa: E402
from models.vibration.features import extract_features  # noqa: E402

PEAK_FREQ = 1   # feature index in FEATURE_NAMES ('rms','peak_freq',...)
RMS = 0


def _seeded() -> None:
    import torch
    torch.manual_seed(0)
    np.random.seed(0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify HBTA retrain separation")
    ap.add_argument("--weights", default="hbta_weights")
    ap.add_argument("--healthy", default="hbta_windows/healthy_windows.npy")
    ap.add_argument("--damaged", default="hbta_windows/damaged_windows.npy")
    ap.add_argument("--labels", default="hbta_windows/labels_damaged.npy")
    ap.add_argument("--warmup", type=int, default=30,
                    help="healthy windows absorbed into the envelope")
    ap.add_argument("--eval-each", type=int, default=60,
                    help="windows measured per class / severity")
    args = ap.parse_args(argv)

    _seeded()
    healthy = np.load(args.healthy)
    damaged = np.load(args.damaged)
    labels = np.load(args.labels).ravel()
    print(f"[verify] HBTA retrain separation  weights={args.weights}")
    print(f"  healthy windows {healthy.shape[0]} | damaged windows "
          f"{damaged.shape[0]} | severities {sorted(set(labels.tolist()))}")

    det = AnomalyDetector(weights_dir=args.weights, n_healthy=args.warmup)
    if not det.has_trained_models:
        print("  ERROR: no trained artifacts loaded from the weights dir. "
              "Did training succeed?", file=sys.stderr)
        return 1

    # warm the healthy envelope on the FIRST warmup windows (fixed order)
    for i in range(min(args.warmup, healthy.shape[0])):
        det.score(healthy[i])

    def devs(windows: np.ndarray, n: int) -> np.ndarray:
        return np.array([det.trained_deviation(windows[i]) for i in range(n)])

    h_eval = devs(healthy[args.warmup:], args.eval_each)
    h_raw = np.mean([det._trained_raw(healthy[args.warmup + i])[0]
                     for i in range(min(20, args.eval_each))])

    print(f"\n  healthy (held-out UDS)   n={len(h_eval)}  dev mean {h_eval.mean():.4f} "
          f"max {h_eval.max():.4f}   raw {h_raw:.4f}")

    rows: list[tuple[int, int, float, float, float]] = []
    for sev in sorted(set(labels.tolist())):
        idx = np.where(labels == sev)[0]
        if len(idx) == 0:
            continue
        n = min(args.eval_each, len(idx))
        d = np.array([det.trained_deviation(damaged[idx[j]]) for j in range(n)])
        rows.append((sev, n, float(d.mean()), float(np.percentile(d, 95)), float(d.max())))

    for sev, n, mean, p95, mx in rows:
        bar = "#" * int(round(mean * 40))
        print(f"  damaged DS{sev:<2d} n={n:<4d} dev mean {mean:.4f}  p95 {p95:.4f}  "
              f"max {mx:.4f}  |{bar}")

    if not rows:
        print("  ERROR: no damaged windows measured.", file=sys.stderr)
        return 1

    h_hi = h_eval.max()
    d_mid = max(r[2] for r in rows if r[0] >= 3) if any(r[0] >= 3 for r in rows) else 0.0
    separates = h_hi < 0.05 and d_mid > h_eval.mean() + 0.05
    if separates:
        verdict = f"SEPARATES (healthy max {h_hi:.4f} ~0; mid+ severity deviates)"
    else:
        verdict = f"CHECK — healthy max {h_hi:.4f}, mid-severity mean {d_mid:.4f} (report honestly)"
    print(f"\n  score-level verdict: {verdict}")
    print("  (healthy dev ~0 = envelope absorbs healthy; damaged dev > 0 = the "
          "trained path sees the imposed damage)")

    # ---- feature-level evidence (honest, measured; NOT a detector pass) ------
    # The trained score may absorb a real feature shift (see README). Report the
    # raw per-window features directly, grouped per sensor family when prep's
    # channel provenance is present, so a real feature-level separation is
    # surfaced even when the score-level envelope does not rank it.
    print("\n  feature-level evidence (raw window features, measured; NOT a detector pass):")
    hcp = Path(args.healthy).with_name("healthy_ch.npy")
    dcp = Path(args.healthy).with_name("damaged_ch.npy")
    cnp = Path(args.healthy).with_name("channel_names.json")
    prov = None
    if hcp.exists() and dcp.exists() and cnp.exists():
        prov = (json.loads(cnp.read_text(encoding="utf-8")),
                np.load(hcp), np.load(dcp))

    if prov:
        cnames, hc, dc = prov
        families: dict[str, list[int]] = {}
        for ci, spec in enumerate(cnames):
            families.setdefault(spec.split(":")[0][:2], []).append(ci)
        for fam in sorted(families):
            idxs = np.array(families[fam])
            print(f"    family {fam}  channels {[cnames[i] for i in idxs]}")
            h_fam = np.where(np.isin(hc[args.warmup:], idxs))[0][:90]
            H = np.array([extract_features(healthy[args.warmup + i], fs=100.0)
                          for i in h_fam])
            for fi, flab in ((PEAK_FREQ, "peak_freq"), (RMS, "rms")):
                lo, hi = H[:, fi].mean() - 2.0 * H[:, fi].std(), \
                         H[:, fi].mean() + 2.0 * H[:, fi].std()
                print(f"      healthy n={len(H)}  {flab} {H[:, fi].mean():7.3f}±"
                      f"{H[:, fi].std():5.3f}   2σ band {lo:.3f}–{hi:.3f}")
            # per-severity feature bands, marked when a mean leaves the healthy 2σ
            h_lo = {fi: H[:, fi].mean() - 2.0 * H[:, fi].std() for fi in (PEAK_FREQ, RMS)}
            h_hi = {fi: H[:, fi].mean() + 2.0 * H[:, fi].std() for fi in (PEAK_FREQ, RMS)}
            for sev, _n, _m, _p, _x in rows:
                d_idx = np.where((labels == sev) & np.isin(dc, idxs))[0][:60]
                if len(d_idx) == 0:
                    continue
                D = np.array([extract_features(damaged[i], fs=100.0) for i in d_idx])
                marks = "".join(
                    "*" if (D[:, fi].mean() < h_lo[fi] or D[:, fi].mean() > h_hi[fi])
                    else " " for fi in (PEAK_FREQ, RMS))
                print(f"      DS{sev:<2d} n={len(D):<3d} peak_freq {D[:, PEAK_FREQ].mean():7.3f} Hz"
                      f"   rms {D[:, RMS].mean():.4f}   {marks}"
                      f"  (* = feature mean outside healthy 2σ: peak_freq, rms)")
    else:
        # no channel provenance (older prep output) — blended fallback
        feats = np.array([extract_features(healthy[args.warmup + i], fs=100.0)
                          for i in range(min(120, args.eval_each))])
        print(f"    healthy   n={len(feats)}  peak_freq {feats[:, PEAK_FREQ].mean():7.3f}±"
              f"{feats[:, PEAK_FREQ].std():5.3f} Hz   rms {feats[:, RMS].mean():.4f}")
        for sev, _n, _m, _p, _x in rows:
            idx = np.where(labels == sev)[0]
            n = min(args.eval_each, len(idx))
            fe = np.array([extract_features(damaged[idx[j]], fs=100.0) for j in range(n)])
            print(f"    damaged DS{sev:<2d} n={n:<4d}  peak_freq {fe[:, PEAK_FREQ].mean():7.3f} Hz"
                  f"   rms {fe[:, RMS].mean():.4f}")
        hp_hi = feats[:, PEAK_FREQ].mean() + 2.0 * feats[:, PEAK_FREQ].std()
        hp_lo = feats[:, PEAK_FREQ].mean() - 2.0 * feats[:, PEAK_FREQ].std()
        print(f"    blended healthy 2σ band {hp_lo:.2f}–{hp_hi:.2f} Hz (SB+SC blurred — "
              f"re-run prep_hbta.py to emit per-family channel provenance)")

    # ---- RMS reference monitor (feature-level detector; NOT the trained path) -
    # The trained score was silent on HBTA damage (score-level CHECK above). The
    # only reproducible feature-level response is a strain-RMS drop. This block
    # is a minimal reference detector: warm a healthy RMS lower envelope (p5
    # percentile of healthy-window RMS, per sensor family), then measure what
    # fraction of damaged windows drop below it vs. what fraction of held-out
    # healthy windows do (the false-alarm floor). Reported as measured rates —
    # no verdict forcing; the score-level gate above is still the exit code.
    print("\n  RMS reference monitor (per-family, healthy-p5 lower envelope):")
    if prov:
        cnames, hc, dc = prov
        families = {}
        for ci, spec in enumerate(cnames):
            families.setdefault(spec.split(":")[0][:2], []).append(ci)
        for fam in sorted(families):
            idxs = np.array(families[fam])
            fam_healthy = np.where(np.isin(hc, idxs))[0]   # all healthy of this family
            # STRATIFIED warmup: prep is channel-major within recording, so the
            # first-N healthy windows all come from one recording and mis-estimate
            # the envelope (measured: 30-window warmup -> 54% false-alarm). Sample
            # every k-th family window in fixed order to span all recordings.
            k = max(1, len(fam_healthy) // args.warmup)
            warm = fam_healthy[::k][:args.warmup]
            if len(warm) < 10:
                print(f"    family {fam}: <10 warmup windows, skipped")
                continue
            rw = np.array([extract_features(healthy[i], fs=100.0)[RMS] for i in warm])
            lo = float(np.percentile(rw, 5.0))
            ev = np.setdiff1d(fam_healthy, warm)[:3000]
            rh = np.array([extract_features(healthy[i], fs=100.0)[RMS] for i in ev])
            fa = float((rh < lo).mean()) * 100.0
            print(f"    family {fam}: stratified warmup n={len(warm)} (stride {k}) "
                  f"RMS p5={lo:.4f} | held-out healthy false-alarm {fa:.1f}% (n={len(ev)})")
            dets: list[float] = []
            for sev, _n, _m, _p, _x in rows:
                d_idx = np.where((labels == sev) & np.isin(dc, idxs))[0]
                n_d = min(800, len(d_idx))
                rd = np.array([extract_features(damaged[i], fs=100.0)[RMS]
                               for i in d_idx[:n_d]])
                det = float((rd < lo).mean()) * 100.0
                dets.append(det)
                print(f"      DS{sev:<2d}  detected {det:5.1f}%  (n={len(rd)})")
            if dets:
                print(f"    family {fam}: detection DS1..DS8 {min(dets):.1f}%–"
                      f"{max(dets):.1f}% vs false-alarm {fa:.1f}%")
    else:
        print("    (no channel provenance — re-run prep_hbta.py to emit per-family evidence)")
    return 0 if separates else 2


if __name__ == "__main__":
    sys.exit(main())
