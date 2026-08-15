"""
vibration/train_lstm_ae.py — train an LSTM autoencoder (torch) with MC-dropout
on healthy 1024-sample @100 Hz windows.

Why an LSTM-AE: it captures temporal/sequential dynamics of the vibration signal
that a feed-forward VAE on raw samples flattens away. Inference uses Monte-Carlo
dropout: at score time the model is run N times with dropout enabled, giving a
reconstruction-error DISTRIBUTION -> mean score + uncertainty (dropout spread).

Outputs (default models/weights/):
    lstm_ae.pt       torch checkpoint dict (state_dict + config + threshold)
    lstm_ae_meta.json  human-readable meta

Reconstruction-loss thresholding: the 95th percentile of the healthy training
reconstruction losses is stored as `threshold`; at inference the ratio
recon/ratio-threshold drives the anomaly score.

Data handling: reuses `load_windows` from train_vae_ocsvm.py (Z24 inputs.npy +
labels.npy layout, windows, or synthetic fallback when data is missing).

Usage:
    python models/vibration/train_lstm_ae.py --data data/z24/inputs.npy --epochs 40
    python models/vibration/train_lstm_ae.py --synthetic --epochs 25
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
    print("ERROR: torch is not installed. Cannot train LSTM-AE.", file=sys.stderr)
    sys.exit(1)

try:
    from .train_vae_ocsvm import load_windows
except ImportError:  # bare-script run
    from train_vae_ocsvm import load_windows

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOW_N = 1024


class LSTMAE(nn.Module):
    """Sequence-to-sequence LSTM autoencoder.

    Encoder maps (B,T,1) -> latent z (last hidden). Decoder replays z as input
    for T steps seeded from z, then a linear head emits the reconstruction.
    Dropout inside both LSTMs enables MC-dropout at inference time.
    """

    def __init__(self, seq_len: int = WINDOW_N, hidden: int = 32, latent_dim: int = 16,
                 dropout: float = 0.2) -> None:
        super().__init__()
        self.seq_len = seq_len
        self.hidden = hidden
        self.latent_dim = latent_dim
        self.dropout = dropout
        # NOTE: nn.LSTM(dropout=..) only applies with num_layers > 1, so we use
        # EXPLICIT nn.Dropout layers instead -> MC-dropout works at inference.
        self.enc = nn.LSTM(1, hidden, batch_first=True)
        self.drop_enc = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden, latent_dim)
        self.fc_hidden = nn.Linear(latent_dim, hidden)  # latent -> decoder init state
        self.dec = nn.LSTM(latent_dim, hidden, batch_first=True)
        self.drop_dec = nn.Dropout(dropout)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, 1)
        B, T, _ = x.shape
        _, (h, _c) = self.enc(x)               # h: (1, B, hidden)
        z = self.drop_enc(self.fc(h[-1])).unsqueeze(1)   # (B, 1, latent) + MC-dropout
        dec_in = z.expand(B, T, -1)            # (B, T, latent)
        h0 = self.fc_hidden(z).transpose(0, 1)            # (1, B, hidden)
        c0 = torch.zeros_like(h0)
        out, _ = self.dec(dec_in, (h0, c0))    # (B, T, hidden)
        return self.head(self.drop_dec(out)).squeeze(-1)  # (B, T) + MC-dropout


def mc_reconstruction_losses(model: nn.Module, X: np.ndarray, device: torch.device,
                             n_samples: int = 20, chunk: int = 256) -> np.ndarray:
    """Run the model n_samples times with dropout enabled (MC-dropout).

    Returns array of per-window reconstruction losses, shape (n_samples, n_windows).

    The forward pass is chunked (default 256 windows at a time) so the LSTM
    never runs the whole dataset in one cuDNN call — a full-4050 batch blows
    past ~8 GB GPU memory in the RNN workspace (torch 2.13/cu130 measured).
    """
    model.train()  # dropout active
    xt = torch.tensor(X, dtype=torch.float32, device=device).unsqueeze(-1)
    n = xt.shape[0]
    losses: list[np.ndarray] = []
    with torch.no_grad():
        for _ in range(n_samples):
            col: list[np.ndarray] = []
            for i in range(0, n, chunk):
                xb = xt[i:i + chunk]
                recon = model(xb)
                col.append(((recon - xb.squeeze(-1)) ** 2).mean(dim=1).cpu().numpy())
            losses.append(np.concatenate(col))
    return np.stack(losses)


def train_lstm_ae(X: np.ndarray, epochs: int, hidden: int, latent_dim: int,
                  device: torch.device, seed: int = 0, batch: int = 32) -> tuple[LSTMAE, np.ndarray]:
    torch.manual_seed(seed)
    n = X.shape[0]
    model = LSTMAE(seq_len=X.shape[1], hidden=hidden, latent_dim=latent_dim, dropout=0.2).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    xt = torch.tensor(X, dtype=torch.float32, device=device).unsqueeze(-1)
    model.train()
    for ep in range(epochs):
        perm = torch.randperm(n, device=device)
        ep_loss = 0.0
        for i in range(0, n, batch):
            xb = xt[perm[i:i + batch]]
            recon = model(xb)
            loss = torch.mean((recon - xb.squeeze(-1)) ** 2)
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_loss += float(loss.item()) * xb.shape[0]
        if (ep + 1) % 10 == 0 or ep == 0:
            print(f"  [lstm] epoch {ep + 1}/{epochs} recon_loss={ep_loss / n:.6f}")
    model.eval()
    losses = mc_reconstruction_losses(model, X, n_samples=1, device=device)[0]
    return model, losses


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train LSTM autoencoder on healthy windows")
    ap.add_argument("--data", default=None)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--latent-dim", type=int, default=16)
    ap.add_argument("--mc-samples", type=int, default=20,
                    help="MC-dropout samples used to measure uncertainty after training")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    outdir = Path(args.outdir) if args.outdir else REPO_ROOT / "models" / "weights"
    outdir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  [env] device={device} torch={torch.__version__}")

    windows, meta = load_windows(None if args.synthetic else args.data)
    print(f"  [data] {windows.shape[0]} windows x {windows.shape[1]} "
          f"source={meta['source']} synthetic={meta['synthetic']}")
    X = windows.astype(np.float32)

    model, train_losses = train_lstm_ae(X, args.epochs, args.hidden, args.latent_dim,
                                        device, seed=args.seed)

    # measure healthy recon-loss distribution (mean + dropout spread)
    all_losses = mc_reconstruction_losses(model, X, n_samples=args.mc_samples, device=device)
    per_win_mean = all_losses.mean(axis=0)
    spread = float(np.mean(all_losses.std(axis=0) / (all_losses.mean(axis=0) + 1e-9)))
    threshold = float(np.percentile(per_win_mean, 95))

    torch.save({
        "state_dict": model.state_dict(),
        "seq_len": model.seq_len, "hidden": args.hidden,
        "latent_dim": args.latent_dim, "dropout": model.dropout,
        "threshold": threshold,
        "healthy_mean_loss": float(per_win_mean.mean()),
        "healthy_std_loss": float(per_win_mean.std()),
        "healthy_dropout_cv": spread,
        "mc_samples": args.mc_samples,
    }, outdir / "lstm_ae.pt")
    (outdir / "lstm_ae_meta.json").write_text(json.dumps({
        "artifact": "lstm autoencoder + MC-dropout",
        "epochs": args.epochs, "hidden": args.hidden, "latent_dim": args.latent_dim,
        "threshold_p95_recon_loss": threshold,
        "healthy_mean_loss": float(per_win_mean.mean()),
        "healthy_dropout_cv": spread,
        "n_windows": int(X.shape[0]),
        **{k: v for k, v in meta.items() if not isinstance(v, (list, np.ndarray))},
    }, indent=2), encoding="utf-8")

    print(f"  [save] wrote {outdir/'lstm_ae.pt'} + lstm_ae_meta.json")
    print(f"  [thresh] healthy recon-loss p95={threshold:.6f} "
          f"dropout-CV={spread:.3f} (uncertainty scale)")
    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
