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

const sourceLabel = (ds: string) => SOURCE_META[ds]?.label ?? ds
const sourceCls = (ds: string) => SOURCE_META[ds]?.cls ?? 'src-offline'

const realLabel = (c: ChannelProvenance) =>
  c.real ? 'real replay' : 'modeled'

/**
 * D1-6 provenance panel — the honest "what am I actually looking at?" reader.
 * Renders the D1-5 data-realism manifest from the backend: the digital-shadow /
 * one-way-data label, the per-channel real-vs-modeled breakdown, the honesty
 * note, and the live-feed / simulated-clock provenance lines.  All text comes
 * from the backend manifest or the stiffness overlay — never invented here.
 */
export const ProvenancePanel = memo(function ProvenancePanel() {
  const manifest = useStore((s) => s.manifest)
  const stiffness = useStore((s) => s.stiffness)
  const seeded = useStore((s) => s.seededDefect)

  const realCount = manifest.channels.filter((c) => c.real).length
  const modeledCount = manifest.channels.length - realCount
  const seededActive = seeded.label && seeded.label !== 'none'

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
        <span className={`source-dot ${sourceCls(manifest.dataSource)}`} />
        <span className="src-label">{sourceLabel(manifest.dataSource)}</span>
        {manifest.channels.length > 0 && (
          <span className="src-count">
            {realCount} real · {modeledCount} modeled
          </span>
        )}
      </div>

      {manifest.channels.length > 0 && (
        <div className="chan-block">
          <div className="block-title">Per-channel source</div>
          {manifest.channels.map((c) => (
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
