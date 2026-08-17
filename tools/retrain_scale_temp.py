"""
tools/retrain_scale_temp.py — temperature-invariant + scale-robust retrain
(§7.6 item 17).

Goal: make the trained ensemble's evidence fire at demo scale AND remove the
documented healthy-state confounds (gate-16 LEG C labels {1}/{6}) while the
deterministic spectral floor stays the demo's base.  Three mechanisms:

  1. SCALE: the LSTM-AE head is trained on RMS-normalized windows and the
     inference path normalizes by RMS, so demo-scale (RMS ~0.05) and real-Z24
     (RMS ~1e-3) map into one dynamic range.  The VAE/OCSVM head works on the
     7-dim feature vector with amplitude kept — the demo family is *included*
     in its training corpus, so demo-scale health is in-distribution.
  2. TEMPERATURE: the VAE/OCSVM is trained in features mode with the
     temperature covariate (feature 6, previously always 0.0) populated.  Each
     healthy window is time-stretched to EVERY point of a dense temperature
     grid and paired with that grid temperature (the DIAGONAL of the
     spectrum-vs-temperature plane — the physically valid set: a healthy
     bridge's spectrum at T sits at the thermal f1 expectation for T).  The
     envelope learns that the whole seasonal f1 drift is healthy AT THE RIGHT
     TEMPERATURE; anything below the entire seasonal band (real stiffness loss)
     is out-of-distribution at every temperature.  That is what removes the
     label-{6} thermal-wandering confound without flattening damage away.
  3. DEMO FAMILY: the steady pink+resonance healthy demo windows and the
     seeded-rupture damage windows are added to the corpus (healthy for
     training, damage for evaluation only), so the trained raw separates
     demo-scale health from demo-scale damage instead of saturating.

Inference contracts preserved: same vae.pt/ocsvm.pkl/scaler.pkl/lstm_ae.pt
sibling set; the checkpoints carry extra config ('mode': 'features',
'scale_norm': true) that `infer.AnomalyDetector` reads to branch.

Usage:
  python tools/retrain_scale_temp.py --outdir models/weights_scale_temp \
      --epochs-vae 40 --epochs-lstm 30 --seed 0
  python tools/retrain_scale_temp.py --scratch --epochs-vae 25  # fixture-only, fast

Weights are written to --outdir; they are NOT installed into models/weights/
until a probe shows the LEG C/D bounds flip AND verify_demo_arc re-pins.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- model modules -----------------------------------------------------------
import torch  # noqa: E402

from models.vibration import features as feat_mod  # noqa: E402
from models.vibration import seeded_defect as _sd  # noqa: E402
from models.vibration import stiffness as physics  # noqa: E402
from models.vibration import temperature as temp  # noqa: E402
from models.vibration.train_lstm_ae import LSTMAE, mc_reconstruction_losses  # noqa: E402
from models.vibration.train_vae_ocsvm import VAE  # noqa: E402

F1_REF = float(physics.F1_REF)          # 3.80 Hz healthy reference
WINDOW_N = 1024
FS = 100.0
Z24 = ROOT / "data" / "z24" / "inputs.npy"
Z24_LABELS = Z24.with_name("labels.npy")
CHANNELS = (6, 7, 8)
HEALTHY_LABELS = (0, 1, 6)
DEMO_SAMPLE_RATE = 2 * F1_REF             # ~7.6 Hz — matches the demo player family

# Coordinated (DIAGONAL) augmentation grid: every healthy window time-stretched
# to each grid temperature's thermal f1 and paired with THAT temperature.  The
# healthy manifold is the thin curve {(spectrum at Ts, T) : Ts ≈ T}, covering the
# full seasonal range; damaged f1 sits below the coldest point of the curve and
# therefore out-of-distribution at every T.
T_GRID = (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0)
LSTM_CORPUS_TARGET = 8000                 # raw-window subsample for the LSTM head


def t_log(*a) -> None:
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


# ---- augmentation helpers (pure numpy, deterministic) -------------------------
def rms_norm(w: np.ndarray) -> np.ndarray:
    s = float(np.sqrt(np.mean(np.asarray(w, dtype=np.float64) ** 2))) or 1.0
    return np.asarray(w, dtype=np.float64) / s


def time_stretch(w: np.ndarray, factor: float) -> np.ndarray:
    """Resample to 1024 keeping the same length by scaling the time axis.

    factor > 1 lowers all frequencies (stretch in time); factor < 1 raises them.
    `np.interp` gives a deterministic linear reconstruction on the fixed grid.
    """
    w = np.asarray(w, dtype=np.float64).ravel()
    n = w.size
    src = np.linspace(0.0, float(n - 1), n)
    grid = np.clip(src / max(factor, 1e-6), 0.0, float(n - 1))
    return np.interp(grid, src, w)


def spectral_factor(target_temp_c: float) -> float:
    """Time-stretch factor that maps a reference-f1 spectrum to ``target_temp_c``'s
    thermal expectation (expected_f1(F1_REF, T) / F1_REF)."""
    f1 = temp.expected_f1(F1_REF, target_temp_c)
    return max(float(F1_REF / f1), 1e-6)


def window_features(w: np.ndarray, t_query_c: float) -> np.ndarray:
    """7-dim feature vector with the temperature covariate populated."""
    return feat_mod.extract_features(w, fs=FS, temperature=t_query_c)


def full_healthy_windows() -> tuple[np.ndarray, np.ndarray]:
    """All Z24 healthy {0,1,6} windows (every segment, channels 6/7/8)."""
    arr = np.load(Z24, mmap_mode="r")
    lab = np.load(Z24_LABELS).ravel()
    out: list[np.ndarray] = []
    for target in HEALTHY_LABELS:
        for s in np.where(lab == target)[0]:
            for c in CHANNELS:
                row = arr[s, c]
                for i in range(0, 6000 - WINDOW_N + 1, WINDOW_N):
                    out.append(row[i:i + WINDOW_N])
    return np.stack(out).astype(np.float64), np.asarray(lab)


def demo_healthy_windows(n_windows: int = 12, seed0: int = 0) -> list[np.ndarray]:
    """The demo's steady healthy family (pink noise + first-mode resonance at the
    seasonal f1) across the year — the signal the demo storyboard streams."""
    rng = np.random.default_rng(999)
    freq = np.fft.rfftfreq(WINDOW_N)
    amps = np.empty(len(freq)); amps[0] = 0.0
    amps[1:] = 1.0 / np.sqrt(np.maximum(freq[1:], 1e-9))
    spec = rng.standard_normal(len(freq)) + 1j * rng.standard_normal(len(freq))
    spec[0] = 0.0
    pink = np.fft.irfft(spec * amps, WINDOW_N)
    pink = pink / (np.std(pink) + 1e-12)
    out = []
    for doy in (15, 105, 205, 300, 315):
        f1 = temp.expected_f1(F1_REF, temp.seasonal_temp_c(doy))
        t = np.arange(WINDOW_N) / FS
        for i in range(n_windows):
            rng2 = np.random.default_rng(seed0 + i + int(doy))
            ph = rng2.uniform(0.0, 2.0 * np.pi)
            res = (np.sin(2 * np.pi * f1 * t + ph)
                   + 0.5 * np.sin(4 * np.pi * f1 * t + 2 * ph)) / 1.12
            w = 0.6 * 0.05 * pink + 0.05 * pink + 0.015 * res
            out.append(0.06 * w / (np.std(w) + 1e-12))  # demo RMS ~0.05-0.06
    return out


def demo_damage_windows(f1_dmg: float, n_windows: int = 12, seed0: int = 10) -> list[np.ndarray]:
    """The demo's seeded-rupture windows (strong 3-harmonic standing wave at the
    damaged f1) — evaluation only, never part of the healthy training corpus."""
    rng = np.random.default_rng(999)
    freq = np.fft.rfftfreq(WINDOW_N)
    amps = np.empty(len(freq)); amps[0] = 0.0
    amps[1:] = 1.0 / np.sqrt(np.maximum(freq[1:], 1e-9))
    spec = rng.standard_normal(len(freq)) + 1j * rng.standard_normal(len(freq))
    spec[0] = 0.0
    pink = np.fft.irfft(spec * amps, WINDOW_N)
    pink = pink / (np.std(pink) + 1e-12)
    t = np.arange(WINDOW_N) / FS
    out = []
    for i in range(n_windows):
        rng2 = np.random.default_rng(seed0 + i)
        ph = rng2.uniform(0.0, 2.0 * np.pi)
        sig = (np.sin(2 * np.pi * f1_dmg * t + ph)
               + 0.5 * np.sin(4 * np.pi * f1_dmg * t + 2 * ph)
               + (1 / 3) * np.sin(6 * np.pi * f1_dmg * t + 3 * ph)) / 1.75
        w = 0.6 * 0.05 * pink + 0.05 * pink + 0.55 * sig
        out.append(0.75 * w / (np.std(w) + 1e-12))  # damage RMS higher than healthy
    return out


def build_feature_corpus(healthy: list[np.ndarray]) -> np.ndarray:
    """Coordinated (DIAGONAL) augmented 7-dim feature matrix.

    Every healthy window is time-stretched to each T_GRID temperature's thermal
    f1 and labelled with the SAME temperature — the envelope learns the true
    healthy f1(T) curve (a thin 1-D set in feature space).  A window whose
    spectrum sits at T's thermal expectation is healthy AT T; real stiffness
    loss (f1 below the entire seasonal band) is off the curve at every T."""
    rows: list[np.ndarray] = []
    for w in healthy:
        for t in T_GRID:
            sw = time_stretch(w, spectral_factor(t))
            rows.append(window_features(sw, t))
    X = np.stack(rows).astype(np.float32)
    t_log(f"feature corpus: {X.shape[0]} rows x {X.shape[1]} "
          f"({len(healthy)} windows x {len(T_GRID)} aug along the T-diagonal)")
    return X


def build_lstm_corpus(healthy: list[np.ndarray], target: int) -> np.ndarray:
    """RMS-normalized raw windows subsampled to `target` — scale-robust LSTM."""
    rows: list[np.ndarray] = []
    for w in healthy:
        for t in T_GRID:
            rows.append(rms_norm(time_stretch(w, spectral_factor(t))))
    if len(rows) > target:
        rng = np.random.default_rng(0)
        idx = rng.choice(len(rows), size=target, replace=False)
        rows = [rows[i] for i in idx]
    return np.stack(rows).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=str(ROOT / "models" / "weights_scale_temp"))
    ap.add_argument("--epochs-vae", type=int, default=40)
    ap.add_argument("--epochs-lstm", type=int, default=30)
    ap.add_argument("--latent-dim", type=int, default=16)
    ap.add_argument("--beta", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scratch", action="store_true",
                    help="fast scratch mode: fixture-scale corpus, short epochs")
    ap.add_argument("--device", choices=["auto", "cpu"], default="auto")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cpu" if args.device == "cpu"
                          else ("cuda" if torch.cuda.is_available() else "cpu"))
    t_log(f"device={device} torch={torch.__version__}")
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # ---- assemble the healthy corpus ---------------------------------------
    if args.scratch:
        # fixture-scale: 180 windows per healthy label from the committed fixture
        fix = ROOT / "data" / "z24" / "fixture"
        healthy = [w for f in ("healthy0.npy", "healthy1.npy", "label6.npy")
                   for w in np.load(fix / f).astype(np.float64)]
    else:
        w_all, _ = full_healthy_windows()
        # deterministic spread across the three healthy labels
        rng = np.random.default_rng(7)
        keep = rng.choice(w_all.shape[0], size=min(w_all.shape[0], 9000),
                          replace=False)
        healthy = list(w_all[keep])
        t_log(f"Z24 healthy windows kept: {len(healthy)} of {w_all.shape[0]}")
        del w_all

    healthy += demo_healthy_windows()          # demo-scale health in-distribution
    t_log(f"healthy corpus total: {len(healthy)} base windows")

    X_feat = build_feature_corpus(healthy)
    X_lstm = build_lstm_corpus(healthy, LSTM_CORPUS_TARGET)

    # ---- VAE + OCSVM on the 7-dim feature vector (temperature populated) ----
    from sklearn.preprocessing import StandardScaler  # noqa: E402

    scaler = StandardScaler().fit(X_feat)
    scaler.scale_ = np.maximum(np.asarray(scaler.scale_), 1e-6)  # never degenerate
    Xs = scaler.transform(X_feat).astype(np.float32)

    vae = VAE(input_dim=X_feat.shape[1], latent_dim=args.latent_dim, dropout=0.1).to(device)
    opt = torch.optim.Adam(vae.parameters(), lr=1e-3, weight_decay=1e-5)
    batch = 256
    Xt = torch.tensor(Xs, dtype=torch.float32, device=device)
    n = Xt.shape[0]
    vae.train()
    for ep in range(args.epochs_vae):
        perm = torch.randperm(n, device=device)
        ep_loss = 0.0
        for i in range(0, n, batch):
            xb = Xt[perm[i:i + batch]]
            recon, mu, logvar = vae(xb)
            kld = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.clamp(max=10.0).exp())
            loss = torch.mean((recon - xb) ** 2) + args.beta * kld
            opt.zero_grad()
            if bool(torch.isfinite(loss)):
                loss.backward(); opt.step()
                ep_loss += float(loss.item()) * xb.shape[0]
        if (ep + 1) % 10 == 0 or ep == 0:
            t_log(f"  [vae] epoch {ep+1}/{args.epochs_vae} loss={ep_loss/n:.6f}")
    vae.eval()
    with torch.no_grad():
        mu, _ = vae.encode(torch.tensor(Xs, dtype=torch.float32, device=device))
        latents = mu.cpu().numpy()
        recon, _, _ = vae(Xt)
        recon_losses = ((recon - Xt) ** 2).mean(dim=1).cpu().numpy()
    assert np.isfinite(latents).all(), "non-finite latents — abort, do not ship"
    from sklearn.svm import OneClassSVM  # noqa: E402
    ocsvm = OneClassSVM(kernel="rbf", gamma="scale", nu=0.01).fit(latents)

    # ---- LSTM-AE on RMS-normalized raw windows -----------------------------
    lstm = LSTMAE(seq_len=WINDOW_N, hidden=32, latent_dim=args.latent_dim, dropout=0.2).to(device)
    lopt = torch.optim.Adam(lstm.parameters(), lr=1e-3, weight_decay=1e-5)
    lt = torch.tensor(X_lstm, dtype=torch.float32, device=device).unsqueeze(-1)
    lopt.zero_grad()
    lbatch = 64
    for ep in range(args.epochs_lstm):
        perm = torch.randperm(lt.shape[0], device=device)
        ep_loss = 0.0
        for i in range(0, lt.shape[0], lbatch):
            xb = lt[perm[i:i + lbatch]]
            recon = lstm(xb)
            loss = torch.mean((recon - xb.squeeze(-1)) ** 2)
            lopt.zero_grad()
            if bool(torch.isfinite(loss)):
                loss.backward(); lopt.step()
                ep_loss += float(loss.item()) * xb.shape[0]
        if (ep + 1) % 10 == 0 or ep == 0:
            t_log(f"  [lstm] epoch {ep+1}/{args.epochs_lstm} loss={ep_loss/lt.shape[0]:.6f}")
    lstm.eval()
    lper = mc_reconstruction_losses(lstm, X_lstm[:512], n_samples=1, device=device)[0]
    lthresh = float(np.percentile(lper, 95))
    lcv = float(np.mean(mc_reconstruction_losses(lstm, X_lstm[:256], n_samples=5,
                                                 device=device).std(axis=0)
                        / (np.mean(mc_reconstruction_losses(lstm, X_lstm[:256],
                                                            n_samples=5,
                                                            device=device), axis=0) + 1e-9)))

    # ---- save artifacts (feature-scope vae + scale-norm lstm) --------------
    def _dump(path: Path, obj) -> None:
        try:
            import joblib; joblib.dump(obj, path)
        except Exception:
            import pickle
            with open(path, "wb") as fh:
                pickle.dump(obj, fh)

    torch.save({"state_dict": vae.state_dict(), "input_dim": int(X_feat.shape[1]),
                "latent_dim": args.latent_dim, "mode": "features",
                "temperature": True, "dropout": 0.1, "beta": args.beta,
                "healthy_recon_loss": float(np.mean(recon_losses)),
                "healthy_recon_std": float(np.std(recon_losses)),
                "threshold_p95": float(np.percentile(recon_losses, 95))},
               outdir / "vae.pt")
    _dump(outdir / "ocsvm.pkl", ocsvm)
    _dump(outdir / "scaler.pkl", scaler)
    torch.save({"state_dict": lstm.state_dict(), "seq_len": WINDOW_N, "hidden": 32,
                "latent_dim": args.latent_dim, "dropout": lstm.dropout,
                "threshold": lthresh, "healthy_mean_loss": float(lper.mean()),
                "healthy_std_loss": float(lper.std()), "healthy_dropout_cv": lcv,
                "mc_samples": 5, "scale_norm": True},
               outdir / "lstm_ae.pt")
    (outdir / "train_meta.json").write_text(json.dumps({
        "artifact": "scale+temp-robust ensemble (item 17)",
        "vae_mode": "features", "vae_temperature": True,
        "lstm_scale_norm": True,
        "n_feature_rows": int(X_feat.shape[0]), "n_lstm_windows": int(X_lstm.shape[0]),
        "t_grid": list(T_GRID),
        "epochs_vae": args.epochs_vae, "epochs_lstm": args.epochs_lstm,
        "seed": args.seed,
    }, indent=2), encoding="utf-8")
    t_log(f"wrote {outdir/'vae.pt'}, ocsvm.pkl, scaler.pkl, lstm_ae.pt, train_meta.json")
    t_log("train_meta: " + json.dumps(json.loads((outdir / 'train_meta.json').read_text('utf-8'))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())