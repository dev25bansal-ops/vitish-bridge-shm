# VITISH 2026 · PS#99 SHM — hosted public demo (landing + twin + backend).

This is the **hosted-public-demo half** of COMPREHENSIVE-ANALYSIS §7.6 item 20:
a single `run_all.py` process serves the scroll-world landing at `/`, the
digital-twin SPA at `/twin`, and the live API + WebSocket at `/api` + `/ws` —
proxied by Caddy for public HTTPS.

The external step — a hosting account + DNS for `demo.example.com` — is CEO/BD
work (tracked 2026-08-31).  Everything below the DNS line is fully verifiable
on a laptop.

## 1. What serves what

| Path      | Served by                                                        |
|-----------|------------------------------------------------------------------|
| `/`       | `landing/` (scroll-world fly-through on **real Z24 films**)      |
| `/twin`   | `twin/dist/` (built SPA, relative `./assets` URLs)               |
| `/api`    | FastAPI backend (`backend/app/api.py`)                            |
| `/ws`     | WebSocket bridge (origin-checked, SEC-03)                         |
| `/health` | liveness probe                                                    |

The mounts are opt-in no-ops when `twin/dist` / `landing` are absent
(`backend/app/static_serve.py`).

## 2. Secrets (SEC posture)

1. `cp .env.public.example .env.public` and replace both
   `REPLACE_openssl_rand_base64_24` placeholders with
   `openssl rand -base64 24` output.  `.env.public` is git-ignored — never
   commit it.
2. `VITE_API_BASE=/api` + `VITE_WS_URL=wss://demo.example.com/ws` are baked
   into the twin build so a hosted visitor's browser talks to the origin it
   was served from (never 127.0.0.1 = their laptop).
3. Broker secure mode (`VITISH_MQTT_USER/PASS` in `.env.public`) turns on the
   mosquitto password file + `allow_anonymous false` + ACL (SEC-01).  The
   demo route stays token-gated (SEC-02) and CORS/WS origins are pinned
   (SEC-03/SEC-06).

## 3. Build + run (laptop-verifiable, loopback)

```bash
# 1) API + WS + landing + twin under /twin, same origin, SECURE-mode broker
cd D:/SHM_Bridges

# broker secure mode (SEC-01)
set -a; source deploy/hosted-demo/.env.public; set +a
docker compose up -d --build            # mosquitto (auth on) + postgres (localhost)

# origins for the loopback smoke — the WS bridge + CORS accept localhost:8000
export VITISH_WS_ORIGINS=http://localhost:8000
export VITISH_CORS_ORIGINS=http://localhost:8000

cd twin && VITE_API_BASE=/api VITE_WS_URL=ws://localhost:8000/ws npm run build && cd ..

python backend/app/run_all.py           # one process: replay + WS + API + static
```

Open `http://localhost:8000/` — scroll the landing (films scrub on real
evidence; `prefers-reduced-motion` → stills).  Open `http://localhost:8000/twin/`
— the twin reaches `/api` + `/ws` on the same origin (no 127.0.0.1 in the
network tab).  This is the full public mode minus the domain.

Sanity: `python scripts/verify_demo_arc.py` still prints the pinned arc
(BHI 87.1 → 33.6), because the served twin is the same demo.

## 4. Go public (CEO/BD step — 2026-08-31)

1. Provision a host (any VPS / PaaS that runs Docker) and point
   `demo.example.com` A/AAAA at it.
2. `curl https://getcaddy.com | bash -s personal` (or use the PaaS proxy) and
   start Caddy in this directory with the included `Caddyfile`.  Caddy orders
   TLS automatically once DNS resolves; it reverse-proxies the SAME loopback
   backend and upgrades `/ws` transparently.
3. Never publish `.env.public`; rotate the broker/demo secrets on any hint of
   exposure (the demo is state-light — a compromise is contained to the
   read-only broker + replay).

## 5. Honesty (unchanged from the repo)

The landing film is **real measured Z24 benchmark evidence** rendered by
`scripts/render_z24_films.py` (provenance in `landing/assets/manifest.json`);
the twin is a demonstration of the pipeline on the real benchmark — no live
field sensors are claimed (`docs/HONESTY-METHODOLOGY.md`).