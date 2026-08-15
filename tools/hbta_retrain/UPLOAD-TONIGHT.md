# HBTA upload → server download — tonight's runbook

Do in this order. Every step is idempotent — if a step drops, just re-run it.

## Step 1 · This machine (Windows): push the tar to Hugging Face

Open PowerShell. Three commands:

```powershell
# (a) remove the native module that was segfaulting (hf_xet 1.4.3 under Python 3.14)
pip uninstall -y hf_xet

# (b) set the token for this shell only
$env:HF_TOKEN = "hf_..."      # write-scoped token from https://huggingface.co/settings/tokens

# (c) upload (Xet off, HF cache on C:). Repo already exists (private) — this overwrites/continues.
cd D:\SHM_Bridges
$env:HF_HOME = "C:\Users\dev25\.cache\huggingface"
$env:HF_HUB_DISABLE_XET = "1"
python tools/hbta_retrain/upload_hf.py Dev2506/hbta-retrain --private
```

Expected output ends with:

```
  [hf] done: https://huggingface.co/Dev2506/hbta-retrain/resolve/main/hbta_retrain_2026-08-15.tar.gz
```

If the upload drops mid-way (network), just re-run (c) — uploads are idempotent (overwrite).
If it segfaults again, `pip uninstall -y hf_xet` first was not enough → fallback at the bottom.

## Step 2 · The internal server (Brev.dev): download + extract + verify

```bash
export HF_TOKEN='hf_...'                       # same token
cd ~
wget -q --show-progress --header="Authorization: Bearer $HF_TOKEN" \
     https://huggingface.co/Dev2506/hbta-retrain/resolve/main/hbta_retrain_2026-08-15.tar.gz
echo "1dad4e3da5f288e73f32c596f94418e58dcc955e9b8b95adeeed8e6f9b10781d  hbta_retrain_2026-08-15.tar.gz" | sha256sum -c -
tar xzf hbta_retrain_2026-08-15.tar.gz
cd hbta-retrain
```

`sha256sum -c -` must print **OK** before extracting. If it doesn't, delete and re-download.

## Step 3 · Train (two lanes, one command)

```bash
conda activate fignn_env          # torch + CUDA
bash run_retrain.sh               # ACCEL lane → expected CHECK (honest), STRAIN lane → measured numbers
```

## Step 4 · Clean up

- **Revoke the token**: https://huggingface.co/settings/tokens → delete the write token
  you used. It was pasted into a chat transcript, so treat it as public the moment
  the download is done. Do this before the server finishes training — the download
  only needs it once.
- (Optional) once you've downloaded, the private repo can stay for reference.

---

## Fallback if the Python upload still crashes

The raw LFS endpoint (no huggingface_hub, no Xet) — Python `requests` PUT:

```python
# one-off: python -c "..."  (run from D:\SHM_Bridges)
import requests, os
TOKEN = os.environ["HF_TOKEN"]
url = "https://huggingface.co/api/models/Dev2506/hbta-retrain/lfs-resolve/HEAD/hbta_retrain_2026-08-15.tar.gz"
with open("hbta_retrain_2026-08-15.tar.gz","rb") as f:
    r = requests.put(url, data=f, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=7200)
print(r.status_code, r.text[:200])
```

If this 403s, the LFS header dance is manual — say so in the chat and I'll write the
full `curl` sequence (git upload-pack → preupload → PUT) for you.
