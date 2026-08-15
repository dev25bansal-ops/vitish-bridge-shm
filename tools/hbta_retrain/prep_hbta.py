"""tools/hbta_retrain/prep_hbta.py — convert the HBTA HDF5 (data_100Hz.h5, Hell
Bridge Test Arena, CC-BY-4.0) into the flat window layout the repo's vibration
trainers already consume (`--data <(N,1024) .npy>`).

Why HBTA (PostHackathon §117, per-structure-type retraining): it is a second,
different structural family (full-scale steel truss bridge) with an UNDAMAGED
phase (UDS recordings) and 8 imposed-damage severities (DS1..DS8) — exactly the
healthy-envelope → separation evidence the trained path needs to prove it
generalizes beyond the Z24 box girder.

Outputs (default <out>/):
  healthy_windows.npy  (N_h, 1024) float32 — only UDS (undamaged-state)
                       recordings: the healthy envelope training set.
  damaged_windows.npy  (N_d, 1024) float32 — DS1..DS8 recordings, for the
                       separation check (per-severity capped, seeded).
  labels_damaged.npy   (N_d,) int — damage severity 1..8 aligned 1:1 with
                       damaged_windows.npy.
  healthy_ch.npy       (N_h,) int16 — per-window (sensor,axis) spec index for
  damaged_ch.npy       (N_d,) int16   every window (see channel_names.json), so
                       verify_hbta.py can group per sensor family (SB lower-chord
                       vs SC cross-girders) instead of blurring them together.
  channel_names.json   the spec list: ["SB01:x", ..., "SC07:y"].
  manifest.json        provenance: source h5, recordings, channels, counts.

The healthy/damaged split is by RECORDING (UDS vs DS), never by window, so no
contamination leaks into the envelope.

Usage:
  python prep_hbta.py --h5 data_100Hz.h5 --out hbta_windows --channels AG
  python prep_hbta.py --h5 data_100Hz.h5 --out hbta_windows --channels all
  python prep_hbta.py --h5 data_100Hz.h5 --out hbta_windows \
      --max-recordings 1    # smoke: 1 UDS + 1 DS recording
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import h5py

WINDOW = 1024
GLOBAL_AG = [f"AG{i:02d}" for i in range(1, 19)]      # 18 global accelerometers
LOCAL_AL = [f"AL{i:02d}" for i in range(1, 41)]       # 40 local accelerometers
STRAIN_SB = [f"SB{i:02d}" for i in range(1, 9)]       # 8 strain gages (lower chord)
STRAIN_SC = [f"SC{i:02d}" for i in range(1, 8)]       # 7 strain gages (cross girders)


def _rec_axis(rec_name: str) -> str:
    """Load-direction of a recording: 'Y' or 'Z' (field 4 of MVS_.._.._SM_Y_01)."""
    return rec_name.split("_")[4]


def classify(rec_name: str) -> tuple[str, int]:
    """Return (kind, severity): ('healthy', 0) for *_UDS_*, ('damaged', ds) for
    *_DS<n>* with n in 1..8, else ('other', 0)."""
    if "_UDS_" in rec_name:
        return "healthy", 0
    if "_DS" in rec_name:
        ds = rec_name.split("DS")[1][0]
        if ds.isdigit():
            sev = int(ds)
            if 1 <= sev <= 8:
                return "damaged", sev
    return "other", 0


def channel_specs(group: str, rec_name: str) -> list[tuple[str, str]]:
    """Return [(sensor, axis), ...] for the requested channel group.

    Axis semantics follow the HBTA functions.py conventions: global AG sensors
    carry y AND z (AG09 is z-only); local AL sensors carry z only; the MVS
    sensor AS carries the recording's load direction; strain gages SB carry x
    (lower-chord beams) and SC carry y (cross girders)."""
    ax = _rec_axis(rec_name)
    specs: list[tuple[str, str]] = []
    if group == "AG":
        for s in GLOBAL_AG:
            specs.append((s, "z"))           # AG09 is z-only
            if s != "AG09":
                specs.append((s, "y"))
    elif group == "AL":
        for s in LOCAL_AL:
            specs.append((s, "z"))
    elif group == "AS":
        specs.append(("AS", ax.lower()))
    elif group == "strain":
        for s in STRAIN_SB:
            specs.append((s, "x"))
        for s in STRAIN_SC:
            specs.append((s, "y"))
    elif group == "all":
        for s in GLOBAL_AG:
            specs.append((s, "z"))
            if s != "AG09":
                specs.append((s, "y"))
        for s in LOCAL_AL:
            specs.append((s, "z"))
        specs.append(("AS", ax.lower()))
    return specs


def windows_from(h5: h5py.File, rec_name: str, specs: list[tuple[str, str]],
                 window: int) -> tuple[np.ndarray, np.ndarray]:
    """All non-overlapping windows of every (sensor, axis) in the recording.

    Returns (windows (n_win, window), channel_ids (n_win,) int16) — channel_ids
    is the spec index of the sensor each window came from, so verify_hbta can
    group per sensor family (e.g. SB lower-chord vs SC cross-girders strain)
    instead of blurring them together."""
    out: list[np.ndarray] = []
    chans: list[np.ndarray] = []
    rec = h5[rec_name]
    for ci, (sensor, axis) in enumerate(specs):
        group = "strain" if sensor.startswith(("SB", "SC")) else "acceleration"
        ds = rec[group][sensor][axis]
        n = ds.shape[0]
        if n < window:
            continue
        n_win = n // window
        seg = np.asarray(ds[:n_win * window], dtype=np.float64).reshape(-1, window)
        out.append(seg)
        chans.append(np.full(seg.shape[0], ci, dtype=np.int16))
    if out:
        return np.concatenate(out), np.concatenate(chans)
    return np.zeros((0, window), dtype=np.float64), np.zeros(0, dtype=np.int16)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prepare HBTA windows for vibration retraining")
    ap.add_argument("--h5", default="data_100Hz.h5")
    ap.add_argument("--out", default="hbta_windows")
    ap.add_argument("--channels", default="AG",
                    help="AG | AL | AS | strain | all  (sensor-group expansion)")
    ap.add_argument("--window", type=int, default=WINDOW)
    ap.add_argument("--max-recordings", type=int, default=None,
                    help="smoke: use only the first N healthy + first N damaged")
    ap.add_argument("--max-damaged-per-severity", type=int, default=800,
                    help="cap damaged eval windows per severity (seeded sample)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    h5 = h5py.File(args.h5, "r")
    rec_names = sorted(h5.keys())
    groups = {"healthy": [], "damaged": [], "other": []}
    for r in rec_names:
        kind, _sev = classify(r)
        groups[kind].append(r)
    if args.max_recordings:
        n = args.max_recordings
        healthy = groups["healthy"][:n]
        damaged = groups["damaged"][:n]
    else:
        healthy = groups["healthy"]
        damaged = groups["damaged"]

    if not healthy:
        print(f"  [prep] ERROR: no UDS (undamaged) recordings found in {args.h5} "
              "(healthy envelope needs at least one).", file=sys.stderr)
        h5.close()
        return 1

    specs = channel_specs(args.channels, healthy[0])
    if not specs:
        print(f"  [prep] ERROR: unknown --channels '{args.channels}'.", file=sys.stderr)
        h5.close()
        return 1
    print(f"  [prep] channels={args.channels} -> {len(specs)} (sensor,axis) per recording")
    print(f"  [prep] recordings: {len(healthy)} healthy (UDS) + {len(damaged)} damaged (DS)")

    # ---- healthy envelope windows (ALL windows, no cap) ----------------------
    h_blocks: list[np.ndarray] = []
    h_chans: list[np.ndarray] = []
    for r in healthy:
        w, ch = windows_from(h5, r, specs, args.window)
        h_blocks.append(w)
        h_chans.append(ch)
        print(f"    healthy  {r}  -> {w.shape[0]} windows")
    healthy_w = np.concatenate(h_blocks).astype(np.float32)
    healthy_ch = np.concatenate(h_chans).astype(np.int16)
    print(f"  [prep] healthy windows total {healthy_w.shape[0]} x {healthy_w.shape[1]}")

    # ---- damaged windows, capped per severity (seeded sample) ----------------
    d_windows: list[np.ndarray] = []
    d_chans: list[np.ndarray] = []
    d_labels: list[int] = []
    manifest_dmg: dict[int, int] = {}
    for r in damaged:
        _kind, sev = classify(r)
        w, ch = windows_from(h5, r, specs, args.window)
        if w.shape[0] == 0:
            continue
        idx = np.arange(w.shape[0])
        if w.shape[0] > args.max_damaged_per_severity:
            idx = np.sort(rng.choice(idx, args.max_damaged_per_severity, replace=False))
        d_windows.append(w[idx])
        d_chans.append(ch[idx])
        d_labels.append(np.full(len(idx), sev, dtype=np.int64))
        manifest_dmg[sev] = manifest_dmg.get(sev, 0) + int(len(idx))
        print(f"    damaged  {r}  sev{sev} -> {len(idx)} windows")
    damaged_w = np.concatenate(d_windows).astype(np.float32) if d_windows else \
        np.zeros((0, args.window), dtype=np.float32)
    damaged_ch = np.concatenate(d_chans).astype(np.int16) if d_chans else \
        np.zeros(0, dtype=np.int16)
    labels_d = np.concatenate(d_labels) if d_labels else np.zeros(0, dtype=np.int64)
    print(f"  [prep] damaged windows total {damaged_w.shape[0]} x {damaged_w.shape[1]} "
          f"(per-severity: {manifest_dmg})")

    np.save(outdir / "healthy_windows.npy", healthy_w)
    np.save(outdir / "damaged_windows.npy", damaged_w)
    np.save(outdir / "labels_damaged.npy", labels_d)
    np.save(outdir / "healthy_ch.npy", healthy_ch)
    np.save(outdir / "damaged_ch.npy", damaged_ch)
    (outdir / "channel_names.json").write_text(json.dumps(
        [f"{s}:{ax}" for s, ax in specs], indent=2), encoding="utf-8")
    (outdir / "manifest.json").write_text(json.dumps({
        "source": args.h5,
        "channels": args.channels,
        "n_channels": len(specs),
        "window": args.window,
        "healthy_recordings": healthy,
        "damaged_recordings": damaged,
        "healthy_windows": int(healthy_w.shape[0]),
        "damaged_windows": int(damaged_w.shape[0]),
        "damaged_per_severity": {str(k): v for k, v in sorted(manifest_dmg.items())},
        "provenance": "healthy_ch.npy / damaged_ch.npy hold the per-window "
                      "(sensor,axis) spec index (see channel_names.json)",
        "note": "healthy/damaged split is by recording (UDS vs DS), never by window",
    }, indent=2), encoding="utf-8")

    h5.close()
    print(f"  [prep] wrote {outdir/'healthy_windows.npy'}, "
          f"{outdir/'damaged_windows.npy'}, {outdir/'labels_damaged.npy'}, "
          f"{outdir/'healthy_ch.npy'}, {outdir/'damaged_ch.npy'}, "
          f"{outdir/'channel_names.json'}, {outdir/'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
