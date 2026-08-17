# VITISH-2026 Comprehensive Project Analysis

**Date:** 2026-08-16 · **Scope:** full project — build, data & training, hardware · **Commit reviewed:** `303f776` (posthack) + `c84fe35` (geo) on `main` · **Addendum (2026-08-16):** §117 follow-up — HBTA detection improvement levers + verified acoustic-emission data catalog (Category 8) · **Addendum (2026-08-17):** NOW items 1–6 landed + TEST-F3 (see §7.6) and the **entire 30-day product-surface block is DONE**: items 7 (S1 RUL decision surface), 8 (NEW-02 real site temperature), 10 (IRC-118/IBMS condition-report generator), 11 (edge bench proof — documented sim proof, `docs/EDGE-BENCH-PROOF.md`, no board flashed), 12 (twin+backend e2e stack smoke), 13 (Postgres CI job + failover latch), 14 (multi-bridge registry — env-driven second synthetic bridge), 15 (honesty-label regression gate — LIVE-badge gating + simulated/fallback labels always present) — gate count now **18**, all passing; the suite grew to **24 files** backend + 71 twin vitest; entering the 90-day block, **item 16 DONE (2026-08-17)** — dated BD workstream `vault/08-Startup/BD-Workstream.md` (owners + acceptance + bottom-up India TAM + CRN↔BHI protocol); CEO/BD slot remains the single OPEN hard dependency (2026-08-31) · **Addendum (2026-08-18):** the §2.2 crit list **BUG-01..06 all FIXED** (`dbd929b` + `a7240e4` — emit fallback on failed publish, whole-window malformed-accel drop in fusion/stiffness, non-latching twin port re-discovery + port-range walk, hero `validate_accel` strictness, replay auto-advance mirroring t=75; 39-check `test_bugfix_regression.py` + twin `config.test.ts`/`fixtures.test.ts`); suite now **24 backend files (arc 19/19, 87.1/67.5/33.6)** + **9 twin files / 76 tests**, merge gate **19/19** · **Addendum (2026-08-18): item 17 decision gate = NO-FLIP** — full-Z24 coordinated-diagonal candidate measured through the real gate FAILs 3 assertions (label{0} 0.141, damaged 0.000, demo-fire still 0; label{1} confound removed only at that price) → shipped weights stay, arc untouched, goal left OPEN with `docs/ITEM17-RETRAIN.md` (root cause: `peak_freq` is not a first-mode estimate on real Z24 — p50s 0.4–15 Hz — so the temperature diagonal never formed for real data; next experiment = band-limited multi-window f1 tracking + wider cold grid)

## How this was produced

A 22-agent analysis workflow ran over the whole repository (all lenses plus independent adversarial verification plus a synthesis critic). It produced **86 findings across 10 lenses**, **5 adversarial verdicts** (4 confirmed, 1 downgraded), and a critic pass (top opportunities, risks, weak recommendations, gaps, 90-day sequence). Every finding cites `file:line` evidence that was re-checked against source; the adversarial verifier independently reproduced the top bugs and security findings before they were confirmed. Numbers are reported as measured — nothing was strengthened beyond what the code or a repro supports.

**The one-line result:** the build is real, honest, and demo-arc-pinned (all 18 gates pass, the floor carries BHI 87.1→67.5→33.6), and the single most damaging defect in the repo was a **false claim that outlived the retrain**: `scripts/metrics_sheet.py` and `verify_demo_arc.py` printed that the trained ensemble is *"inert — degenerate shipped scaler"* even though the 2026-08-15 retrain made it ACTIVE and gates 10/16 assert separation. **Fixed (CODE-F1, 2026-08-17)** — the stale prose is swept from code + committed docs, and re-running the metrics generator now emits the measured split.

---

## Category 1 · Project Analysis & Strategic Opportunities

### 1.1 S1 — Ship the RUL / "years to NBI≤4" decision surface *(High · P1 · 1–2 days)*
**The gap:** the regulator's question is *"which bridge first, and when"*, not a prettier health score — and every piece already exists. `deterioration.py:150-158` computes the first year P(NBI≤4)≥25%; `project()` returns a year-by-year fan with p10/p90; `/api/bridge/{id}/deterioration` already serves it and the twin polls it every 5s.
**Do:** add a "projected years to NBI≤4" band (expected + p10/p90 + next-inspection year) to the HealthPanel, and a next-inspection/priority sort to the fleet map. Label honestly: *"Markov projection, LTBP fleet prior — not certified RUL."* This is the most procurement-relevant surface the repo can ship without a partner.
**Status ✅ DONE 2026-08-17:** band in the HealthPanel + `/api/fleet/priority` ranking + `FleetPriorityPanel` overlay on the map + mandatory honesty label on every render + never-quote row added (see §7.6 item 7).

### 1.2 S2 — Make the IBMS CRN 0–6 calibration the strategic lock-in *(High · P1 · 2–4 weeks)*
**The gap:** the pitch positions VITISH as "the calibration layer of the national IBMS," but there is no CRN↔BHI path in code. IRICEN/IBMS uses the numeric CRN 0–6 scale, and the 30 Sep 2026 MoRTH survey is the dated procurement hook.
**Do:** build a calibration module mapping BHI sub-indices to CRN 0–6 with labeled confidence + provenance (mirroring the existing, honestly-labeled BHI→NBI mapping at `deterioration.py:100-110`), expose `/api/bridge/{id}/crn`, and make the CRN↔BHI regression the named pilot deliverable (#119). A regulator sees IBMS condition every second instead of every two years.

### 1.3 S3 — Turn the measured thermal de-confounding into a product surface *(Medium · P1)*
**The gap:** gate 16 already *proves* the deterministic floor stays flat across a full-year seasonal f1 sweep (max 0.037, GREEN) yet fires on the seeded rupture (0.72/0.94). This is a defensible differentiator competitors cannot even demonstrate — but it lives in tests, not the product.
**Do:** surface a "thermal de-confounding" panel on the twin (residual vs ±7% band, gate-16 evidence link), and build the temperature covariate (feature index 6 already exists, currently passed as 0.0) into the trained envelope to kill the label-{6} season confounding. This converts a documented honest limit into a moat.

### 1.4 S4 — Make the fleet-prior learning loop code, not slogan *(Medium · P2)*
**The gap:** moat #2 claims a data flywheel, but nothing appends observed transitions back into the LTBP Markov priors (`regulator_bridges.py:100-123` is seeded and immutable).
**Do:** add a "fleet prior update" path — export per-bridge condition history from the store, convert to transitions, merge into `ltbp_summary.json` with `empirical:true` provenance. Label the fleet map "prior-driven prioritization view" (1 live + 49 illustrative) to stay honest.

### 1.5 S5 — Productize "onboard a new bridge in a day" *(High · P1 · 4–8 weeks)*
**The gap:** a second bridge today means code edits — `config.py:85-86` pins `bridge_id='z24'`/`nodes=[6,7,8]`, `contract.py:22` freezes BRIDGE_ID, `stiffness.py:40` fixes `_REF_NODE=7`, and the FEM hardcodes `L_TOTAL=58, L_MAIN=30, SUPPORTS=(0,14,44,58), RHO_A`. The "$980 pilot, deploy in a day" cost-to-serve moat does not exist yet.
**Do:** bridge-config-as-data — a registry (span arrangement, node layout, girder type → auto-calibrated EI_CAL, auto-learned f1 baseline) + `POST /api/bridge/{id}/onboard`. The FEM is already element-parametric, so the physics refactor is contained. This is the single biggest demo→product step.

### 1.6 S6 — Reframe from "monitoring" to "risk-prioritized inspection" against 30 Sep 2026 *(Medium · P2)*
**The gap:** the demand signal is "pick the right bridges to inspect first with a fixed budget" (Gambhira aftermath: 1,800 inspected → 20 closed / 113 partial). `next_inspection()` is literally a prioritization rule; the demo leads with a lone health score instead.
**Do:** rank `/api/bridges` by `next_inspection_year`/`p_poor` and surface an "inspection schedule" view. Re-word the pitch headline around risk-prioritized inspection for the IBMS deadline.

### 1.7 S7 — Publish the honest-findings methodology + three reusable pipelines *(Low · P3)*
The publishable nucleus already exists (Z24 mirroring, CrackSeg9k/SDNET conversion, `ltbp_analyze.py`). **Fix the stale "inert" prose first** (see Issues, CODE-F1 — a P1 honesty bug that blocks this whole category). Then ship one methodology write-up + per-tool packaging. Keep dacl10k (CC BY-NC) and SDNET2018 (registration) out of public artifacts.

### 1.8 S8 — De-risk the 4-in-1 IoT leg: fix the bridge-id mismatch + bench proof *(High · P2)*
**The bug:** firmware `esp01/config.h` sets `BRIDGE_ID='esp01-1'` but `edge_node.py:16` hardcodes `EDGE_BRIDGE='esp32-1'` — a stock-flashed ESP-01S reaches the generic `bridge/+/#` subscriber but is **silently ignored** by the edge monitor and recorder. The 4-in-1 wedge and the $980 pilot kit rest on this leg, which has never streamed a packet (decision #11 = NO LIVE badge).
**Do:** align the ids (or subscribe to the configured edge id), run `scripts/edge_sim.py` (byte-identical host sim) through the real monitor/recorder/API and pin it as a gate, and align the pilot-kit SKU/price with what is actually bench-proven. Keep NO-LIVE-badge until a real packet is measured.

---

## Category 2 · Issues & Required Fixes

### 2.1 Security (highest severity first)

| ID | Issue | Severity | Priority | Effort |
|----|-------|----------|----------|--------|
| SEC-01 | Anonymous MQTT broker on all interfaces → telemetry forgery + control injection | **Critical** | **P0** | 30 min |
| SEC-02 | REST API: no auth, 0.0.0.0 bind, CORS `*`+credentials, unauthenticated state-changing POST | High | P1 | 30 min |
| SEC-03 | WebSocket bridge: no Origin validation (CSWSH) | Medium | P1 | 20 min |
| SEC-04 | Postgres on 0.0.0.0:5432 with trivial hardcoded creds (`vitish`/`vitish`) | Medium | P1 | 10 min |
| SEC-05 | Public-broker live feed fully spoofable; forged rows persisted as `live-demo` | Medium | P2 | 1–2 h |
| SEC-06 | Unbounded WS connections/per-client state → trivial LAN DoS | Medium | P2 | 1–2 h |
| SEC-07 | `requirements.txt` only lower-bound pins, no lockfile (supply-chain drift) | Low | P3 | 30 min |
| SEC-08 | Cesium ion token on disk (gitignored, correct today; residual accidental-commit risk) | Low | P3 | 10 min |

**SEC-01 (Critical/P0) — the demo-day integrity risk.** `docker-compose.yml:10-11` publishes 1883/9001 on `0.0.0.0`; `docker/mosquitto.conf:2-8` has `allow_anonymous true`. The router re-publishes any `/inject` topic as `control/cmd` (deliberately — "so a remote actor can drive the damage injector"), and `FusionService.on_accel` fuses **without** contract validation (only `isinstance` + `len>0`), unlike the recorder. Consequences from any venue WiFi device: forge `bridge/z24/accel` to drive BHI GREEN/RED, or `{"cmd":"cv","value":1.0}+{"cmd":"load","value":1.0}` → deterministically forces BHI ≈30.8 (RED). *Confirmed real by adversarial repro.*
**Fix:** at minimum bind compose ports to `127.0.0.1` (one line per service); properly: broker password file + `require_authentication`, a topic ACL limiting `bridge/z24/#` publishes, and `validate_accel` on the fusion ingress boundary.

**SEC-02 (High/P1).** `api.py:88-94` = `allow_origins=['*']` + `allow_credentials=True` — the docstring's claim that browsers refuse credentialed cross-origin calls is *wrong* for Starlette (verified in installed source: the wildcard is reflected to the request origin). No auth anywhere; `POST /api/demo/scenario` is unauthenticated, unrate-limited, and flips healthy↔rupture (fighting the demo driver). Default `api_host`/`ws_host` to `127.0.0.1`; add a shared-secret check + per-IP rate limit on the state-changing route.

**SEC-03 (CSWSH).** `websockets.serve` omits the `origins` argument, so any webpage on the LAN can open `ws://<laptop>:8765` and receive the full live telemetry + alerts. Pass explicit origins / require a shared-secret query param.

**SEC-04.** `docker-compose.yml:30-33` — pin `127.0.0.1:5432:5432`, generate the password per-deployment, or drop the published port (backend runs on the same host).

### 2.2 Bugs

| ID | Issue | Severity | Priority | Effort |
|----|-------|----------|----------|--------|
| ID | Issue | Severity | Priority | Effort | Status |
|----|-------|----------|----------|--------|--------|
| BUG-01 | **MemoryStore is bridge-agnostic** — z24 rms history/node state polluted by edge (`esp32-1`) and `live-demo` rows | High | P1 | Medium | **✅ FIXED** `dbd929b` + symmetric `recent_bhi('live-demo')` assert `a7240e4` |
| BUG-02 | `emit()` silently drops messages when the broker looks delivering but `publish()` fails | Medium | P2 | One line | **✅ FIXED** `a7240e4` |
| BUG-03 | `fusion.on_accel`/`stiffness.on_accel` raise on malformed accel payloads — swallowed by the bus, fused BHI stalls + ERROR spam every second | Medium | P2 | Small | **✅ FIXED** `a7240e4` |
| BUG-04 | Twin backend discovery is one-shot (`tried` latch) — never re-discovers a late/fallback-port backend (REPLAY badge forever) | Medium | P2 | Small | **✅ FIXED** `a7240e4` |
| BUG-05 | `contract.validate_accel` hero path omits node/rms-finite/flag checks the live-demo path enforces (upstream hole feeding BUG-03) | Low | P3 | Small | **✅ FIXED** `a7240e4` |
| BUG-06 | Offline replay fixture never advances scenario to `rupture` — the seeded-defect arc, scripted alerts, and collapse animation are dead code in REPLAY mode | Low | P3 | Medium | **✅ FIXED** `a7240e4` |

**BUG-01 (confirmed real by adversarial repro).** `MemoryStore.insert_accel/bhi/alert` accept `bridge=` and discard it; `recent_rms/bhi/alerts` and `current_state` ignore it. Three recorders feed one store — `run_all.py:122` (z24), `:129-130` (**always-on** `bridge/esp32-1/#`), `:145-146` (live-demo under `--live`). Verified: after inserting z24/esp32-1/live-demo rows, `recent_rms('z24')` returns the foreign rows and `current_state('z24')['nodes']` includes foreign nodes 1/2/3. Latent today (no non-hero rows in the shipped demo), but it **fires the moment the ESP32 board streams** — which is the active next feature. Fix: per-bridge deques or bridge-tagged rows, filtered on read; regression test asserting `store.recent_bhi('live-demo')` never returns z24 rows. **Status ✅ FIXED:** bridge-tag + filtered reads in `dbd929b`; symmetric `recent_bhi('live-demo')` isolation assert added in `a7240e4` (test_contract_parity.py).

**BUG-02 (silent message loss).** `mqtt_client.py:344-352` gates the bus fallback on a connection *snapshot* (`broker_delivering`), not on the publish *result*. When `publisher.publish()` returns False (transient `MQTT_ERR_CONN_LOST`, queue overflow), the message is on neither MQTT nor the bus — contradicts the docstring's exactly-once promise. One-line fix: fall back when `not broker_delivering or not ok`. **Status ✅ FIXED `a7240e4`:** `emit()` now falls back to the in-process bus when `not broker_delivering or not ok` (a `FakePublisher.ok=False` + live-subscriber harness proves the bus fallback fires); regression: `test_bugfix_regression.py::test_bug02_emit_fallback_on_publish_failure` (6 checks).

**BUG-03..06 status ✅ FIXED `a7240e4`** (regression file `backend/tests/test_bugfix_regression.py`, 39 checks, now gate 19/19; twin `config.test.ts` + `fixtures.test.ts`):
- **BUG-03:** fusion/stiffness coerce the whole accel window (node int-not-bool, all samples finite) BEFORE any ring mutation; malformed windows are dropped with a `log.warning` and BHI/floor/ring state untouched — 13 checks feed 7 malformed payloads into both consumers and assert no raise, no residue, valid windows still received.
- **BUG-04:** `config.ts` latch removed (latch on success only), API-port walk `[8000,8000+20)` mirrors `run_all.py`'s `_find_free_port`; ws.ts re-discovers before each connect (`DISCOVERY_AWAIT_MS=600` cap) — 3 vitest cases incl. the actual bug (backend boots LATE → second discovery finds it).
- **BUG-05:** hero `validate_accel` now enforces node positive-int (not bool), rms finite, flag ∈ {0,1}, all samples finite — 16 bad rows rejected, clean row + live-demo thin row pass.
- **BUG-06:** replay fixture auto-advances to `rupture` at the same beat the live driver publishes (`AUTO_RUPTURE_DELAY_S=75`) — 3 asserts pin healthy-before/flip-at-the-beat.

Suite after the sweep: backend **24 files PASS** incl. `verify_demo_arc.py` **19/19** (arc 87.1/67.5/33.6 preserved), twin **9 files / 76 tests PASS**, merge gate renumbered to **19/19**. BUG-01 core fix predates this sweep (`dbd929b`); its symmetric regression assert ships here.

### 2.3 Performance

| ID | Issue | Severity | Priority | Effort |
|----|-------|----------|----------|--------|
| PERF-01 | Trained-push MC-dropout scoring = dominant per-window CPU cost, ~15s first-call stall — yet contributes ~0 at demo scale | High | P1 | 2–3 h |
| PERF-02 | `/api/bridge/z24/stiffness` ~286ms, polled every 1.5s/tab — `np.linalg.inv(L)` hotspot | *see verdict* | P1 | 1–2 h |
| PERF-03 | 92MB `crack_seg.pt` lazy load (~3.9s) blocks the demo driver at the t=45 cv beat | Medium | P2 | <1 h |
| PERF-04 | Simulator runs 4 FEM eigen-solves/tick (~60ms), 3 computing the same constant f1 | Medium | P2 | 1 h |
| PERF-05 | BridgeMap rebuilds+re-sends 50-bridge GeoJSON on every store mutation (no gating) | Medium | P2 | 30–60 min |
| PERF-06 | JSONL flush+stat syscall pair per insert under the store lock; compaction rewrites whole file | Low | P3 | 1 h |
| PERF-07 | Main bundle 2.46MB raw/661KB gzip; map+charts not code-split | Low | P3 | 2–3 h |
| PERF-08 | `/health` does a 0.4s-timeout socket connect on every request | Low | P3 | <30 min |

**PERF-01 (High/P1).** Every ring-fill, `get_anomaly` runs 20-sample MC-dropout through BOTH the VAE/OCSVM (41 forwards) and LSTM-AE — ~168ms/window measured, executed synchronously in the publish thread under the fusion RLock; ×3 nodes ≈ 500ms burst every 10.24s; the **first** call builds the detector inline = 15.6s stall hitting ~t=10s into the demo (BHI gauge freeze). And at demo scale the push is measured ~0 (gate-16 LEG D). **Fix:** batch MC-dropout into one forward per component (~168ms→<10ms), pre-build the detector eagerly at startup, and share one ensemble evaluation per 10.24s across the 3 nodes.

**PERF-02 — *adversarial verdict: downgraded.* The claimed 286ms is real only without the BLAS thread cap the code deliberately sets (`backend/app/__init__.py:27-28`, `models/vibration/stiffness.py:38-43`). Under the shipped capped runtime, measured: snapshot median **28.6ms** (~2.2% of a core/tab), `np.linalg.inv` 0.2ms. The claim's numbers reproduce exactly in the no-cap config, which the codebase explicitly prevents.** Residual real issue (mild): no memoization — all 15 FEM solves recompute every 1.5s/tab, scaling linearly with tabs. Still worth the cheap fix: replace `inv(L) @ Ks @ inv(L).T` with triangular solves, and memoize `damage_from_f1` on a coarse f1 grid.

### 2.4 Code quality

| ID | Issue | Severity | Priority | Effort |
|----|-------|----------|----------|--------|
| CODE-F1 | **Stale "INERT / degenerate scaler" claims about the trained ensemble in code + generated docs** | **High** | **P1** | Low |
| CODE-F2 | MemoryStore silently ignores `bridge` in every insert/read (same root as BUG-01) | Medium | P1 | Medium |
| CODE-F3 | `Publisher.publish_accel/bhi/alert` are dead code (contract shapes duplicated in test fakes) | Low | P2 | Low |
| CODE-F4 | Free-port probing + API launcher duplicated across `run_all.py`/`api.py`/`ws_bridge.py` | Low | P2 | Medium |
| CODE-F5 | Runtime inference path prints warnings to stdout instead of logging | Low | P2 | Low |
| CODE-F6 | Demo beat labeled "LLM copilot recommendation" contradicts the rule-based-copilot guardrail | Low | P2 | One line |
| CODE-F7 | Hardcoded label range (`range(10,17)`) + physics constants duplicate the contract registry | Low | P3 | Low |
| CODE-F8 | `metrics_sheet.py` hardcodes the generation date in its output header | Low | P3 | Low |
| CODE-F9 | `models/fusion/bhi.py` reference class maps uncertainty 20 pts/fraction, contract says 10 | Low | P3 | Low |
| CODE-F10 | Illustrative regulator sub-index constants scattered across `api.py` | Low | P3 | Low |

**CODE-F1 (the #1 overall issue in this analysis).** After the 2026-08-15 non-degenerate retrain, the shipped ensemble is ACTIVE (gate 10 asserts separation: healthy dev 0.0 vs damaged mean 0.1158). Yet `scripts/metrics_sheet.py:469-470,504-505,658` and `scripts/verify_demo_arc.py:17-18` still print *"trained VAE/OCSVM ensemble is inert — degenerate shipped scaler"*, and the stale claim is baked into committed artifacts: `vault/05-Demo/Metrics.md:50`, `pitch/metrics/metrics-sheet.md:7,20`, `Idea-and-Deck.md:43`, `QandA-Dry-Run.md:38`, `Submission-Checklist.md:42`. **Running `metrics_sheet.py` today regenerates a false claim.** `vault/05-Demo/Deconfounding-Study.md:58` ("demo-scale trained inertness, Leg D") is CORRECT and must stay. **Fix:** replace scaler-level "INERT" with the measured split; better, derive the sentence at runtime from the loaded detector's `mode` attribute so future retrains can't re-stale it; regenerate both metric files; audit the 5 docs; re-run all 16 gates.

### 2.5 Architecture

| ID | Issue | Severity | Priority | Effort |
|----|-------|----------|----------|--------|
| ARCH-01 | Single-process, single-bridge design: 1.7L bridges = N processes; singleton set forbids multi-tenant | **Critical** | **P0** | Large (3–6 mo) / interim bridge-worker 2–4 wks |
| ARCH-02 | EventBus is synchronous in-process fan-out — recorder/Postgres latency throttles the whole cadence | High | P1 | 1–2 wks |
| ARCH-03 | Postgres schema flat/unnormalized: no registry, retention, partitioning; per-row autocommit inserts | High | P1 | 2–4 wks |
| ARCH-04 | **Raw waveform samples never persisted** — the retrain/data-flywheel plane does not exist | High | P1 | 1–3 wks |
| ARCH-05 | One healthy envelope + one physics identity per process — per-structure detection structurally impossible (the honest §117 limits are architectural, not model bugs) | High | P1 | 2–4 wks |
| ARCH-06 | MemoryStore bridge-agnostic + `state_cache.json` keyed by kind only (same root as BUG-01) | Medium | P1 | 3–5 days |
| ARCH-07 | Twin is hero-centric: WS fans every event to every client; fleet map is 49 static illustrative bridges | Medium | P1 | 2–4 wks |
| ARCH-08 | Single-host compose, anonymous broker, no TLS/auth, un-containerized backend — the demo→production leap is the widest gap | High | P1 | 2–4 wks |
| ARCH-09 | Strain/acoustic (§117) blocked at the frozen contract/recorder/fusion layers — need a generic telemetry envelope now | Medium | P2 | 3–6 wks |
| ARCH-10 | cv and load sub-indices are control-channel (scripted) evidence, not measured — fleet BHI needs per-bridge ingestion for both | Medium | P2 | 3–6 wks |

**ARCH-01 (Critical/P0) — the honest framing matters.** Every tenant concern is a module-level constant or singleton (`contract.py:22` freezes BRIDGE_ID; `events.py:86-92`, `db.py:447-475`, `simulator.py:566-575`, `stiffness.py:188-198`, `anomaly.py:45-51` are all process-global). A second `run_all.py` on another port would double-consume broker topics with independent state. **Interim:** bridge-worker mode (per-process topic prefix + shared store keyed by bridge + load-balanced API/WS tier). **Product:** the tenant boundary must be defined now — `bridge_id` threaded through every singleton — before any multi-bridge claim. Keep the single-process demo as the pinned golden path.

**ARCH-04 (High/P1, easy to under-rate).** The recorder inserts only `(node, ts, rms, flag)`; the 100-sample window is **dropped at the boundary**. There is no raw-window storage, no on-alert capture, no feature store — the §117 "per-structure-type retrain" has no live collection path, and the honest "no fleet data ever reaches a training set" limitation is architectural, not policy. **Fix:** optional raw-capture tier (on-alarm + periodic windows), compressed, bridge-tagged, gated OFF in the demo.

**ARCH-05 (this is the §117 answer).** The envelope, detector, and FEM are each a single process-global instance. The measured honest findings — HBTA damage not separable at score level, later-campaign healthy label {6} deviating like damage, demo-scale saturation — are **consequences of a shared envelope and a Z24-geometry FEM**, not model bugs. Per-structure retrain requires a per-bridge/structure-class model registry. The minimal change: key baseline/detector/tracker by `bridge_id`; parameterize the FEM (span/supports/mass/EI) as instance state.

---

## Category 3 · Enhancements & Modifications

| ID | Enhancement | Severity | Priority | Effort |
|----|-------------|----------|----------|--------|
| ENH-01 | Make MemoryStore bridge-aware (tag every record with bridge id) | High | P1 | 1–2 dev-days |
| ENH-02 | Build the twin edge-node status card (close task #39) | Medium | P2 | 1–2 dev-days |
| ENH-03 | Change-gate the BridgeMap GeoJSON subscription | Medium | P2 | ½ day |
| ENH-04 | Unify the two vibration-detector entry points (`load_predictor` vs `demo_predictor`) | Medium | P2 | 1 dev-day |
| ENH-05 | Fix stale "trained ensemble inert" prose in metrics/verify scripts | Low | P2 | ½ day |
| ENH-06 | Scale the simulated clock to demo playback speed (day-label/thermal desync at `--speed>1`) | Low | P3 | ½ day |
| ENH-07 | Make CORS origins environment-driven (`VITISH_API_ORIGINS`) | Medium | P2 | ½ day |
| ENH-08 | Postgres retention + 1-minute downsampling for pilot-scale ingestion | Low | P3 | 2–3 dev-days |
| ENH-09 | Add a jsdom test environment + component smoke tests to the twin | Low | P2 | 1–2 dev-days |
| ENH-10 | Eliminate the hand-mirrored BHI contract in the twin via `/api/config` + a parity test | Medium | P2 | 1 dev-day |

- **ENH-01** is the same root as BUG-01 but scoped as a proper engineering task (tag rows, extend the JSONL `_log`/`_apply_record` round-trip, filter reads, regression test, re-run `verify_gate.sh` — the tuple shape is load-bearing across gates + the `state_cache.json` reload).
- **ENH-02** closes task #39: the backend already serves `/api/bridge/esp32-1/state` and a manifest `edge_node` block; the twin is structurally unwired (`ws_bridge.py:76-77` subscribes z24 only; `main.tsx` polls nothing). Add a 5s REST poller + honest EdgeStatusCard (RSSI/heap/uptime, "self-test BIST tone" label) — **out of** the BHI/fusion path.
- **ENH-04**: the two detector entry points have different `n_healthy` (5 vs 10) and independent envelopes — a script exercising `load_predictor` is not testing the detector the demo runs (documented drift risk). Make `demo_predictor` the single factory; re-run gates 10/16 + `verify_demo_arc.py` (trained push must stay ~0 at demo scale).
- **ENH-10**: `store.ts:180-222` hand-copies BHI_W/GREEN/AMBER/WINDOW_N/FS and the comment documents its positional args don't line up with Python beyond the third. Extend `/api/config` (already carries fs/window_n) with the contract block; align the twin `computeBhi` signature; add a parity test gridding (cv,vib,load) against `contract.compute_bhi`. Cheap, high-value drift guard.

---

## Category 4 · Advanced Features

| ID | Feature | Severity | Priority | Effort |
|----|---------|----------|----------|--------|
| AF-01 | FEM-surrogate damage localizer: invert the Z24 FEM to a per-zone EI map in real time | High | P1 | 2–3 wks |
| AF-02 | Damage posterior + P(severe) decision band instead of point BHI | High | P1 | 2–3 wks |
| AF-03 | Crack-width metrology + longitudinal growth curves | High | P1 | 4–6 wks |
| AF-04 | Temperature-invariant fleet transfer: per-bridge thermal calibration compresses onboarding | Medium | P2 | 3–4 wks |
| AF-05 | Audit-trailed "inspector briefing" drafts from the honest ledger (LLM as drafting layer, never decision-maker) | Medium | P2 | 2 wks |
| AF-06 | AR field app: project live crack masks + width onto the bridge, write findings back to the twin | Medium | P3 | 6–8 wks |
| AF-07 | Online Bayesian recalibration of the twin FEM (model re-fits itself) | Medium | P3 | 3–4 wks |
| AF-08 | Sparse-sensor early warning: GNN over the bridge graph localizes damage from a sensor subset | Low | P3 | 8–12 wks |

**AF-02 (High/P1) is the strongest of these** — all three uncertainty building blocks already exist and are thrown away: MC-dropout recon-spread (infer.py:375-376), inter-node spread (fusion.py:125-129), and the u→BHI-points conversion (contract.py:117-120). Combine into a full damage posterior per window (epistemic + aleatoric + model-form) and emit P(severe) + an "inspect now / monitor / defer" band. This is the regulator-facing upgrade of the whole product.

**AF-01 (note the critic's demotion below):** a surrogate for the ~14 on-demand bisection FEM solves is real ML work for a speedup nobody experiences; damage % is an honestly-labeled explainability overlay, not fused into BHI. **Demote to P3 / fold into PostHackathon #118** — the critic flagged this lens's P1 score as overrated.

**AF-04** directly retires the label-{6} confounding (gate 16): fit a per-bridge f1-vs-temp coefficient from each bridge's own history, share a temperature-normalized healthy envelope across same-structure-type bridges. A new bridge gets a fleet-seeded envelope before it accumulates 30 baseline windows. **This is the deployment-cost + false-alarm advantage incumbents structurally cannot match.**

**AF-06, AF-07, AF-08 are all criticized as premature** (see Category 7 — critic's weak-recommendations list). Build AF-03/04/05 instead.

---

## Category 5 · New Additions

| ID | Addition | Severity | Priority | Effort |
|----|----------|----------|----------|--------|
| NEW-01 | Out-of-band alert dispatch (Telegram / email / SMS) + mobile push path | High | P1 | 0.5–3 days |
| NEW-02 | Real site temperature via Open-Meteo (keyless) replacing the simulated thermal model — **DONE 2026-08-17** | High | P1 | 0.5–1 day |
| NEW-03 | Expand GitHub Actions to twin lint + vitest + production build | Medium | P1 | 30–60 min |
| NEW-04 | IRC-118 / MoRTH IBMS condition-report generator (PDF + CSV) — **DONE 2026-08-17** | Medium | P2 | 3–5 days |
| NEW-05 | Strain/deflection runtime channel (contract + ingestion + sub-index) | Medium | P2 | 1–2 wks |
| NEW-06 | Defer TinyML; first attach a real accelerometer (I2C ADXL345/MPU-6050) to the ESP node | Low | P3 | bench first |
| NEW-07 | Defer full multi-tenant SaaS/RBAC/billing; ship a light per-bridge access token for pilots | Low | P3 | 2–3 days |
| NEW-08 | Landing page + hosted public demo (hosted LIVE tier gated on #121) | Medium | P2 | varies |
| NEW-09 | Enrich the LTBP/InfoBridge path: live NBI refresh + real regulator fleet conditions | Low | P3 | 1–2 days |
| NEW-10 | Defer BIM/IFC + Prometheus/Grafana; take the light alternatives (bridge-config JSON + `/metrics`) | Low | P3 | 1–2 days each |

**NEW-01 (High/P1) — the mission needs a phone.** Today an alert exists only in the browser tab and the store (grep for telegram/smtp/webhook: zero matches). "Prevent the next Morbi" is undeliverable without a push path, every pilot needs it, and it's the strongest live-demo beat (a real RED BHI 33.6 firing to the presenter's phone). Telegram = one free HTTP POST, reusing the existing bus-subscriber pattern (`EdgeNodeMonitor` is the template) and the **frozen alert payload** — no contract change. Degrade to log-only when a channel is unreachable (preserves the offline demo posture). Alert wording must stay floor-based/probabilistic, never "collapse imminent."

**NEW-02 (DONE 2026-08-17):** `backend/app/site_temperature.py` probes the keyless Open-Meteo forecast API for the real Koppigen anchor (47.136/7.578) — urllib stdlib, 15-min TTL cache, 3s bounded fetch, never raises (every failure degrades to the simulated seasonal model). The `temp_source` label lives in the block and **flips honestly on fallback** ("measured air temperature — Open-Meteo forecast" vs "simulated seasonal temperature (day-of-year model) — not a measured sensor"); the twin renders it in the ProvenancePanel as a `measured`/`modeled` chip, and the same block rides `/api/manifest` (`site_temperature`) and `/api/bridge/z24/stiffness` (`site_temp`). Real T is **display/provenance only** — it is never fused into the BHI, the anomaly floor, or the thermal overlay, per the spec; the deterministic demo arc is untouched (arc re-pinned 19/19 in the suite). `VITISH_SITE_TEMP_DISABLE=1` forces the offline fallback in the test runner / gate scripts (no network in CI); 23-check backend test + 5 vitest cases cover the measured, cache, force-probe, fallback, garbage, and manifest-flip paths. Verified live: when Open-Meteo rate-limited the demo IP, the panel honestly flipped to `site temp · 10.9°C [modeled] … simulated seasonal`. Test files went 18 → **19**; twin vitest 58 → **71**.

**Spec (original):** thermal wander is the top false-alarm source in vibration SHM; today `temperature.py` is an explicitly-labeled synthetic day-of-year sinusoid. Open-Meteo (free, keyless, historical+forecast) for the real Koppigen anchor (47.136/7.578) makes the gate-16 thermal-normalization claim defensible on real data. The `temp_source` manifest label must flip on fallback so no surface shows "measured" when it's modeled; the deterministic demo arc is untouched (the thermal overlay sits on the floor, which is pinned). **Do not feed real T into the anomaly floor until the temperature-normalized retrain exists.**

**NEW-03 (DONE 2026-08-17):** `ci.yml` now runs twin lint + vitest + production build (in addition to `run_tests.sh` + typecheck). The twin's 58 vitest tests, `eslint --max-warnings=0`, and the production build are gated in CI — a twin regression can no longer merge while backend gates stay green.

**NEW-04 (DONE 2026-08-17 = §7.6 item 10):** `backend/app/condition_report.py` assembles the existing pieces (live state, D1-3 condition card, D1-4/D2-11 Markov projection + next-inspection, alerts, NEW-02 site temperature) into (1) a per-bridge **PDF** condition report via reportlab platypus and (2) a fleet **IBMS-inventory CSV** (one row per bridge, NBI rating + next-inspection year + years-to-poor band). Every surface carries the mandatory label: *"DRAFT in IRC-118 format — fields to be confirmed against the final MoRTH IBMS schema. Not a certified assessment"* — the disclaimer is both a cover block and a `record_disclaimer` column on every CSV row so the caveat survives cut-and-paste export. Regulator healths keep the "SEEDED/illustrative" label; the generator never invents a field (everything comes from the services the UI reads). New `GET /api/bridge/{id}/report.pdf` + `GET /api/fleet/report.csv`; suite 19 → **20 files** (test_condition_report.py: compose/pdf-text/inventory/route checks). Sample artifacts in `docs/samples/` (uncommitted local). requirement: reportlab added.

**NEW-05 (mission-aligned but data-blocked — see critic):** Morbi was a tendon rupture; the sensor class that catches it is strain, not acceleration — and the HBTA package already trains a STRAIN lane (15 gages). But no real strain data is in-repo (honestly flagged blocked), so a runtime channel would be synthetic-only. Build it as an honest channel stub at most; the real lane waits on pilot sensors. **Update (2026-08-16):** AE is the complementary class — it catches the *initiation* moment strain/DE can't see at global scale; the verified AE data catalog + §117 improvement levers are in Category 8.

---

## Category 6 · Verification & Testing Strategy

| ID | Gap | Severity | Priority | Effort |
|----|-----|----------|----------|--------|
| TEST-F1 | CI runs only backend gates + twin typecheck — twin vitest/lint/build never gated | High | P1 | 1–2 h |
| TEST-F2 | No twin+backend e2e; every `.tsx` has zero test coverage; no browser automation | High | P1 | 0.5–1 day |
| TEST-F3 | **The two trained-ML gates SKIP silently on fresh clone/CI** — the strongest correctness claims only verified on the dev machine | High | P1 | 0.5–1 day |
| TEST-F4 | No performance/load testing; WS fanout + twin map/render hot spots un-gated | Medium | P2 | 0.5–1 day |
| TEST-F5 | PostgresStore SQL path, failover latch, state_cache JSONL reload/compaction/corrupt-line handling untested | Medium | P2 | 0.5–1 day |
| TEST-F6 | No security testing or secret-scan gate (CORS/bind are "local-only-safe" by convention only) | Medium | P2 | 0.5 day + |
| TEST-F7 | Recovery paths untested: broker reconnect/backoff, WS disconnect + drop-oldest, stale-message dedup, `_shutdown` ordering | Medium | P2 | 0.5–1 day |
| TEST-F8 | No coverage measurement; no automated UAT of the 7-beat storyboard (16 standalone scripts, no discovery) | Low | P3 | 1–2 days |

**TEST-F3 (DONE 2026-08-17).** `test_trained_path.py` and `test_deconfounding.py` LEG C no longer skip on a fresh clone/CI: small trained weights (`vae.pt`/`ocsvm.pkl`/`scaler.pkl`/`lstm_ae.pt` + meta, ~235 KB) and a deterministic real-Z24 fixture (`data/z24/fixture/`, 4 groups ≈ 2.8 MB, `scripts/make_z24_fixture.py`) are committed, shared via `backend/tests/_z24_data.py` (prefers the full `inputs.npy` when present, falls back to the fixture). Both gates print `TRAINED_REAL_DATA=RUN(fixture|full)` and `run_tests.sh` **fails under `CI=1`** if either prints `TRAINED_REAL_DATA=SKIP`. LEG C's healthy claim was honestly split during the refactor: the old "healthy {0,1} stays ~0 (measured 0.0000)" was actually a label-0-only slice — label-1 genuinely deviates max ~0.31, so it is now pinned as a documented state-confound alongside label {6} (max ~0.37), with a state-agnostic retrain required to flip those assertions back to a ~0 bound.

**TEST-F2 — the UAT the judge runs manually, automated.** Add Playwright: (1) headless twin smoke — boot `run_all.py --demo` + `vite preview`, assert LIVE badge, BHI gauge, 50 map markers, zero console errors; (2) storyboard-arc e2e — assert BHI moves GREEN→AMBER→RED and the 4 alerts appear. Wire as a separate CI job. `backend/scripts/e2e_live_run.py` exists but is not in any gate.

**TEST-F5** — a Postgres service-container job asserting bridge-scoped isolation (z24 vs live-demo), the 3-failure failover latch, and the JSONL reload/compaction/corrupt-line skip. `state_cache.json` currently sits at 0 bytes — the persistence path is essentially unexercised.

**TEST-F6** — three gates: a config-assertion test that `create_app()` refuses wildcard-CORS/0.0.0.0 unless `VITISH_LOCAL_DEV=1` (kills the convention-only guardrail); `pip-audit` + `npm audit` + a secret-scan in CI; OWASP ZAP baseline post-hackathon.

---

## Category 7 · Beyond the categories (critic pass)

### 7.1 Top opportunities (P1-rated, hours each — the critic's re-rank)

1. **Stale "inert" prose sweep (CODE-F1)** — *this is P1, not P3*; a judge who runs `metrics_sheet.py` sees the repo contradict its own ACTIVE state and its pitch.
2. **Out-of-band alert dispatch (NEW-01)** — Telegram v1, env token, fail-open, throttled, honest wording.
3. **RUL/decision surface (S1)** — fleet ranking + per-bridge P(severe) band, mandatory "Markov projection, small n — not certified RUL" label; the 49 regulator healths are seeded/illustrative so the ranking must never read as real inspection data.
4. **Real site temperature (NEW-02)** — Open-Meteo + honest `temp_source` flip on fallback.
5. **Stop the trained-ML gates SKIPping silently (TEST-F3)** — restore weights + inputs.npy in CI; keep advisory until stable so the green streak never flakes.
6. **De-risk the IoT leg (S8)** — fix `esp01-1`/`esp32-1` mismatch + bench proof (board → MQTT → API → twin card, honestly labeled self-test-bist) or the documented simulator proof.
7. **MemoryStore bridge-awareness + BHI-contract parity (ENH-01 + ENH-10)** — per-bridge deques + the `/api/config` contract block + `computeBhi` parity test.
8. **CI parity (NEW-03 + TEST-F5)** — gate twin vitest/lint/build and exercise Postgres.

### 7.2 Risks (things that would hurt the brand if mishandled)

- **RUL overclaim:** "years to NBI≤4" must read as projection-under-a-prior, never certified remaining life. Label on every render and pitch mention; extend the disclosure beat to the ranking table. **Remediated 2026-08-17 (S1):** the mandatory label is on the HealthPanel band and the fleet-priority card, and the ranking table itself carries "49 regulators illustrative — not certified RUL" (see §7.6 item 7).
- **Demo-vs-pitch ML gap (no lens framed this as narrative risk):** the trained ensemble is **invisible at demo scale** — amplitude-saturated, arc floor-carried by construction (gate-16 LEG D). Company-Project line 71 lists the trained path as "REAL + verified," but a rigorous judge watching the demo sees the AI never move the needle on the only stream on screen. Either rephrase line 71 to "separates on real Z24 data; the live-demo overlay is floor-carried," or make the trained path fire at demo scale (the temperature-invariant/scale-robust retrain).
- **The $980 pilot-kit SKU is unbuildable today:** the only hardware is a BIST-tone ESP-01S (no accelerometer, no ADC); no camera node or validated gateway. The pilot-kit BOM needs a real accelerometer node + cost truthing before the "deploy in a day / ~$980" and "$10-class wireless accelerometer" claims survive contact with a pilot.
- **Geographic mismatch:** the fleet map shows 50 famous **US** bridges while the GTM is MoRTH/India; the LTBP/NBI priors are FHWA/US. Relabel honestly ("illustrative international reference network") or build an Indian illustrative fleet with IRC-118 ratings, and plan an India condition-data path.
- **The actual critical path is non-code:** no named CEO/BD and no pilot funnel (#120 has 8 blocked human actions). Every technical recommendation is subordinate to it — the 90-day plan needs a BD/partnership workstream with dated owners.

### 7.3 Weak recommendations the critic would cut (do not build)

AR field app (showcase only), GNN sparse-sensor localizer (no dataset/buyer), **FEM-surrogate damage localizer (overrated at P1 — demote to P3)**, online Bayesian FEM recalibration (risks destabilizing the pinned arc), unifying `load_predictor`/`demo_predictor` (deliberate distinction — churn with zero behavior change), fleet-flywheel append code before any pilot observation exists (premature), "open source = distribution" framing (the moat is procurement + commissioned data), strain channel beyond an honest stub (data-blocked), live NBI refresh (US data, doesn't serve India GTM), perf/load testing + numeric coverage (low value at demo scale — spend those hours on the pilot funnel).

### 7.4 The four gaps the critic added that no lens surfaced

1. **Repo self-contradiction is worse than any lens scored it** (CODE-F1 → promoted to the #1 overall item).
2. **Pitch-vs-demo ML gap** (7.2 above).
3. **Geographic mismatch** (7.2 above).
4. **No honesty-label regression gate:** the twin's honesty labels (LIVE-badge gating, "simulated temperature", floor-carried notes) live in UI code with nothing asserting they stay attached as the UI evolves. A cheap automated check protects the brand from UI drift.
5. **MoRTH deadline 30 Sep 2026 is ~6 weeks out:** risk-prioritized-inspection narrative, IRC-118 report generator, and a provisional (labeled) CRN↔BHI mapping should be sequenced against the date, not tech convenience.

### 7.5 Adversarial verification results (independently reproduced)

| Finding | Verdict | Adjustment |
|---------|---------|------------|
| MemoryStore bridge-agnosticism (BUG-01) | **CONFIRMED** — reproduced: foreign rows returned for `recent_rms('z24')` | unchanged (medium) |
| Anonymous MQTT → forgery/control injection (SEC-01) | **CONFIRMED** — verified end-to-end in source; `{"cmd":"cv","value":1.0}+load` deterministically forces BHI ≈30.8 | unchanged (high) |
| REST API no auth / CORS / 0.0.0.0 (SEC-02) | **CONFIRMED** — Starlette origin-reflection verified in installed source | unchanged (medium) |
| MC-dropout trained-push cost (PERF-01) | **CONFIRMED** — reproduced; cadence *understated* (continuous ~3/tick after ring fill, not 10.24s), magnitude *possibly overstated* (bracketed 25–188ms) | unchanged (medium) |
| `/stiffness` 286ms hotspot (PERF-02) | **NOT reproduced at severity** — real only without the BLAS thread cap the code deliberately sets; shipped runtime ≈29ms | **downgraded to low** |

### 7.6 The 90-day priority sequence

**NOW — days 1–14 (all 6 DONE 2026-08-17; nothing touched the pinned arc or gates):**
1. ✅ Fix stale "inert" prose (`metrics_sheet.py` 3 sites + `verify_demo_arc.py:18`); re-run all 16 gates; regenerate the metrics sheet. — swept code + 5 committed docs, metrics regenerated, gates now 18.
2. ✅ Fix the ESP-01S bridge-id mismatch (`esp01-1` vs `esp32-1`). — aligned + byte-identical host sim pinned as gate 13.
3. ✅ Telegram alert dispatcher on the alert topic (env-token, fail-open, throttled, honest wording). — gate 17.
4. ✅ CORS origins env-driven (`VITISH_CORS_ORIGINS`) + docstring/ROADMAP update.
5. ✅ MemoryStore bridge-tag (append field, update JSONL `_apply_record`/`_log`) + extend `/api/config` with the BHI contract block + `computeBhi` parity test. — gate 18.
6. ✅ CI: twin vitest + lint + production build. — plus **TEST-F3** no-silent-SKIP (below).

**30 days — product surfaces + verifiable CI, sequenced against the 30 Sep IBMS deadline:**
7. ✅ RUL decision surface: fleet ranking + per-bridge P(severe) band with honest labels + never-quote list update. — **S1 DONE (2026-08-17):** `deterioration.py` now returns a `years_to_poor` band (first year each p10/expected/p90 series crosses NBI≤4, `already_poor` when the current condition is already ≤4); new `GET /api/fleet/priority` ranks all 50 bridges by next-inspection year (most urgent first, hero GREEN last) with the honest "49 regulators seeded/illustrative — not a certified RUL" label; the HealthPanel carries the "Projected years to NBI≤4 · decision band" (band + expected + next-inspection year + mandatory honesty label); the fleet map carries a `FleetPriorityPanel` overlay (live `/api/fleet/priority` poll with an offline deteriorationFixture mirror) — during the demo arc the hero climbs the ranking as it degrades. Q&A landmine table updated.
8. ✅ Open-Meteo real site temperature with offline fallback + `temp_source` manifest flip. — **NEW-02 DONE (2026-08-17):** `backend/app/site_temperature.py` probes keyless Open-Meteo for the real Koppigen anchor (47.136/7.578), 15-min TTL cache, never-raises fallback to the simulated seasonal model; the temperature source label flips honestly so no surface shows "measured" when modeled (manifest `site_temperature` + stiffness `site_temp` blocks + ProvenancePanel `measured`/`modeled` chip). Real T is display/provenance only — never fed into the BHI, anomaly floor, or thermal model. Suite went 18 → **19 files** (23-check test), twin vitest 58 → **71**, arc re-pinned 19/19.
9. ✅ CI artifact-restore job running `test_trained_path` + deconfounding LEG C — no silent SKIP. — **TEST-F3 DONE:** small trained weights (`vae.pt`/`ocsvm.pkl`/`scaler.pkl`/`lstm_ae.pt` + meta, ~235 KB) and a real-Z24 fixture (`data/z24/fixture/`, 4 groups ≈ 2.8 MB, built by `scripts/make_z24_fixture.py`) are COMMITTED; both trained gates run real evidence on a fresh clone/CI (`TRAINED_REAL_DATA=RUN(fixture|full)`), and `run_tests.sh` **fails under `CI=1`** if either prints `TRAINED_REAL_DATA=SKIP`. LEG C's healthy claim was honestly split — label {0} (envelope's own state) stays ~0; healthy labels {1} and {6} are pinned as documented state-confounds (max ~0.31/~0.37) rather than hidden.
10. ✅ IRC-118 / IBMS condition-report generator (draft-style, explicitly not certified). — **NEW-04 DONE (2026-08-17):** `condition_report.py` (reportlab platypus) — per-bridge regulator-facing PDF (bridge identity, live BHI/sub-indices, D1-3 condition card, Markov projection table + next-inspection + years-to-poor band, recent alerts, NEW-02 site temperature, honesty footer) + fleet IBMS-inventory CSV (50 rows: NBI rating, next-inspection year, years-to-poor, `record_disclaimer` on every row). Mandatory "DRAFT in IRC-118 format — fields to be confirmed against the final MoRTH IBMS schema. Not a certified assessment" on the cover and in the CSV. Routes `GET /api/bridge/{id}/report.pdf` + `GET /api/fleet/report.csv`; suite 19 → **20 files**; samples in `docs/samples/`.
11. ✅ Edge bench proof: board → MQTT → `/api/bridge/esp32-1/state` → twin status card with honest BIST labels (or documented sim proof if no board). — **DONE 2026-08-17 via the documented-sim-proof branch** (`docs/EDGE-BENCH-PROOF.md`) — the board was NOT flashed (Key-Decisions #11, H8-gated stretch; standing constraint leaves the hardware). The doc records the full bench protocol a real proof would run, what is committed and proven today (`firmware/esp32` + `firmware/esp01` firmware, `tools/esp` flash tooling + MicroPython images + CP210x driver installer, `scripts/edge_sim.py` host simulator byte-identical to the firmware's BIST signal logic), and the exact repro of the PROVEN leg: `backend/tests/test_edge_node.py` (54 checks: monitor per-slot, esp01-1 not silently ignored, recorder capture, API/manifest surfaces) + `backend/tests/test_honesty_gate.py` (46 checks, item 15: LIVE gating). The only unproven link is the physical board → MQTT hop; the edge `live` flag stays gated on a real measured packet (item 15), so no LIVE badge appears until a board is bench-tested. Twin status card is tracked under Phase-4 task #39.
12. ✅ Twin+backend e2e smoke in CI (run_all on the event bus: `/health`, `/api/bridges`, `/api/config`, one WS connect). — **DONE (2026-08-17):** `backend/scripts/e2e_stack_smoke.py` boots the real one-command stack (`app/run_all.py`, no `--demo`/`--live`) as a child process and proves the twin's three data contracts over loopback: `/health` (status ok, service `vitish-shm-backend`, bridge z24), `/api/bridges` (count 50, hero id z24), `/api/config` (z24 block + `bhi.weights` ENH-10 block, ws_port matching the banner), then **one WS connect** that must receive the `hello` frame and a live `bridge/z24/bhi` envelope with a numeric bhi and a valid state (measured: bhi 87.1 GREEN). The simulator replays real Z24 when the datum is present and falls back to synthetic pink-noise otherwise, so the smoke is deterministic in CI without the 992 MB download; `VITISH_SITE_TEMP_DISABLE=1` forces the offline modeled fallback (mirrors `run_tests.sh`). Clean subprocess termination in `finally`. Suite 20 → **21 files**.
13. ✅ Postgres service CI job exercising the SQL path + failover latch. — **DONE (2026-08-17):** new `pg-store` CI job starts a `postgres:16` service container (published on localhost:5432, `pg_isready` health-gated) and runs `backend/scripts/ci_pg_path.py` with `VITISH_DB_DSN` set — real SQL evidence, no silent SKIP (`CI=1` downgrades a missing-DSN SKIP to a failure, matching the TEST-F3 pattern). The script exercises the REAL persistence path: accel/bhi/alert round-trip fidelity (values, types, newest-first ordering, per-bridge scoping incl. a second `reg-001` bridge), durability across a fresh connection (`create_tables=False`), and the runtime-failover latch — kill the live connection → 3 inserts mirror into the in-memory ring WITHOUT raising → paced reconnect resumes Postgres → degraded-window rows stay volatile (never back-filled). The latch's logic is ALSO regression-tested without Docker in the normal suite via `backend/tests/test_pg_failover.py` (deterministic fake psycopg2, 12 checks, no server). Suite 21 → **22 files**; the pg path stays OUT of the runner so the main suite remains air-gapped/Postgres-free.
14. ✅ Multi-bridge proof: a second synthetic bridge via env + a bridge registry, scoped honestly as "onboard in days," not "a day." — **DONE (2026-08-17):** new `backend/app/bridge_registry.py` parses `VITISH_EXTRA_BRIDGES=<id>:<name>:<city>:<state>[:<lat>:<lon>]` (comma-separated; malformed/duplicate/hero-colliding entries skipped, never crash boot; missing coords fall back to deterministic schematic coordinates so extras land on the map instead of the twin's zero-coord drop). Each extra is a **SIMULATED** bridge: `synthetic: True`, `source_label` ("simulated telemetry (synthetic channel model) — not a real sensor"), and a module-level `ONBOARD_LABEL` that scopes the demo answer — config + registry prove the SOFTWARE path is a same-run exercise, but a real deployment is a **days-scale** task (sensor+edge-node install, baseline/calibration, channel-model fit, registry+config), never "a day". Wiring: the simulator streams each extra's own healthy synthetic channel (own seed, same measurement chain; flag always 0); `fusion.py` subscribes `bridge/+/accel` and routes the hero to the existing anomaly-scored path **byte-identical** while extras run a **heuristic-only** BHI (RMS-deviation vs. the extra's own EMA baseline) that **never calls `get_anomaly`/`last_evidence`** (that baseline belongs to the hero path — its evidence window must not be clobbered); `regulator_bridges.all_bridges()` appends extras AFTER the 49 regulators so the default (no env) inventory stays exactly **50** and every existing count assertion keeps its meaning; `run_all` subscribes a per-extra recorder so `/api/bridge/<extra>/history` + `/state` serve real fused rows; `/api/config` exposes a `multi_bridge` block (extra list + `onboard_label`). Suite 22 → **23 files** (`backend/tests/test_multi_bridge.py`, 35 checks: parse/labels, 50-parity, 50+2 inventory + geojson `synthetic` property, fusion routing incl. the get_anomaly/last_evidence spy proving extras never touch the model baseline, ghost-bridge ignore, `/api/config` + `/api/bridges` + extra-history 200). Arc + gates preserved; visual twin footnote (FleetPriorityPanel regulator-count + ONBOARD_LABEL when extras exist) is tracked as a cosmetic follow-up.
15. ✅ Honesty-label regression gate (LIVE-badge gating, simulated/fallback labels always present). — **DONE (2026-08-17):** new `backend/tests/test_honesty_gate.py` (46 checks) sweeps every human-facing surface and fails the suite if a label is dropped or a non-live surface claims live. **LIVE-badge gating:** the edge `/api/bridge/<slot>/state` `live` flag is now `online AND received` (real measured packet + fresh), never the slot being monitored — an unwitnessed ESP32/ESP-01S returns `live: False` with a `live_label` ("OFF-LINE — no measured packet yet; firmware committed, board not flashed/bench-tested"); even an online node keeps the honest `signal_kind: self-test-bist` + `honesty.accel_is` ("no accelerometer attached"). The hero's `live: True` is stream-liveness only — its state now carries a `telemetry` block mirroring the manifest's canonical label (`channel_models.get_data_source_label`, new helper) reading "real Z24 benchmark replay" or "procedural synthetic", with the note "never a live field sensor". `/api/live` stays `enabled: False` unless the stack started with `--live`. **Simulated/fallback labels always present:** `/api/bridges` gained a per-class `labels` block (hero "never a live field sensor" / regulators "never real inspection data" / extras = the registry `source_label` when present); regulator `/state` now returns `illustrative: True` + the same honest note (it had none); extra `/state` serves its registry record verbatim (`synthetic`, `source_label`, `onboard_label`) so the simulated nature can't be flattened away; the manifest's `site_temperature` block is asserted for BOTH label paths (measured Open-Meteo wording and the simulated-seasonal fallback, the latter via injected `_http_get` — deterministic, no network); `/api/config` `multi_bridge.onboard_label` + `bhi` block and `/api/fleet/priority` `priors_label` + "not a certified RUL" note are pinned. Suite 23 → **24 files**. Existing `test_edge_node.py` updated to assert the new gating (pre-packet live=False, post-packet live=True + BIST still honest). The twin's SourceBadge already disambiguates transport ("LIVE · backend ws") from sensor; the data-level gating now lives in the backend + is regression-tested. Arc 19/19 + all 18 gates preserved.

**90 days — pilot-enabling + publication; the BD track runs in parallel all 90 days:**
16. **BD/partnership workstream with dated owners and acceptance criteria** — 2–3 pilot LOIs, incorporation + IP review, bottom-up India TAM, CRN↔BHI calibration-study protocol (#120) — the real critical path. — **DONE (2026-08-17):** the dated workstream is `vault/08-Startup/BD-Workstream.md` — every row carries an owner slot + acceptance artifact + deadline, the bottom-up India TAM is written from real cited counts (NH ~1.7 lakh @ $260/bridge/yr ≈ ~$44M/yr ceiling, not the $3.96B slide number; state/rail layers TBD by pilot), the CRN↔BHI calibration-study protocol (§119/§120) is specified (ordinal CRN regression onto the three sub-indices, n<8 ⇒ "feasibility read not certified mapping", arc re-pinned only if the study says the demo band is wrong), and the honest boundary is explicit (a verbal "interested" is not an LOI; the LOI text may not claim a certified rating). What the doc cannot do is name the humans: **CEO/BD remains the single OPEN hard dependency** (2026-08-31) — LOIs, incorporation, and the calibration study all wait on it. The in-repo-able portion is the plan + TAM + protocol; the signed artifacts are dated acceptance targets, not shipped items.
17. Temperature-invariant / scale-robust retrain so trained evidence fires at demo scale (closes the pitch-vs-demo ML gap; flips gate-16 LEG C bound). — **DECISION GATE DONE (2026-08-18) = NO-FLIP — see `docs/ITEM17-RETRAIN.md`.** Pipeline + tools built (`3461ee5`): coordinated temperature-diagonal augmentation (every healthy window stretched to each thermal f1 and paired with its T), features-mode VAE/OCSVM + RMS-normalized LSTM-AE, temperature threaded through inference (per-call override + site-temp resolution), probe measuring LEG C/D bounds. Full-Z24 candidate trained on GPU and measured through the REAL suite `test_deconfounding.py`: **FAIL, 3 assertions** — label{0} broke to 0.1408 (shipped 0.0000), damaged mean collapsed to 0.0000 (shipped 0.1158), demo-damage push still 0; only label{1} (0.3063→0.0000) cleared. Root cause measured: `peak_freq` (max-PSD bin) is not a first-mode estimate on real Z24 windows (group p50s 0.4–15.3 Hz; single-window periodograms are too noisy), so the diagonal conditioning never formed for real data. **Decision: keep shipped weights — the arc 87.1/67.5/33.6 and all 19 gates are untouched and re-verified; item-17 goal remains OPEN with a documented next experiment (band-limited multi-window f1 tracking + wider cold grid).** Candidate artifacts stay in gitignored `models/weights_scale_temp/`.
18. Crack-width metrology (pixel-scale, uncalibrated, honestly labeled) on the YOLO-seg path.
19. Honest-findings methodology write-up + publish the three reusable pipelines with licenses; dacl10k/SDNET stay out of public artifacts.
20. Landing page + hosted public demo — only after CORS/auth-token/secret-scan land.
21. Fleet-prior learning-loop v1: observed-transitions store + append path before the first pilot produces data.

**Explicitly deferred (do not schedule):** AR field app, GNN sparse-sensor localizer, FEM-surrogate localizer, online Bayesian FEM recalibration, strain/deflection runtime channel, multi-tenant SaaS/RBAC/billing, BIM/IFC import, Prometheus/Grafana, perf/load testing, numeric coverage measurement, live NBI refresh.

---

## Category 8 · §117 Follow-up: HBTA Detection Improvement & Acoustic-Emission Data *(addendum, 2026-08-16)*

**How this was produced:** a 29-agent workflow (4 dataset finders → 2 independent improvement-method agents grounded in the SHM literature → 21/21 candidate URLs verified by fetch/download → 1 synthesizer) ran over the measured 2026-08-16 server HBTA findings. Every number below is as-measured or as-verified; nothing strengthened. This section supplements the §117 entries in Categories 1–7 (ARCH-05, ARCH-09, NEW-05, 7.3).

### 8.1 The root cause, sharpened (two things earlier passes missed)

The measured score-level CHECK on both HBTA lanes is **not model capacity** — two independent methods agents converged on the same structural causes:

1. **The shipped score is geometrically blind to HBTA damage.** `models/vibration/infer.py` computes `dev = max(0, t_s − envelope_hi − margin)` — an **upper-tail** test that fires only when the raw trained score *exceeds* the healthy ceiling. HBTA damage is a **downward** signature (strain RMS drops ~50% per severity), so damaged windows land *below* the healthy envelope, score ≈ 0, and the envelope absorbs them. Healthy dev max **0.4179** vs damaged means **0.0015–0.0046** (accel) / healthy 0.0 vs damaged 0.0000–0.0025 (strain) is the **wrong test direction, not weak signal**.
2. **One-class novelty is the wrong tool for a labeled dataset.** HBTA ships DS1–DS8 severity labels; VAE/OCSVM + LSTM-AE fits P(x|healthy) and discards them. A supervised ordinal severity model can exploit the already-measured monotone strain-RMS-vs-severity trend (SB 0.113→0.052–0.073, SC 0.125→0.046–0.061) and return a severity ranking instead of a binary flag.
3. The healthy-side binding constraint: **pooled EOV**. The healthy reference mixes P1/P2 pier positions × SM/NM monitoring modes × Y/Z axes × SB/SC gage families → healthy strain-RMS CV ≈ **50%**, so no severity mean clears the pooled 2σ band. The verify harness already proved the point: first-N warmup → **54% false alarm** vs stratified warmup → **5–13%**.

### 8.2 Improvement levers (ranked; each independently testable in `verify_hbta.py`)

| ID | Lever | What | Effort | Honest expected impact |
|----|-------|------|--------|------------------------|
| IMP-01 | **Fix the score direction** | Signed one-sided index / lower-tail percentile for RMS & band powers (upper-tail for features that rise under damage), or a one-sided CUSUM on the signed residual | LOW (near-zero) | Prerequisite — restores all detection power the upper-tail envelope threw away |
| IMP-02 | **Supervised ordinal severity on strain features** | Ordinal regression / monotonic-constrained gradient boosting on per-gage RMS (+ strain mean/range), with **recording-grouped CV** (windows are contiguous + channel-major within a recording — random splits leak; prep's healthy/damaged split is already by-recording, extend that discipline to the training folds) | LOW–MED (~2–5 dev-days) | DS3+ detection to high-70s–90s% at a pinned 5% FA + severity estimate. **DS1 honestly stays near the FA floor — physical, report it, don't tune it away** |
| IMP-03 | **Per-operating-state healthy envelope** | Fit scaler/envelope/one-class per stratum (position × mode × axis × family) or cluster operating states (k-means/GMM); score each window against its own state | LOW (~1 day) | CV 50%→~15%, 2σ band shrinks 2–3×; the measured ~50% severity drop then clears it. Highest evidence-per-effort experiment (implementable as a `--state-columns` mode in verify_hbta.py — provenance already in `healthy_ch.npy`/`damaged_ch.npy`) |
| IMP-04 | **Longer windows + modal-frequency tracking (accel lane)** | 10.24 s gives Δf = 0.098 Hz ≈ 5 FFT bins across a ~0.5 Hz shift; a single Hann periodogram has ~100% relative variance. 30–60 s overlapped windows + FDD/SSI/ESPRIT → a frequency-drop index (f ∝ √(k/m), physics-based, load-independent) | MED (~3–10 dev-days) | Clean separation on DS3+ once state/temperature-conditioned. Caveat: temperature moves frequencies as much as early damage (Z24 f1 wanders 14.5% p2p vs a ~0.5 Hz damage shift) — gate-16's de-confounding precedent is the required guard |
| IMP-05 | **Load / reference-channel normalization** | Strain RMS scales with applied load; traffic is a prime mover of the healthy CV. Normalize by WIM/traffic energy, or a reference gage on an undamaged element (channel-to-reference RATIO cancels common-mode load) | MED–HIGH | Multiplicative with IMP-03; removes the load axis from strain |
| IMP-06 | **Multivariate strain features** | Per-band powers, **band ratios** (first-order load-invariant), crest factor, kurtosis, zero-crossing rate; PCA-whiten + Mahalanobis novelty | MED | Rescues channels silent in scalar RMS if damage redistributes spectral energy |
| IMP-07 | **Residualize EOV** | The temperature covariate (`features.py` index 6) is a pass-through constant 0.0 today — **no EOV compensation is active**. Fit healthy feature-vs-environment mapping (temp, humidity, traffic) and monitor the residual (regression, cointegration, SSI residuals) | MED–HIGH | Z24 literature: residual-based monitoring exposes damage fully masked by environment |

**Execution order:** IMP-01 → IMP-02 → IMP-03 → IMP-04 → IMP-05/06 → IMP-07 (fast root-cause fixes first). IMP-01 and IMP-03 are the two cheap experiments that confirm/refute the direction + EOV hypotheses before investing in IMP-02's supervised model.

### 8.3 Acoustic-emission data: verified catalog (21/21 candidates checked, 2026-08-16)

**The reality that shapes this:** exactly **one** open dataset of AE on a real in-situ bridge exists. Public full-bridge AE *recordings* essentially don't exist — the practical ladder is Tier A (the one bridge dataset) → Tier B (lab fatigue/bolt proxies, raw waveforms) → Tier C (request-access) → own acquisition.

**Tier A — real bridge AE (open download):**

| Dataset | What it is | AE | Size / license | Access |
|---------|-----------|-----|----------------|--------|
| **Univ. of Trento — "NDT Campaign on a Steel Bridge through AE Sensors and Accelerometers"** (2024) | Full-scale in-situ **steel bowstring girder bridge, 65 m span**, two-cell box girder; AE on a longitudinal weld | **6 AE** (20×20 cm grid) + accelerometers at quarter-spans | 84.6 MB · **CC BY 4.0** | Open, no registration — [builtenvdata.eu/datasets/68](https://experiments.builtenvdata.eu/datasets/68/), DOI 10.60756/unitn-vbua48i539. Caveat: threshold-triggered hit data, not continuous raw waveforms |

**Tier B — lab AE proxies, raw waveforms, open:**

| Dataset | What it is | AE | Size / license | Why it's useful |
|---------|-----------|-----|----------------|-----------------|
| **ORION-AE** — bolt-loosening (Harvard Dataverse) | 2 Al plates / 3 bolts under 100 Hz shaker; 5 campaigns × 7 torque levels 5–60 cNm, ~10 s continuous | 3 AE (Micro-80/F50A/Micro-200HF) + laser vibrometer, **5 MHz** | **~9.3 GB** (not ~1 GB as often claimed) · **CC0** | Directly relevant to bridge bolted connections; raw multi-channel AE with severity labels |
| **Zonzini et al.** — plate impact localization (Zenodo) | 1×1×0.003 m aluminum plate, 9 impact positions + matched ray-trace simulation | 3 AE (experimental), 25 Rx (sim), 2 MHz | 63.9 MB · CC BY 4.0 | Cleanest ML-ready source-localization benchmark — closest plate analog to bridge plates |
| **Vallen openAE pmma-plate** (filetransfer.vallen.de) | PMMA plate; pencil-lead-break / pulser / salt sources | **4 AE**, 2.5 MHz | ~9.5 MB · CC-BY-4.0 *claimed, not verifiable* | Native **Vallen SQLite format** — byte-compatible with a Vallen-equipped bridge system's output; tiny, instant to ingest |
| **Wisner & Yochens** (Zenodo) | Controlled sources (pencil-lead-break + friction), single specimen, multiple locations | 1 AE + 1 laser | 551.6 MB · CC BY 4.0 | Raw waveforms with pre-built Training/Testing split, two modalities |
| **Topolar et al.** (Zenodo) | 3D-printed FRC concrete coupons under direct tension | AE descriptors (RMS/ring count) | 24.9 MB · CC BY 4.0 | Only concrete-AE in the list — material-level signature data |

**Tier C — request-access / documentation (worth one email each):**
- **Univ. of Minnesota / MnDOT — Cedar Avenue fracture-critical bridge** (DRUM 11299/163209): a real fracture-critical bridge monitored with **16 AE sensors**, but only the 5 MB PDF *report* is public; raw data isn't. Contacting the report authors is the single best real-bridge-AE request you can make.
- **UCSB plate-depth** (github.com/ntulshibagwale/plate-depth-classification): strong ML-ready raw waveforms (2 AE ch, 10 MHz, balanced 3-class) but **no license** — must email the author.

**Flags that save time:**
- **Z24, LTBP InfoBridge, and openLAB (TU Dresden) all have ZERO AE channels** — do not chase them for AE.
- **ES-Data portal is dead** (NXDOMAIN) — remove from any ingestion plan.
- **PHM2010's official CDN links are dead** — the Kaggle mirror `rabahba/phm-data-challenge-2010` works (CC0).
- Bearing-fault-AE (Kaggle, ~57 GB) is **STFT spectrograms**, not raw time series; Faran (Technion) is **feature-level spectral densities** with no waveforms; "Multimodal Concrete Crack" is **microphone audio**, not AE.

### 8.4 Strategic read & decision

- **What AE adds that vibration/strain cannot:** it detects *active* damage — crack growth / micro-cracking emits elastic stress waves that change global stiffness negligibly, so they're invisible to modal/RMS indices until damage has accumulated; it's **local** and localizable by time-of-arrival triangulation ("where is it failing", not just "is it"); it catches **initiation**, complementing NEW-05's conclusion that strain/DE is the class that catches the *rupture event itself*.
- **Honest limits:** passive (silent when damage isn't propagating), range-limited by attenuation (sensor density required), sensitive to rain/traffic (robust hit detection + clustering), and a qualitative activity measure — not residual capacity; needs supervised signal-feature→damage-mode classification.
- **Deployment path:** Tier A = real-bridge proof on the hero pipeline; Tier B = train source-localization / detection models; Tier C (UMN request) = real fracture-critical AE; then own acquisition — AE sensors are cheap, the DAQ/conditioning is the cost (~$3–8k for a 2–4 ch Vallen/PAC starter).
- **Engineering enabler (unchanged):** AE integration is blocked at the same frozen contract/recorder/fusion layers as strain (ARCH-09) — a generic telemetry envelope is the prerequisite. Build AE as an honest channel stub / roadmap item now; the real lane waits on data + the envelope.

---

## Appendix · Method & provenance

- **Workflow:** 6 subsystem mappers → 10 analysis lenses (STRATEGIC, BUGS, SECURITY, PERFORMANCE, CODEQUALITY, ARCHITECTURE, ENHANCEMENTS, ADVANCED, NEWADDITIONS, TESTING) → 5 adversarial verifiers → 1 synthesis critic. 86 findings total, all schema-structured with severity/priority/effort/timeline/deps/evidence/description/recommendation.
- **Ground truth used:** shipped state at `303f776`, incl. the 2026-08-15 non-degenerate retrain (ensemble ACTIVE), gate-16 de-confounding, geo fix, and the honest-findings ledger. Live demo arc BHI 87.1→67.5→33.6 was not perturbed by any of this work.
- **Honesty rule upheld throughout:** every number is as-measured or as-reproduced; the one downgrade (PERF-02) is documented with the exact config that reproduces the claim; the "demo-scale trained inertness" statements in `vault/05-Demo/Deconfounding-Study.md` are correct and were explicitly preserved.
