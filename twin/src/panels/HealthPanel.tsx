import { memo, useMemo } from 'react'
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useStore, BHI_W, WINDOW_N, WINDOW_S } from '../store'
import type { HealthState } from '../store'
import { BHI_AMBER, BHI_GREEN } from '../store'

// --- BHI gauge (SVG arc, 0-100, color bands) -------------------------------
function polar(cx: number, cy: number, r: number, angleDeg: number): [number, number] {
  const rad = (angleDeg * Math.PI) / 180
  return [cx + r * Math.sin(rad), cy - r * Math.cos(rad)]
}

function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const [x0, y0] = polar(cx, cy, r, a0)
  const [x1, y1] = polar(cx, cy, r, a1)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}

const angleOf = (value: number) => -120 + (value / 100) * 240
const CX = 80
const CY = 80
const R = 60

function Gauge({ value, u, state }: { value: number; u: number; state: HealthState }) {
  const needle = angleOf(Math.max(0, Math.min(100, value)))
  const [nx, ny] = polar(CX, CY, R - 8, needle)
  const lo = angleOf(Math.max(0, value - u))
  const hi = angleOf(Math.min(100, value + u))
  const stateColor =
    state === 'GREEN' ? 'var(--green)' : state === 'AMBER' ? 'var(--amber)' : 'var(--red)'

  return (
    <svg viewBox="0 0 160 152" className="gauge">
      <circle cx={CX} cy={CY} r={R} fill="none" stroke="var(--grid)" strokeWidth={13} />
      <path d={arcPath(CX, CY, R, -120, 0)} fill="none" stroke="var(--red)" strokeWidth={13} strokeLinecap="butt" />
      <path d={arcPath(CX, CY, R, 0, angleOf(70))} fill="none" stroke="var(--amber)" strokeWidth={13} strokeLinecap="butt" />
      <path d={arcPath(CX, CY, R, angleOf(70), 120)} fill="none" stroke="var(--green)" strokeWidth={13} strokeLinecap="butt" />
      <path d={arcPath(CX, CY, R - 9, -120, 120)} fill="none" stroke="#00000022" strokeWidth={1} />
      {u > 0 && (
        <path d={arcPath(CX, CY, R + 10, lo, hi)} fill="none" stroke="var(--accent)" strokeWidth={4} strokeOpacity={0.55} strokeLinecap="round" />
      )}
      <line x1={CX} y1={CY} x2={nx} y2={ny} stroke="var(--text)" strokeWidth={2.5} strokeLinecap="round" />
      <circle cx={CX} cy={CY} r={4.5} fill="var(--text)" />
      <text x={CX} y={CY - 6} textAnchor="middle" className="gauge-value">{value.toFixed(1)}</text>
      <text x={CX} y={CY + 14} textAnchor="middle" className="gauge-u">±{u.toFixed(1)}</text>
      <text x={CX} y={CY + 42} textAnchor="middle" className="gauge-state" fill={stateColor}>{state}</text>
    </svg>
  )
}

function SubBar({ label, value, weight }: { label: string; value: number; weight: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  const cls = value <= 0.3 ? 'ok' : value <= 0.6 ? 'warn' : 'bad'
  return (
    <div className="subbar">
      <div className="subbar-head">
        <span className="subbar-label">{label}</span>
        <span className="subbar-meta">w={weight}</span>
        <span className="subbar-val">{value.toFixed(2)}</span>
      </div>
      <div className="subbar-track">
        <div className={`subbar-fill ${cls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/**
 * Health panel: BHI gauge (SVG arc with color bands + uncertainty band),
 * cv/vib/load sub-index bars, and a Recharts BHI trend.
 */
export const HealthPanel = memo(function HealthPanel() {
  const live = useStore((s) => s.live)
  const bhiTrend = useStore((s) => s.bhiTrend)

  // D2-9: uncertainty envelope on the trend — the current measurement
  // uncertainty u (±) is drawn as a band around every point, honestly labeled.
  const trendData = useMemo(
    () =>
      bhiTrend.slice(-60).map((v, i) => ({
        i,
        v,
        lo: Math.max(0, v - live.u),
        hi: Math.min(100, v + live.u),
      })),
    [bhiTrend, live.u],
  )

  return (
    <section className="panel">
      <header className="panel-title">Bridge Health · Z24</header>
      <div className="gauge-row">
        <Gauge value={live.bhi} u={live.u} state={live.state} />
        <div className="gauge-meta">
          <div className="meta-line">
            <span className="meta-key">RMS</span>
            <span className="meta-val">{live.rms.toFixed(3)}</span>
            <span className="meta-unit">m/s²</span>
          </div>
          <div className="meta-line">
            <span className="meta-key">f0</span>
            <span className="meta-val">{live.freq.toFixed(1)}</span>
            <span className="meta-unit">Hz</span>
          </div>
          <div className="meta-line">
            <span className="meta-key">window</span>
            <span className="meta-val">{WINDOW_S}</span>
            <span className="meta-unit">s · {WINDOW_N}</span>
          </div>
        </div>
      </div>

      <div className="subbar-block">
        <div className="block-title">Sub-indices (higher = worse)</div>
        <SubBar label="cv · vision" value={live.cv} weight={BHI_W.cv.toFixed(2)} />
        <SubBar label="vib · vibration" value={live.vib} weight={BHI_W.vib.toFixed(2)} />
        {/* ROADMAP line 68: transparently credit whichever detector carries the
            vibration evidence — deterministic spectral floor vs trained ensemble. */}
        {live.vibEvidence && (
          <div className="vib-evidence" title="Floor = always-on spectral heuristic; trained = ML ensemble push (envelope-relative)">
            <span className="vib-evidence-key">vib source</span>
            <span className="vib-evidence-detail">
              floor {live.vibEvidence.floor.toFixed(2)}
              {live.vibEvidence.trained_push > 0
                ? ` + trained ${live.vibEvidence.trained_push.toFixed(2)}`
                : ' · trained 0.00 (inert)'}
            </span>
          </div>
        )}
        <SubBar label="load · traffic" value={live.load} weight={BHI_W.load.toFixed(2)} />
      </div>

      <div className="trend-block">
        <div className="block-title">BHI trend · last {trendData.length} (shaded = ±u)</div>
        {trendData.length > 1 ? (
          <ResponsiveContainer width="100%" height={110}>
            <AreaChart data={trendData} margin={{ top: 6, right: 2, left: 2, bottom: 0 }}>
              <defs>
                <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="uncBandGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis dataKey="i" hide />
              <YAxis domain={[0, 100]} hide />
              <Tooltip
                contentStyle={{ background: 'var(--panel)', border: '1px solid var(--border)', fontSize: 11 }}
                labelStyle={{ color: 'var(--muted)' }}
                formatter={(value) => [Number(value ?? 0).toFixed(1), 'BHI']}
              />
              <ReferenceLine y={BHI_GREEN} stroke="var(--green)" strokeDasharray="4 3" strokeOpacity={0.5} />
              <ReferenceLine y={BHI_AMBER} stroke="var(--amber)" strokeDasharray="4 3" strokeOpacity={0.5} />
              {/* uncertainty band (±u) behind the trend line */}
              <Area
                type="monotone"
                dataKey="hi"
                stroke="none"
                fill="url(#uncBandGrad)"
                dot={false}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="lo"
                stroke="none"
                fill="var(--panel)"
                dot={false}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke="var(--accent)"
                strokeWidth={1.5}
                fill="url(#trendGrad)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="chart-empty">collecting trend…</div>
        )}
      </div>
    </section>
  )
})
