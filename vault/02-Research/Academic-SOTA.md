---
tags: [research, sota, ml, vitish-2026, shm]
created: 2026-08-13
---

# Academic SOTA — cite, don't build

## The model-family story (say it in one breath)

"LSTM-AE on edge for latency; **Transformer foundation model in cloud for accuracy**" — mirrors Benfenati's own deployment story ([[Vibration-Model]]).

## The papers

| Paper | arXiv | Claim | Use in demo/Q&A |
|---|---|---|---|
| **Benfenati et al. 2025** (IEEE TSUSC) | arXiv:2404.02944 | Self-supervised **masked-autoencoder** Transformer foundation model — **99.9% AD accuracy in 15 windows** vs PCA 95.03% in 120 | The cloud-layer SOTA frame |
| **CiF benchmark** | arXiv:2605.18413 | Zero-shot foundation models plateau on real infrastructure (**~25% mAP**) | Defense for "why fine-tune, not just SAM2?" ([[CV-Model]]) |
| **SECrackSeg** (Sensors 2025) | — | **SAM2 + S-Adapter** crack segmentation refinement | Optional hero-mask pass |
| **Neumann et al.** | arXiv:2409.17735 | Temperature confounding in modal features | The de-confounding citation ([[Vibration-Model]]) |
| **Sajedi & Liang** | arXiv:2004.05151 | LSTM-AE with **MC-dropout** (uncertainty) | Edge baseline + uncertainty band ([[BHI-Formula]]) |
| **SHM-Agents** | arXiv:2605.12916 | LLM agents → plain-language maintenance advice | The copilot pane ([[Digital-Twin]]) |
| **SPECTRA** | arXiv:2607.03446 | — | Related-work slide |
| **VAE+OCSVM on Z24** (Scientific Reports 2025) | — | PR 0.996 / recall 0.999 | Our primary vibration model ([[Vibration-Model]]) |

## Survey / domain-adaptation / federated citations

- Zhang & Liang domain adaptation (arXiv:2512.18780) · Yang et al. deep generative SHM (arXiv:2507.15026) · Torzoni et al. (arXiv:2506.14453) · Phan et al. (arXiv:2411.04475).
- **Federated learning** future-work: Feng et al. (arXiv:2606.03084) — "fine-tune across bridges without sharing raw sensor data".

Related: [[Vibration-Model]] · [[CV-Model]] · [[QandA-Prep]]
