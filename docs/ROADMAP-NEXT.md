# VITISH SHM — Complete Next-Step Roadmap

**Date:** 2026-08-14 (event ~2026-08-20)
**Source:** Consolidated output of 13 code-audit reader agents covering backend, ML models, twin (R3F + Cesium + MapLibre), vault, and root config/scripts.
**Current state:** PS#99 build is COMPLETE and verified — 8 gates / 291 checks exit 0, GREEN->AMBER->RED arc pinned (BHI 87.1 → 77.7 → AMBER 54 → RED 33.6), D1-1..D1-6 + D2-7..D2-12 landed, YC-demo-ready. What remains is a set of real demo-day risks (a verified online-map rendering bug, trained-ML inertness, port-fallback blindness, alert-loss on reload) plus polish, rehearsal, and the post-hackathon product track.

**Spot-verified 2026-08-14** (the top three "now" findings were reproduced in source before publishing):
1. **BridgeMap match-expression bug — CONFIRMED.** `twin/src/map/BridgeMap.tsx:181,200` — both `fill-color`/`circle-color` are 8-element `['match',['get','state'],'RED','#dc2626','AMBER','#d97706','#16a34a','#16a34a']`; MapLibre `Match` requires an odd arg count (the trailing `'#16a34a'` is duplicated), so `addLayer` validation drops both layers → online fleet map renders ZERO dots.
2. **seeded_defect S101 narrative — CONFIRMED.** `describe({'girder_saw_cut':1.0})` returns `f1_drift -12.92%` but `label:'none'`, `active:[]` (iterates only `Z24_SEQUENCE`).
3. **Trained-ML scaler degeneracy — CONFIRMED.** `models/weights/scaler.pkl` feature `f3` has mean 1.8e-9 / scale 1.4e-8 (near-zero variance) → standardized values ~1e4–1e8 → VAE recon error and score saturate to 1.0 for healthy AND damaged; the demo arc is carried by the deterministic spectral floor, not the trained ensemble.

Priority buckets: **[now]** = demo breakers / correctness / missing core pieces — do first. **[before-demo]** = tests, tooling, narrative and robustness polish. **[hackathon-week]** = SIH checklist + rehearsal + submission prep. **[post-hackathon]** = product/startup/hardware.

---

## 1. NOW — demo breakers, correctness bugs, missing core pieces

### Twin / map (visible demo breakers)
- [ ] **[xs]** Fix the BridgeMap maplibre match-expression bug — `D:/SHM_Bridges/twin/src/map/BridgeMap.tsx:180-211`. Both `fill-color` and `circle-color` are `['match',['get','state'],'RED','#dc2626','AMBER','#d97706','#16a34a','#16a34a']` — 8 (even) elements; Match.parse requires odd (labels+outputs+default). Style.addLayer validates by default, hard-errors, and DROPS both layers; the SVG fallback hides this offline, but the online fleet map shows ZERO dots. Delete the duplicated trailing `'#16a34a'` in both expressions. **Verified in source. Single most visible online-demo breaker.**
- [ ] **[s]** Populate the bridge fleet on the live path — `twin/src/store.ts` has no `setBridges`; the fleet is only set by `lib/fixtures.ts:150` (REPLAY path). A backend-first session (WS connects in 3 s) shows an empty map and a '—' header. Add a `setBridges` action; fetch `GET /api/bridges` once WS is live, or call `generateFleet()` in `connect()` before the WS attempt.
- [ ] **[m]** Close the port-fallback discovery gap — backend walks API to 8001+ and WS to 8766+ when busy, but the twin hardcodes `http://127.0.0.1:8000` (4 lib files) and `ws://127.0.0.1:8765`, ignoring `VITISH_API_PORT/VITISH_WS_PORT`; `/api/config` even reports `settings.ws_port`, not the bridge's bound port. On boot fetch `/api/config` (short timeout) and build URLs from returned ports with localhost defaults; make `/api/config` return `ws.bound_port`; read `VITE_WS_URL`/`VITE_API_BASE`; ship `twin/.env.example` (VITE_CESIUM_TOKEN too); wire or delete the dead `/api`+`/ws` proxies in `vite.config.ts`.
- [ ] **[s]** Add a top-level ErrorBoundary — `twin/src/main.tsx` / `App.tsx` / `TwinCanvas.tsx`. One panel/map/Canvas runtime crash currently blanks the whole HUD; a small boundary rendering a labeled fallback card keeps the demo alive.

### Backend robustness (silent failure modes)
- [ ] **[m]** mqtt on_disconnect + subscriber-aware emit fallback — `backend/app/mqtt_client.py`. `emit()`'s bus fallback keys only off publisher connectivity: (a) asymmetric publisher-up/subscriber-down startup drops messages to the bus; (b) `connected.is_set()` lags a real broker death by up to keepalive 60 s while paho buffers → silent BHI/accel loss mid-demo. Register `on_disconnect` to clear `connected` immediately and extend the fallback condition to subscriber state.
- [ ] **[s]** WS bridge drop-oldest — `backend/app/ws_bridge.py:124-126`. `put_nowait` QueueFull fires INSIDE the event loop (call_soon_threadsafe) and is uncaught → slow/backgrounded tab silently misses the BHI band-crossing. Use `if q.full(): q.get_nowait()` then log once when drops occur.
- [ ] **[m]** Alert history on connect — `store.recent_alerts()` exists in both stores but no REST endpoint exposes it and the WS bridge only replays the scenario. Add `GET /api/bridge/{id}/alerts?limit=N` and send the last N alerts in the WS catch-up. Removes the 'empty AlertsPanel after reload mid-arc' hazard.
- [ ] **[m]** Postgres runtime failover — `backend/app/db.py`. If Postgres dies after initial `get_store`, every insert raises, persistence silently stops, and the recorder logs exceptions at up to ~300 msg/s. Add a health-check + reconnect + degrade-to-memory latch on insert failure. Add the missing mqtt healthcheck in `docker-compose.yml`.
- [ ] **[xs]** Deterioration endpoint clean 503 — `backend/app/api.py` catches only ValueError but `deterioration.load_priors()` raises FileNotFoundError when `data/ltbp/analysis/ltbp_summary.json` is missing → unhandled 500. Catch FileNotFoundError and return 503 with 'run scripts/ltbp_analyze.py'.
- [ ] **[s]** Harden `Simulator.run()` against silent thread death — `backend/app/simulator.py`. No per-tick try/except → one player/emit exception kills the daemon thread silently while the stack keeps streaming stale data. Wrap the loop to log-and-continue; confirm fusion.run / ws_bridge have the same guard.
- [ ] **[s]** Small backend guards — `fusion.py` (type-check `samples` is a list of floats — a truthy string extends the ring with garbage), `anomaly.py` (lower-clamp score/uncertainty; push assumed [0,1] but unenforced; document the shared module-global `_baseline` across the 3 nodes), `config.py` (`_env_list_int` ValueError guard; ws_host/api_host not env-overridable while the ports are), `run_all.py` (add `from typing import Optional` — latent NameError under get_type_hints/pydantic).
- [ ] **[s]** `--no-broker` flag + SyntheticPlayer mode validation — `backend/app/simulator.py`. The flag is parsed but never honored (Publisher always created). Implement or remove it; raise ValueError for unknown SyntheticPlayer modes instead of silently treating them as healthy.
- [ ] **[xs]** Wire anomaly baseline reset on data-source change — `run_all.py` never connects `channel_models.set_data_source` to `anomaly.reset_anomaly_baseline()`; a future z24-replay→synthetic switch would carry a stale healthy envelope. Wire it now (cheap).
- [ ] **[xs]** stiffness `_last_seen` staleness — `backend/app/stiffness.py`. `_last_seen` is updated BEFORE the tracking-gate rejection, so out-of-band bursts defeat the staleness flag. Move it after the gate check.

### Contract / honesty / ML core
- [ ] **[s]** Reconcile the live-demo accel row with the frozen contract — `backend/app/live_feed.py` emits `fs:0, samples:[]` while the docstring claims 'contract-shaped dicts'; `contract.py::validate_accel` would REJECT them (bridge/fs/length). Parameterise validate_accel by bridge and document the live-demo row as a deliberately thin rms-only row, or emit full contract-valid rows. At minimum fix the docstring.
- [ ] **[m]** Enforce or retire the contract validator at ingestion — `validate_accel` is smoke-test-only; the runtime pipeline never validates accel/bhi payloads. Insert a lightweight validation at the recorder boundary (bridge-aware, log-and-drop not raise), and add negative tests for wrong bridge/fs/sample-length.
- [ ] **[m]** Strict YOLO-only mode in `CrackDetector.detect()` — `models/cv/inference.py:76-83`. Empty YOLO results fall back to the heuristic and emit FPs on genuinely clean frames — structurally defeats 'clean concrete must not jump / no GREEN flicker' and makes `verify_crack_seg`'s clean leg measure the heuristic. Add `return_yolo_only`/strict mode and use it for both verification and the demo clean-frame policy.
- [ ] **[m]** Fix the trained ML ensemble saturation, or relabel honestly — verified: shipped `scaler.pkl` has a zero-variance feature (band_power_0_5_10, scale~0) → standardized values ~8e4, recon error ~2e7, score saturates to 1.0 for healthy AND damaged; LSTM threshold (3e-7) is 4 orders below live recon errors (~2.4e-3); real-Z24 margin (0.29 vs 0.40 raw) never clears the 0.05 envelope dead-band. The arc is carried 100% by the deterministic spectral floor. Either retrain VAE/OCSVM + LSTM-AE on demo-scale windows with a non-degenerate scaler and gate `trained_deviation(damaged) > 0`, or mark the weights experimental and credit the floor in the demo narrative. Do not leave decorative weights in an ML-claiming demo.
- [ ] **[s]** Verify demo-time CPU with trained weights loaded — `models/weights/` artifacts exist, so every fusion `on_accel` (3x/sec) runs 40 MC-dropout torch passes inline in a producer thread. `test_demo_arc.py` patches `trained_push` to 0.0 so this path is unmeasured. Run the 175 s arc with weights present; if lag appears, gate/offload `trained_push`.
- [ ] **[l]** Wire real CV inference into the demo path (cv_feed bridge) — `crack_seg.pt` is trained but the demo still fires scripted `cmd:cv` events (7-Day-Roadmap Day 3, the biggest remaining 'not yet'). At storyboard t=45/t=85 run one real frame through CrackDetector (YOLO, strict), map detection area/confidence → cv evidence, emit on `control/cmd` cv, keep the scripted value as fallback, re-verify the arc. Converts ledger row 'CV SCRIPTED' → 'CV REAL'.
- [ ] **[s]** Fix `seeded_defect.describe()` — `models/vibration/seeded_defect.py`. Bug A (verified): describe() iterates only Z24_SEQUENCE, so `progress={'girder_saw_cut':1.0}` yields f1 drift -12.92% but label 'none' and active=[] — iterate DEFECTS (Z24 then S101). Bug B (verified): the top-level absolute import lacks the try/except relative fallback every sibling has — `python models/vibration/seeded_defect.py` crashes with ModuleNotFoundError.
- [ ] **[s]** Cache CrackDetector across `?run_seg=1` — `backend/app/api.py` reloads the 92 MB YOLO per request (1-3 s/hit). Hoist a lazy module-level detector or route through `models.load_predictor` with an instance cache. Also note: run_seg currently scores a SYNTHETIC demo_frame, not a real frame — document what the presenter is showing.
- [ ] **[s]** Unify the `u` uncertainty scale — fusion publishes u∈[0.03,0.40] (fraction) while `_DEFAULT_HERO` and regulators return u=3.0 (absolute BHI points); the twin renders ±u as a BHI band, so it collapses when live fusion takes over. Pick one semantic (absolute points) and map fusion's u or drop the 3.0 hardcodes.
- [ ] **[s]** Reconcile replay-vs-manifest honesty labels — when REST is up but WS is down, the twin streams REPLAY fixtures while the manifest poller reports the real data_source; the wsStatus chip and provenance panel can contradict each other. Surface a combined label ('REPLAY fixtures — backend WS offline') or suppress the real-source claim while in replay.
- [ ] **[xs]** Regulator map honesty + perf — `backend/app/regulator_bridges.py`. Seeded bhi floor is 62.0, so no regulator can EVER be RED while the docstring claims a RED spread — widen the formula or fix the docstring. Cache the 49 deterministic healths (api.py calls all_bridges 3x per /api/bridges request).

---

## 2. BEFORE-DEMO — tests, tooling, narrative and robustness polish

### Test infrastructure
- [ ] **[m]** Unified test runner + CI wiring — the 10 backend test files are standalone `python tests/xxx.py` scripts (empty `__init__.py`, no pytest/conftest/CI); `verify_gate.sh` covers 8 but omits `smoke_live_feed_unit.py` (the only deterministic live-feed coverage). Add one command (runner or pytest collection) + `.github/workflows`, and append smoke_live_feed_unit to the gate.
- [ ] **[m]** HTTP route tests for the newer endpoints — `/api/live`, `/api/manifest`, `/api/bridge/{id}/stiffness`, `/seeded-defect`, `/deterioration`, `/condition` (default + run_seg with a fake detector), `/api/config`, asserting status codes, payload shape, and the 'tracker/simulator not running' guards.
- [ ] **[m]** Trained-path regression gate — no test exercises `_score_vae_ocsvm`/`_score_lstm`/`trained_deviation` with the shipped artifacts. Assert healthy ~0 and damaged > 0 (or the relabel), envelope warm-up behavior.
- [ ] **[m]** DemoDriver.run() beat-timing regression test — the 7 storyboard beats are untested (test_demo_arc manually replicates the arc). Drive DemoDriver.run() against a FakePublisher and assert the full beat sequence + that t=75 'rupture' reaches the DamageInjector; add a ramp/impact (tendon-snap) regression test.
- [ ] **[m]** Make global-state test mutations restorable — `test_demo_arc.py` monkeypatches `trained_push` permanently (works only because anomaly.py imports the module, not the function), `test_manifest.py` mutates `set_data_source` with no restore, smoke_test mutates store singletons. Context-manage them so the suite is pytest-safe and order-independent.
- [ ] **[s]** De-flake smoke_test — replace 0.1-0.3 s sleeps with event-based waits; close the two test_ws asyncio loops; parameterise ws_port 8976; clean up test_store's mkdtemp; rewire the 'crack beat sends cv cmd' check to assert on the FakePublisher output (it currently asserts the BEATS definition).
- [ ] **[xs]** test_manifest real-data skip message — the inputs.npy branch silently skips on a fresh clone (991 MB file, only .gitkeep committed). Emit an explicit skip.

### CV/model tooling
- [ ] **[m]** verify_crack_seg strict YOLO-only + per-image severity — `models/cv/verify_crack_seg.py` measures the HEURISTIC wherever YOLO finds nothing (beats_fp trivially True), and `mean_sev` hardcodes 8000 (=0.05*400*400) while SDNET tiles are 256x256 → same detection scores ~2.4x higher severity. Call the model directly and normalize per-image.
- [ ] **[m]** train_yolo resume + default dataset — implement the documented resume-from-local `crack_seg.pt` (offline machine exits 3 today) or fix the docstring; default `--data` to the negatives-balanced `yolo9k_sub2/data.yaml` (bare retrain currently hits the FP-biased all-positives set); make `--cache` a real bool flag.
- [ ] **[m]** Decide the fate of crack_unet.pt — trained (31.5 MB) but nothing loads it; the promised BHI cv signal is unrealized. Either wire CrackUNet as a dense segmenter in inference.py or remove the orphaned weight and mark train_unet experimental. Also remove its dead `if k != 4`, hoist `import cv2`, add a RAM guard for imgsz>256.
- [ ] **[m]** Dataset-prep portability/honesty — `prep_negatives.py` (os.link try/except→copy2, fix `build_split` annotation), `prep_sdnet.py` (stop swallowing a bad --sdnet-path into synthetic exit-0; darken branch polylines; add Uncracked negatives; randomize val split; fix the misleading cv2 comment; checksum), `prep_crackseg9k.py` ({idx}.png / MIN_AREA doc drift, drop dead h/w params).
- [ ] **[m]** models package reconciliation — `models/__init__.load_predictor` is dead public API (nothing calls it; 'single entry point used by the backend' is false) — wire the backend through it with an instance cache or re-document. `models/fusion/bhi.py` BridgeHealthIndex is unused by the backend (fusion math in 3 places) — make it the single call path or label it the reference implementation. `models/fusion/condition.py` `condition_card([])` returns NBI 9 'Excellent' @0.75 confidence from 'segmentation' on ZERO evidence — make it 'no crack evidence detected' with lower confidence (update test_condition.py); NBI band 0 'Failed' is unreachable (NBI_PER_CI=8.0 spans 9..1); validate imaged_frac.
- [ ] **[s]** Surface trained-push magnitude in the UI — expose the floor vs trained contribution so the demo transparently credits whichever detector carries the arc.

### Demo content & narrative
- [ ] **[m]** Generate the per-scenario confusion matrix + CV metric sheet — Mission criterion #3, Storyboard beat 2:00-4:00, and Q&A Q3/Q7 require it; none exists. One-command script emitting the per-scenario matrix + threshold-vs-FPR curve + crack_seg mAP@0.5/precision/recall; write into Metrics.md + pitch folder.
- [ ] **[s]** Curate demo crack frames — create `data/cv/demo-frames/` (verified missing) with 3-6 val-split frames for the cv_feed bridge.
- [ ] **[m]** Create `scripts/verify_demo_arc.py` — Build-Log D1-1 names it 'next' but it does not exist (verified). Re-pin the arc values against real data (87.1 / 67.5 / 33.6).
- [ ] **[s]** Mirror D2-11 Markov projection offline — the offline replay never calls setDeterioration, so DeteriorationPanel shows the permanent 'backend unreachable' state offline. Emit a small fixture projection or degrade the label.
- [ ] **[s]** Reconcile offline vs online f1 narrative + hero location — offline replay says 3.80→3.52, live FEM says 3.80→~3.24 for the same scenario; hero bridge sits in Davenport IA (41.59,-90.5) on the fleet map but Nottwil CH (47.135,8.165) in the Cesium view. Mirror the backend mapping and either move the hero to Nottwil or label the discrepancy.
- [ ] **[s]** Align Q&A Q4 + storyboard beat honesty — Q4 overclaims 'official .mat under KU Leuven license' (registration not done); the beat 'show VAE/OCSVM confusion matrix' collides with measured non-separability; Four-Components still quotes 'BHI 87→12' vs verified RED 33.6. Register or soften; produce the honest matrix or reword the beat.
- [ ] **[m]** Refresh stale vault notes in one pass — Home.md 'Next build: real crack_seg.pt' (now trained); Realistic-Digital-Twin §4 blockers #1/#2 (resolved) still shown open; Tech-Stack 'No CesiumJS' vs D2-7; Digital-Twin 'Morbi-style suspension bridge' vs Z24 box girder; Company-Project §15 CV row 'SCRIPTED / no crack_seg.pt' (weights exist). Prevents a presenter quoting a resolved/contradicted claim.
- [ ] **[xs]** Quarantine `_report_fulltext.txt` — tracked at root, no superseded warning, still carries audit-corrected-away overclaims (4 cables, 18 days, 60 m, 690 citations, mAP 0.65, USD 5-15/mo, TLS, LoRaWAN, Jetson 30 FPS). Add a SUPERSEDED banner pointing to the master plan.

### Twin polish
- [ ] **[xs]** Log once on first poller failure — all four pollers/WS silently swallow errors; add a single console.warn breadcrumb (then silence) so a broken backend is debuggable without spamming.
- [ ] **[xs]** Guard the stiffness poller against overlap + whitelist manifest dataSource — an in-flight flag for the 1.5 s two-fetch poll; validate dataSource against z24-replay|synthetic|live-demo|offline instead of a bare type cast.
- [ ] **[s]** Derive map colors from theme.ts — BridgeMap re-hardcodes the three hex values in the match paint arrays AND the SVG legend dots; build both from STATE_COLORS so the palette can't desync; remove dead ACCENT export or use it for the selection ring.
- [ ] **[s]** Centralize contract literals — 'window 10.24 s · fs 100 Hz' hardcoded in 3 files; sub-index weights as display strings in HealthPanel vs BHI_W; f1 baseline 3.8 duplicated across store/fixtures/stiffness/panels/collapse; computeBhi omits age_factor/traffic_factor. Derive from the store's exported constants (mirror factors with default 1.0).
- [ ] **[s]** ProvenancePanel guards + DeteriorationPanel extras — guard `manifest.channels ?? []`; prefer backend dataSourceLabel over the local SOURCE_META copy; render nextInspectionRule and rating (fetched but never displayed).
- [ ] **[xs]** Cesium attribution compliance — `.cesium-viewer-bottom` is display:none; restore a minimal visible credit for a public YC demo.
- [ ] **[s]** Twin HTML/theme hygiene — remove the dark #0b0f14/color-scheme:dark inline style (dark flash + dark controls) and add a favicon; add an explicit `.env` line to twin/.gitignore (the Cesium token is currently protected only by the repo-root rule); keep at least the right telemetry panels at <=760px; move hardcoded hex colors to CSS variables.
- [ ] **[s]** Twin scene hygiene — CameraRig per-frame Vector3 allocation + target-lerp fighting user drag; MorbiBridge web twist/pier sway snapping on recovery (gate on cascade) + the 35% saturation constant duplicated with the SceneOverlay legend; collapse.ts dead cableBroken/cableDrop/BRIDGE.zDeck + deckY dedup + droop comment; SensorMarkers redundant tmpC.clone() + empty-canvas deselect. Add `models/cv/__init__.py` and `models/fusion/__init__.py`.
- [ ] **[l]** Twin unit tests (Vitest) — zero tests anywhere in twin/. Cover computeBhi/stateFor (the BHI arc is the core claim), ws.ts state machine + ingest guards, fft.ts spectrum, fixtures determinism, collapse.ts pure math, and a maplibre style-spec layer-validation test (would have caught the BridgeMap bug). Add a `test` script + lint.
- [ ] **[m]** Live scripts reproducibility + e2e PASS criterion — e2e passes while zero bytes flow (ok=enabled only proves the thread lives); require received>0 (or published>0). smoke_live_feed: WINDOW env override, --no-network fast path, local-broker option so it never depends on test.mosquitto.org.
- [ ] **[s]** live_feed rate limiting + WS-surface decision — add a per-topic rate cap; ws_bridge never subscribes bridge/live-demo/# (docstring overpromises) — subscribe+forward or fix the docstring; decide live-demo telemetry persistence (deliberately dropped today).
- [ ] **[s]** Backend hygiene batch — surface/drop dead contract constants (ANOMALY_LATENCY_S, TOPIC_LORA, Z24_SCENARIOS/LABELS); fix stale docstrings (live_feed 'contract-shaped', demo_predictor '~51 s warm-up' — actually ~15 s); note CORS `*`+credentials is local-only-safe; move the dev db_dsn credential to env-only; `_live_hero_state` → `.get()` with DEFAULT_HERO fallback.

---

## 3. HACKATHON-WEEK — SIH checklist + rehearsal + submission prep

- [ ] **[s]** Register with KU Leuven for the official Z24 .mat package (Data-Access-Checklist #1, Risk #8, Q&A Q4) — highest demo-day honesty risk; complete registration, keep the confirmation email, align the Q4 wording.
- [ ] **[m]** Close the Pre-Hackathon-Checklist logistics — 6-member roster incl >=1 female + unique team name; email organizers for the exact scorecard + demo format; one-paragraph idea + 10-slide PPT; Z24 one-command mirror check; pre-stage venv/Docker offline; venue-class hardware practice + 2 backup takes; 6-min pitch draft with death-toll locked; Q&A bank with 2 owners.
- [ ] **[m]** Network-off USB + cloud verify — copy all datasets/weights/assets (crack_seg.pt, lstm_ae.pt, vae.pt, ocsvm.pkl, scaler.pkl) and verify the whole stack runs with network OFF, including the SVG-map fallback and offline replay. Confirm the live public-MQTT feed degrades to 'waiting' non-fatally.
- [ ] **[m]** Full 6-min dress rehearsal at H34 — timed/recorded, timer+projector+audio, walking the approved Storyboard, with fail-injection (broker down, no internet, 8000/8765 occupied, backgrounded tab) against the now-phase hardening. Record 2 backup takes.
- [ ] **[m]** 3-tier demo assets (live → video → screenshots) staged on 2 laptops + 1 phone.
- [ ] **[s]** Write RUNBOOK.md at repo root — cold-start command, docker kill-and-recover drill, demo assets list, network-off start order, 'kill the stale 8000/8765 instance' diagnostic. (File does not exist.)
- [ ] **[xs]** Create the git tags — `arc-verified-2026-08-13` and `release-2026-08-13` (none exist); freeze the verified state; re-run the arc gate after every subsequent change.
- [ ] **[s]** Final gate run — extended verify_gate.sh (incl. smoke_live_feed_unit) + demo-arc regression on the frozen state; update the stale test-count references (memory says '83/83 + 19/19'; suite now yields 85 + 239 = 324).
- [ ] **[m]** Q&A bank dry-run with corrected facts only — 170-collapse vs MoRTH-42 landmine, cost table (~$980 pilot / ~$260/yr / $25-30/mo), latency split stated deliberately, and the 'never quote 4 cables / 18 days / EU mandate / 60 m / 690 citations / mAP 0.65' guardrails.
- [ ] **[xs]** LIVE badge decision (ESP32 smoke gate) — no firmware/board exists; default to NO LIVE badge and narrate ESP32 as the H8-gated stretch; document in Key-Decisions.
- [ ] **[s]** Submission prep — submit 30 min early, walk-in bag check, 2 backup takes + USB/cloud ready, confirm venue GPU/environment (Risk #5), rehearse dataset-provenance answers (Q2/Q8/Q10/Q11).

---

## 4. POST-HACKATHON — product/startup, real hardware, scaling, publishing

- [ ] **[l]** Build the real ESP32-S3 edge node (H8-gated) — firmware/ does not exist; WiFi + MQTT on bridge/{id}/accel + rolling RMS flag, bench-tested. Only if a board is in hand; otherwise document as future work.
- [ ] **[l]** RUL / predictive-maintenance projection + realistic traffic/WIM load model — age/traffic factors are 1.0 placeholders, load is still scripted; add remaining-life projection on the verified BHI trend (band in HealthPanel) and a real load model.
- [ ] **[xl]** Realism roadmap items #11 / #13 / #14 — event-triggered capture + replay; component asset registry (backend model + frontend raycast cards); crack-severity → image-to-3D photo registration.
- [ ] **[xl]** Complete the trained ML story — real retrain (non-degenerate scaler, demo-scale thresholds), trained-path gate, environmental de-confounding study, per-structure-type retraining, strain + acoustic sensors.
- [ ] **[l]** CV scale-up — integrate or retire crack_unet.pt; dacl10k 19-class fine-tune as a talking point; SAM2 refinement pass; decide MiniRocket+Ridge's fate.
- [ ] **[l]** BHI calibration study vs IBMS CRN 0-6 — calibrate weights/bands against MoRTH ratings on pilot data (named pilot deliverable; IBMS survey deadline 30 Sep 2026 is the procurement hook).
- [ ] **[xl]** Pilot deployment + startup track — partner PWD bridge pilot + railway overbridge + one export (2-3 LOIs); incorporation + legal/IP; named CEO/BD owning the pilot funnel; bottom-up India TAM (~1.7 lakh NH bridges); data-licensing plan (production data commissioned, not dacl10k/SDNET2018); competitor pricing depth; federated learning moat; IBMS integration path; refresh the $500k pre-seed ask.
- [ ] **[m]** Production-grade data plane + CI — auth/TLS + healthchecked broker (drop anonymous localhost + public test.mosquitto.org dependency); env-only Postgres credential; GitHub Actions running the unified backend gate + twin typecheck/tests; pin numpy>=2.0 (np.trapezoid); reconsider the 1600 KB Cesium bundle vs code-splitting.
- [ ] **[m]** Publish + open-source the reusable pieces — Z24 mirroring tooling, CrackSeg9k/SDNET conversion pipelines, Markov-priors workflow (scripts/ltbp_analyze.py); write up the honest-findings methodology (deterministic floor + bounded trained push, per-scenario evaluation).

---

## Appendix — known technical debt / hygiene (every tiny leftover)

**Dead code (remove or wire):**
- `backend/app/db.py:32` — `_clamp` defined, never called.
- `backend/app/mqtt_client.py` — `Subscriber.add_handler` has no callers (routing uses default_handler).
- `backend/app/events.py` — the `source` parameter on `EventBus.publish` is never forwarded to callbacks (callers believe it tags messages); either forward `(source, topic, payload)` or drop it.
- `models/vibration/heuristic.py` — `_base_rms`/`_base_rms_std` initialized 0.0, never written → `rms_trigger_sigma=3.0` is permanently dead; `max(self._base_rms, median)` redundant.
- `models/vibration/minirocket_fallback.py` — implemented but only imported by models/smoke_test.py; never wired into the backend (decide: integrate or mark reference-only).
- `models/__init__.py` — `load_predictor` factory is unused by the backend; `__version__='0.1.0'` hardcoded (duplicates app/__init__).
- `models/fusion/bhi.py` — BridgeHealthIndex unused by the backend (fusion math in 3 places); `self.history` unbounded; no w-dict key validation.
- `models/vibration/infer.py` — `has_trained_models` property never called; `blend_heuristic` param stored never read; `add_healthy()`/`reset_baseline()` documented but unused in the live path; `print()` for load warnings + '[infer] mode:' banner on backend import (should be logging); undocumented MC-variational scoring under `model.train()` (systematic score inflation vs eval-calibrated threshold).
- `models/vibration/train_lstm_ae.py` — `train_lstm_ae()` returns `train_losses` that `main()` never reads.
- `models/cv/prep_crackseg9k.py` — `row_to_yolo(r,h,w)` ignores h,w (uses mask.shape); docstring claims {idx}.png but only .jpg written; docstring says '<40 px' noise drop, code uses MIN_AREA=15.
- `models/cv/train_unet.py` — `k = rng.choice([1,2,3])` then `if k != 4` (always True); `import cv2` inside `_rasterize` per call.
- `twin/src/lib/fft.ts` — `dominantHz()` exported, imported nowhere; no power-of-two guard; scaling DC at 2/n (cosmetic).
- `twin/src/lib/theme.ts` — `ACCENT` exported, imported nowhere; the 'single source of truth' comment is false (BridgeMap re-hardcodes the palette).
- `twin/src/lib/ws.ts` — write-only `timedOut` variable; `startReplay()`'s returned cleanup ignored; dead branch where `computeBhi` fallback is unreachable behind `typeof p.bhi === 'number'`; the frame branch parses image_b64 then discards it (no camera display exists); 5 s fixed retry has no backoff.
- `twin/src/scene/collapse.ts` — `cableBroken` (always false) and `cableDrop` dead fields; `BRIDGE.zDeck=2.3` never referenced (sensor z-offset hardcoded as 2.3 in store.ts); `BRIDGE.deckY` duplicates `store.ts BRIDGE_DECK_Y`; droop-bell comment vs actual ~0.34 m at piers.
- `backend/app/run_all.py` — `_shutdown` calls `stiffness_mod.get_tracker()` twice.
- `D:/SHM_Bridges/parse.py` — committed dead script (reads z24.json, an OpenAlex error response → silent no-op, exit 0).
- `requirements.txt` — `redis>=5.0` declared but no Redis service/import anywhere (the 'Redis pub/sub' plan was never implemented).
- `backend/app/simulator.py` — `--no-broker` flag parsed, never honored.

**Stray files / dumps (cleanup):**
- `.verify/` (untracked scratch): research dumps (bing_*.html, rf*.html, sut.html, mendeley_cfd.html), zero-byte files (arxiv.xml, hv2.json, hv_search.json, hv_crackseg9k.json), logs (geo_run2.log, geo_verify.log), screenshots (geo_view.png, twin_d2_11.*), arc_calib.py, critique_dump/findings_summary/roadmap_dump.txt. Archive what's needed for the research trail, prune the rest.
- Root research dumps (asce.json, dv.json, g2.json, giorgi.json, lstm.json, sdnet.json, z24.json, z24b/c/d.json) — all gitignored and referenced by nothing. `dv.json` is empty (0 B); `z24.json` holds an OpenAlex ERROR response. Keep as research trail or delete.
- `.gitignore:50` ignores `*.json` globally — a future root-level JSON config would be silently excluded unless negated.
- `models/weights/smoke_empty` and `smoke_no_weights.pt` are intentionally absent to force fallback paths — uncommented; a reader/operator may think files are missing. Add a comment.

**Doc/code drift (fix or annotate):**
- `contract.py` dead constants: `TOPIC_LORA`, `ANOMALY_LATENCY_S`, `Z24_SCENARIOS/Z24_HEALTHY_LABELS/Z24_DAMAGE_LABELS` (no consumers); `AGE_FACTOR/TRAFFIC_FACTOR` always 1.0 (documented placeholder).
- `live_feed.py` docstring 'the WS bridge / API can surface the rest' — WS bridge never subscribes to live-demo topics; 'contract-shaped dicts' false (fs=0, samples=[]).
- `demo_predictor.py` warm-up comment '~51 s' stale (sliding window advances 1 s/call → ~15 s).
- `train_yolo.py` 'resume from local' claim unimplemented.
- `verify_crack_seg.py` hardcoded `Path('no_such_weights.pt')` brittle; all-clean/zero-detect images silently keep max_conf/max_sev at 0.
- `regulator_bridges.py` docstring RED-spread claim vs 62.0 floor.
- `deterioration.py` — `next_inspection_rule` string hardcodes '4'/'25%' instead of interpolating args; `condition_from_bhi` has no type guard before `np.isnan`; `PRIORS_LABEL` hardcodes '44 FHWA InfoBridge pilot bridges' with no consistency check; `transition_matrix` silently swallows malformed 'i->j' keys.
- `README.md` `docker compose up -d --build` — no service has a `build:` section (no-op); live public-MQTT feed is the one external-network dependency.
- `docker-compose.yml` — POSTGRES_PASSWORD hardcoded 'vitish'; mqtt service has no healthcheck; mosquitto allow_anonymous (documented local-only).
- `index.html` — no favicon (browser 404s /favicon.ico).
- Vault staleness — Four-Components 'BHI 87→12' vs RED 33.6; Storyboard beat vs missing confusion matrix; QandA-Prep Q4 overclaim; Company-Project §15 CV/ESP32/RUL ledger rows.
- Memory/test-count drift — 'smoke 83/83 + 19/19' is stale; suite now 85 + 239 = 324.
- `features.py` — `np.trapezoid` requires numpy>=2.0 (portability footgun for numpy 1.x).
- `stiffness.py` — `fem_modes` computes the eigen-decomposition twice (eigvals + eig on the same reduced system); midspan_deflection hardcodes a 350 kN load (documented demo constant).
- CORS `allow_origins=['*']` + `allow_credentials=True` in api.py (local-only safe; echo-origin behavior).
- The `u` fraction-vs-points semantic mismatch (see now-phase) and the shared anomaly `_baseline` across nodes (see now-phase).

**Untested paths to keep on the radar (not blocking the demo):**
- PostgresStore SQL path (requires Docker) — MemoryStore-only coverage today.
- LiveFeed real MQTT connect path (public broker protocol drift) — unit test is network-free by design.
- `run_all` startup/shutdown flag combinations (--demo/--speed/--live/--scenario edges).
- Z24Player/Z24RupturePlayer real-replay indexing (only runs when data/z24 exists).
- live-demo telemetry persistence is deliberately dropped by `attach_recorder` — confirm the product intent (UI should never expect live temp/humidity history).

---

**Suggested execution order:** Now-phase items 1-4 (twin demo breakers) → 5-13 (backend robustness) → 14-21 (ML/CV/honesty core, incl. the real-CV cv_feed bridge) → before-demo tests first (they gate everything else) → demo content/narrative → rehearsal block in hackathon-week. After the event, open the post-hackathon track. Re-run `scripts/verify_gate.sh` and the demo-arc regression after every change — the arc must hold as the guardrail.