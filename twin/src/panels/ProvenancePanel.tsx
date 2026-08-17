import { memo } from 'react'
import { useStore } from '../store'
import type { ChannelProvenance } from '../store'

// --- data-source label / color mapping -------------------------------------
const SOURCE_META: Record<string, { label: string; cls: string }> = {
  'z24-replay': { label: 'real Z24 benchmark replay', cls: 'src-real' },
  synthetic: { label: 'modeled synthetic', cls: 'src-synthetic' },
  'live-demo': { label: 'third-party live feed', cls: 'src-live' },
  offline: { label: 'replay fixtures (backend unreachable)', cls: 'src-offline' },
}

const sourceCls = (ds: string) => SOURCE_META[ds]?.cls ?? 'src-offline'

const realLabel = (c: ChannelProvenance) =>
  c.real ? 'real replay' : 'modeled'

/**
 * D1-6 provenance panel — the honest "what am I actually looking at?" reader.
 * Renders the D1-5 data-realism manifest from the backend: the digital-shadow /
 * one-way-data label, the per-channel real-vs-modeled breakdown, the honesty
 * note, and the live-feed / simulated-clock provenance lines.  All text comes
 * from the backend manifest or the stiffness overlay — never invented here.
 *
 * HONESTY GATE (ROADMAP line 46): when the WS bridge is down but REST is up
 * (backend starting, or WS bound to a busy port), the manifest poller still
 * reports a real data source while the panels stream OFFLINE fixtures.  We
 * surface the combined label — "REPLAY fixtures · backend WS offline" — and
 * demote the manifest's real-source claim to a "resumes on reconnect" note
 * instead of letting the two contradict each other on screen.
 */
export const ProvenancePanel = memo(function ProvenancePanel() {
  const manifest = useStore((s) => s.manifest)
  const stiffness = useStore((s) => s.stiffness)
  const seeded = useStore((s) => s.seededDefect)
  const wsStatus = useStore((s) => s.wsStatus)
  // NEW-02: the site-temperature block rides the manifest (D1-5) — same source
  // of truth the panel reads for every other provenance claim.
  const siteTemp = manifest.siteTemperature

  // Line 85: defensive guard — never trust the wire shape. The manifest poller
  // always sends an array, but a foreign/older backend could omit the field.
  const channels = manifest.channels ?? []
  const realCount = channels.filter((c) => c.real).length
  const modeledCount = channels.length - realCount
  const seededActive = seeded.label && seeded.label !== 'none'
  // Line 85: prefer the backend's own data_source_label (richer, canonical text
  // straight from the manifest — e.g. "procedural synthetic (dev fallback — no
  // real data)") over the local SOURCE_META copy; fall back only when the
  // backend label is empty (the offline default).
  const manifestLabel =
    manifest.dataSourceLabel ||
    (SOURCE_META[manifest.dataSource]?.label ?? manifest.dataSource)
  // Line 46: WS down + REST up → stream is fixtures while the manifest claims a
  // real source. 'offline' is the manifest's own honest default (backend fully
  // down), which already agrees with the REPLAY badge — no extra label needed.
  const replaying = wsStatus === 'replay'
  const manifestClaimsSource = manifest.dataSource !== 'offline'

  return (
    <section className="panel">
      <header className="panel-title">Data Provenance · D1-5</header>

      <div className="shadow-chip">
        <span className="shadow-chip-dot" />
        <div>
          <div className="shadow-chip-title">DIGITAL SHADOW</div>
          <div className="shadow-chip-sub">one-way data · model never commands the bridge</div>
        </div>
      </div>

      <div className="src-line">
        {replaying && manifestClaimsSource ? (
          <>
            <span className="source-dot src-offline" />
            <span className="src-label">REPLAY fixtures · backend WS offline</span>
          </>
        ) : (
          <>
            <span className={`source-dot ${sourceCls(manifest.dataSource)}`} />
            <span className="src-label">{manifestLabel}</span>
          </>
        )}
        {channels.length > 0 && !(replaying && manifestClaimsSource) && (
          <span className="src-count">
            {realCount} real · {modeledCount} modeled
          </span>
        )}
      </div>

      {replaying && manifestClaimsSource && (
        <div className="honesty-note">
          Backend REST is up (manifest reports {manifestLabel}) but
          the live WebSocket is offline — the stream you are watching is fixture
          replay. The manifest source applies once the live WS reconnects.
        </div>
      )}

      {channels.length > 0 && (
        <div className="chan-block">
          <div className="block-title">Per-channel source</div>
          {channels.map((c) => (
            <div className="chan-line" key={c.node}>
              <span className={`source-dot ${c.real ? 'src-real' : 'src-synthetic'}`} />
              <span className="chan-node">node {c.node}</span>
              <span className="chan-sensor">{c.sensor}</span>
              <span className={`chan-kind ${c.real ? 'real' : 'modeled'}`}>
                {realLabel(c)}
              </span>
            </div>
          ))}
        </div>
      )}

      {manifest.honestyNote && (
        <div className="honesty-note">“{manifest.honestyNote}”</div>
      )}

      {manifest.liveFeedActive && (
        <div className="live-feed-line">
          <span className="live-feed-dot" />
          live public-broker feed active · bridge={manifest.liveFeedBridge} ·
          never fused into Z24 BHI
        </div>
      )}

      {stiffness.simClock && (
        <div className="clock-line">
          <span className="meta-key">sim clock</span>
          <span className="meta-val">{stiffness.simClock}</span>
          {stiffness.tempC !== undefined && (
            <>
              <span className="meta-key">· sim T</span>
              <span className="meta-val">{stiffness.tempC.toFixed(1)}°C</span>
              <span className="meta-unit">(modeled)</span>
            </>
          )}
        </div>
      )}
      {/* NEW-02: real site air temperature — the source chip flips so no surface
          shows 'measured' when the probe fell back to the simulated model.  The
          label text comes straight from the backend manifest, never invented. */}
      {siteTemp?.tempC !== undefined && siteTemp.sourceLabel && (
        <div className="site-temp-line">
          <span className="meta-key">site temp</span>
          <span className="meta-val">{siteTemp.tempC.toFixed(1)}°C</span>
          <span className={`site-temp-src ${siteTemp.source === 'open-meteo' ? 'measured' : 'modeled'}`}>
            {siteTemp.source === 'open-meteo' ? 'measured' : 'modeled'}
          </span>
          <span className="meta-unit">{siteTemp.sourceLabel}</span>
        </div>
      )}
      {stiffness.residualInterpretation && (
        <div className="thermal-note">{stiffness.residualInterpretation}</div>
      )}

      {seededActive && (
        <div className="seeded-block">
          <div className="block-title">Seeded defect · D2-12</div>
          <div className="seeded-line">
            <span className="meta-key">scenario</span>
            <span className="meta-val">{seeded.label}</span>
            {seeded.source && <span className="meta-unit">({seeded.source})</span>}
          </div>
          <div className="seeded-line">
            <span className="meta-key">seeded EI</span>
            <span className="meta-val">main span -{seeded.eiLossPct.toFixed(1)}%</span>
            <span className="meta-unit">per-span {seeded.perSpanLossPct
              .map((v) => `${v.toFixed(1)}%`).join(' / ')}</span>
          </div>
          <div className="seeded-line">
            <span className="meta-key">f1</span>
            <span className="meta-val">{seeded.f1.toFixed(2)} Hz</span>
            <span className="meta-unit">drift {seeded.f1DriftPct.toFixed(1)}% vs {seeded.f1Ref.toFixed(2)} Hz</span>
          </div>
          <div className="seeded-note">{seeded.note}</div>
        </div>
      )}
    </section>
  )
})
