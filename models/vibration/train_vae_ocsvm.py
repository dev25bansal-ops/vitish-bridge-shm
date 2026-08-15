"""
vibration/train_vae_ocsvm.py — train a VAE (torch) on healthy Z24 windows,
then a one-class SVM (sklearn) on the VAE latent space.

Outputs (default models/weights/):
    vae.pt      torch checkpoint dict {state_dict, input_dim, latent_dim,
                                       mode(raw|features), dropout, beta}
    ocsvm.pkl   fitted sklearn OneClassSVM on latent means (joblib)
    scaler.pkl  fitted sklearn StandardScaler on the VAE input
    train_meta.json  training summary + data provenance

Data input:
    --data <path>  one of
      * inputs.npy  (segments, channels, samples)  Z24-processed layout
        -> uses labels.npy beside it to keep only healthy labels [0,1,6]
      * any.npy with shape (N, 1024)  -> raw windows already sliced
      * a directory containing inputs.npy + labels.npy
      * a CSV of raw windows (N rows x 1024 cols)
    If missing / no healthy segments -> a small synthetic healthy set is
    generated so the training code stays exercisable (labelled in meta).

Usage:
    python models/vibration/train_vae_ocsvm.py --data data/z24/inputs.npy --epochs 50
    python models/vibration/train_vae_ocsvm.py --synthetic --mode features --epochs 30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover
    print("ERROR: torch is not installed. Cannot train VAE.", file=sys.stderr)
    sys.exit(1)

try:
    from . import features as feat_mod
except ImportError:  # bare-script run
    import features as feat_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOW_N = 1024
Z24_CHANNELS = 27
Z24_SIM_NODES = [6, 7, 8]


# ---------------------------------------------------------------------------
# Synthetic healthy windows (deterministic) — used only when real data is absent
# ---------------------------------------------------------------------------
def synthetic_healthy_windows(n: int = 240, window_n: int = WINDOW_N, fs: float = 100.0,
                              seed: int = 0) -> np.ndarray:
    """Sum of a few random low-frequency sinusoids + AR(1) noise, RMS ~0.05-0.12."""
    rng = np.random.default_rng(seed)
    t = np.arange(window_n) / fs
    out = np.zeros((n, window_n))
    for i in range(n):
        x = np.zeros(window_n)
        for _ in range(int(rng.integers(3, 6))):
            amp = rng.uniform(0.01, 0.05)
            f0 = rng.uniform(1.5, 12.0)
            ph = rng.uniform(0, 2 * np.pi)
            x += amp * np.sin(2 * np.pi * f0 * t + ph)
        rho = rng.uniform(0.2, 0.5)
        noise = rng.standard_normal(window_n)
        for j in range(1, window_n):
            noise[j] += rho * noise[j - 1]
        x = x + 0.01 * noise
        x *= rng.uniform(0.8, 1.4) / max(np.sqrt(np.mean(x ** 2)), 1e-9)
        out[i] = x * 0.08  # target RMS ~0.08
    return out.astype(np.float32)


# ---------------------------------------------------------------------------
# Data loading (robust to missing data — always returns something + provenance)
# ---------------------------------------------------------------------------
def load_windows(data: str | None, healthy_labels=None, window_n: int = WINDOW_N,
                 fs: float = 100.0) -> tuple[np.ndarray, dict]:
    """Return (windows (N,window_n) float32, provenance dict)."""
    healthy_labels = healthy_labels or [0, 1, 6]
    meta: dict = {"source": "synthetic", "synthetic": True}

    if data is None:
        print("  [data] --data not provided -> using SYNTHETIC healthy windows "
              "(real Z24 data optional; drop inputs.npy/labels.npy beside it).")
        return synthetic_healthy_windows(), meta

    path = Path(data).expanduser()
    if not path.exists():
        print(f"  [data] WARNING: '{path}' not found -> falling back to synthetic healthy set.")
        return synthetic_healthy_windows(), meta

    try:
        if path.is_dir():
            cand = path / "inputs.npy"
            if cand.exists():
                path = cand
            else:
                print(f"  [data] '{path}' has no inputs.npy -> synthetic.")
                return synthetic_healthy_windows(), meta

        if path.suffix == ".npy":
            arr = np.load(path)
            labels_path = path.with_name("labels.npy")
            labels = np.load(labels_path) if labels_path.exists() else None
        else:  # csv / txt raw windows
            arr = np.genfromtxt(path, delimiter=",")
            labels = None
        arr = np.asarray(arr, dtype=np.float32)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [data] WARNING: could not load '{path}' ({exc}) -> synthetic.")
        return synthetic_healthy_windows(), meta

    if arr.ndim == 3:  # (segments, channels, samples) Z24-processed layout
        meta = {"source": "z24", "synthetic": False, "shape": list(arr.shape)}
        if labels is not None:
            labels = np.asarray(labels).ravel()
            keep = np.isin(labels, healthy_labels)
            arr = arr[keep]
            labels = labels[keep]
            meta["healthy_segments"] = int(arr.shape[0])
            if arr.shape[0] == 0:
                print("  [data] no healthy segments (labels not in {0,1,6}) -> synthetic.")
                return synthetic_healthy_windows(), meta
        n_seg, n_ch, n_samp = arr.shape
        ch = [c for c in Z24_SIM_NODES if c < n_ch] or list(range(min(3, n_ch)))
        seg = arr[:, ch, :].reshape(n_seg * len(ch), n_samp)
        windows = []
        for s in seg:
            for i in range(0, n_samp - window_n + 1, window_n):
                windows.append(s[i:i + window_n])
        if not windows:
            return synthetic_healthy_windows(), meta
        meta["windows"] = len(windows)
        return np.stack(windows).astype(np.float32), meta

    if arr.ndim == 2 and arr.shape[1] == window_n:
        meta = {"source": "windows", "synthetic": False, "windows": arr.shape[0]}
        return arr.astype(np.float32), meta

    print(f"  [data] unexpected shape {arr.shape} (need (N,{window_n}) or "
          f"(segments,channels,samples)) -> synthetic.")
    return synthetic_healthy_windows(), meta


# ---------------------------------------------------------------------------
# VAE
# ---------------------------------------------------------------------------
class VAE(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 128, latent_dim: int = 16,
                 dropout: float = 0.1) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.enc = nn.Sequential(
            nn.Linear(input_dim, hidden), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.mu = nn.Linear(hidden, latent_dim)
        self.logvar = nn.Linear(hidden, latent_dim)
        self.dec = nn.Sequential(
            nn.Linear(latent_dim, hidden), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, input_dim),
        )

    def encode(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.enc(x)
        return self.mu(h), self.logvar(h)

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        if self.training:
            std = torch.exp(0.5 * logvar)
            eps = torch.randn_like(std)
            return mu + eps * std
        return mu

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.dec(z), mu, logvar


def train_vae(windows: np.ndarray, epochs: int, input_mode: str, latent_dim: int,
              beta: float, device: torch.device, seed: int = 0) -> tuple[VAE, np.ndarray]:
    """Train the VAE; returns (model, training recon-losses)."""
    torch.manual_seed(seed)
    X = torch.tensor(windows, dtype=torch.float32, device=device)
    n = X.shape[0]
    model = VAE(input_dim=X.shape[1], latent_dim=latent_dim, dropout=0.1).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    batch = 128
    losses: list[float] = []
    model.train()
    for ep in range(epochs):
        perm = torch.randperm(n, device=device)
        ep_recon = 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            xb = X[idx]
            recon, mu, logvar = model(xb)
            recon_mse = torch.mean((recon - xb) ** 2)
            kld = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
            loss = recon_mse + beta * kld
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_recon += float(recon_mse.item()) * len(idx)
        losses.append(ep_recon / n)
    model.eval()
    with torch.no_grad():
        tr = torch.tensor(windows, dtype=torch.float32, device=device)
        recon, _, _ = model(tr)
        recon_losses = ((recon - tr) ** 2).mean(dim=1).cpu().numpy()
    print(f"  [vae] trained input_dim={X.shape[1]} latent={latent_dim} "
          f"epochs={epochs} last_recon_loss={losses[-1]:.5f} (mode={input_mode})")
    return model, recon_losses


def fit_ocsvm(latents: np.ndarray, nu: float = 0.01) -> "object":
    from sklearn.svm import OneClassSVM
    model = OneClassSVM(kernel="rbf", gamma="scale", nu=nu)
    model.fit(latents)
    return model


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train VAE + OCSVM on healthy Z24 windows")
    ap.add_argument("--data", default=None, help="inputs.npy / dir / csv (see docstring)")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--latent-dim", type=int, default=16)
    ap.add_argument("--beta", type=float, default=1e-3, help="KL weight")
    ap.add_argument("--mode", choices=["raw", "features"], default="raw",
                    help="train on raw 1024-samples or on the 7-dim feature vector")
    ap.add_argument("--outdir", default=None, help="default <repo>/models/weights")
    ap.add_argument("--synthetic", action="store_true", help="force synthetic healthy data")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    outdir = Path(args.outdir) if args.outdir else REPO_ROOT / "models" / "weights"
    outdir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  [env] device={device} torch={torch.__version__}")

    windows, meta = load_windows(None if args.synthetic else args.data)
    print(f"  [data] {windows.shape[0]} windows x {windows.shape[1]} "
          f"source={meta['source']} synthetic={meta['synthetic']}")

    # input encoding: raw windows or feature vectors
    if args.mode == "features":
        X = np.stack([feat_mod.extract_features(w, fs=100.0) for w in windows]).astype(np.float32)
    else:
        X = windows.astype(np.float32)
    print(f"  [prep] VAE input {X.shape} (mode={args.mode})")

    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler().fit(X)
    # A near-zero-variance feature (e.g. an always-empty frequency band) yields a
    # scale of ~1e-8, so standardization explodes to ~1e4-1e8 and every score
    # saturates identically for healthy AND damaged windows (measured 0.9743 on
    # the shipped artifact) — the trained ensemble becomes INERT and the demo arc
    # rides entirely on the deterministic spectral floor.  Clamp the denominator
    # so retrains stay discriminative (ROADMAP line 40 / line 117).
    scaler.scale_ = np.maximum(np.asarray(scaler.scale_), 1e-6)
    Xs = scaler.transform(X).astype(np.float32)

    vae, recon_losses = train_vae(Xs, args.epochs, args.mode, args.latent_dim,
                                  args.beta, device, seed=args.seed)

    # latent means for OCSVM
    with torch.no_grad():
        mu, _ = vae.encode(torch.tensor(Xs, dtype=torch.float32, device=device))
        latents = mu.cpu().numpy()
    ocsvm = fit_ocsvm(latents)

    # save artifacts
    torch.save({"state_dict": vae.state_dict(),
                "input_dim": int(X.shape[1]),
                "latent_dim": args.latent_dim,
                "mode": args.mode,
                "dropout": 0.1,
                "beta": args.beta,
                "healthy_recon_loss": float(np.mean(recon_losses)),
                "healthy_recon_std": float(np.std(recon_losses)),
                "threshold_p95": float(np.percentile(recon_losses, 95))},
               outdir / "vae.pt")

    _dump_model(outdir / "ocsvm.pkl", ocsvm)
    _dump_model(outdir / "scaler.pkl", scaler)

    (outdir / "train_meta.json").write_text(json.dumps({
        "artifact": "vae + ocsvm + scaler",
        "mode": args.mode, "epochs": args.epochs, "latent_dim": args.latent_dim,
        "input_dim": int(X.shape[1]), "n_windows": int(windows.shape[0]),
        **{k: v for k, v in meta.items() if not isinstance(v, (list, np.ndarray))},
    }, indent=2), encoding="utf-8")

    print(f"  [save] wrote {outdir/'vae.pt'}, {outdir/'ocsvm.pkl'}, "
          f"{outdir/'scaler.pkl'}, {outdir/'train_meta.json'}")
    print("DONE. Next: backend loads AnomalyDetector() which prefers these artifacts.")
    return 0


def _dump_model(path: Path, model) -> None:
    try:
        import joblib
        joblib.dump(model, path)
    except Exception:
        import pickle
        with open(path, "wb") as fh:
            pickle.dump(model, fh)


if __name__ == "__main__":
    raise SystemExit(main())
