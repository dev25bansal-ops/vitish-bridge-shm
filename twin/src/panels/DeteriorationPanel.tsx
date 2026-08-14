import { memo } from 'react'
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useStore } from '../store'

/** Condition-colour for the current-NBI chip (NBI 0-9, 9 = new). */
function conditionColor(cond: number): string {
  if (cond >= 7) return '#16a34a'
  if (cond >= 5) return '#d97706'
  return '#dc2626'
}

/**
 * D2-11 Markov + Bayesian-updating condition panel.  The projection curve
 * re-anchors on every poll: the live BHI (which the measured crack state
 * moves) re-maps to a current NBI condition, and the LTBP empirical Markov
 * prior fans out a yearly expected / p10-p90 uncertainty band from there.
 * Honest framing: empirical LTBP priors on a small n, labelled — never a
 * certified RUL.
 */
export const DeteriorationPanel = memo(function DeteriorationPanel() {
  const det = useStore((s) => s.deterioration)

  const hasProjection = det.projection.length > 0
  const cond = Math.round(det.currentCondition * 10) / 10
  const condColor = conditionColor(det.currentCondition)
  const nxt = det.nextInspectionYear

  return (
    <section className="panel">
      <header className="panel-title">
        Condition Projection · D2-11
        <span className="panel-sub">Markov + Bayesian updating</span>
      </header>

      <div className="det-row">
        <div className="det-stat">
          <span className="det-label">current BHI</span>
          <span className="det-value">{det.currentBhi.toFixed(1)}</span>
        </div>
        <div className="det-stat">
          <span className="det-label">NBI cond.</span>
          <span className="det-value" style={{ color: condColor }}>
            {cond.toFixed(1)}
          </span>
        </div>
        <div className="det-stat">
          <span className="det-label">next inspect</span>
          <span className="det-value">
            {nxt !== null ? `yr ${nxt}` : '—'}
          </span>
        </div>
      </div>

      {hasProjection ? (
        <div className="det-chart-wrap">
          <ResponsiveContainer
            width="100%"
            height={140}
            initialDimension={{ width: 297, height: 140 }}
          >
            <ComposedChart data={det.projection} margin={{ top: 6, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="detFanGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0d9488" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#0d9488" stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="year"
                type="number"
                domain={[0, 30]}
                ticks={[0, 5, 10, 15, 20, 25, 30]}
                tick={{ fontSize: 10, fill: '#64748b' }}
                tickFormatter={(v) => `y${v}`}
                tickLine={false}
                axisLine={{ stroke: '#cbd5e1' }}
              />
              <YAxis
                domain={[1, 9]}
                reversed
                tick={{ fontSize: 10, fill: '#64748b' }}
                tickLine={false}
                axisLine={false}
                width={24}
              />
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #cbd5e1', fontSize: 11 }}
                labelStyle={{ color: '#64748b' }}
                labelFormatter={(v) => `year ${v}`}
                formatter={(value: unknown, name: unknown) => [
                  Number(value ?? 0).toFixed(1),
                  name === 'expected' ? 'NBI' : String(name),
                ]}
              />
              {/* uncertainty fan (p10-p90) behind the expected line */}
              <Area
                type="monotone"
                dataKey="p90"
                stroke="none"
                fill="url(#detFanGrad)"
                dot={false}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="p10"
                stroke="none"
                fill="#ffffff"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="expected"
                stroke="#0d9488"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="p10"
                stroke="#94a3b8"
                strokeWidth={0.75}
                strokeDasharray="3 3"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="p90"
                stroke="#94a3b8"
                strokeWidth={0.75}
                strokeDasharray="3 3"
                dot={false}
                isAnimationActive={false}
              />
              <ReferenceLine y={4} stroke="#dc2626" strokeDasharray="4 3" strokeOpacity={0.45} />
              {nxt !== null && (
                <ReferenceLine
                  x={nxt}
                  stroke="#d97706"
                  strokeDasharray="4 3"
                  label={{
                    value: `inspect`,
                    position: 'insideTopRight',
                    fontSize: 10,
                    fill: '#d97706',
                  }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
          <div className="det-chart-note">fan = p10–p90 · dashed line = NBI 4 (poor)</div>
        </div>
      ) : (
        <div className="chart-empty">Markov projection not available (backend unreachable)</div>
      )}

      {det.priorsLabel && (
        <div className="honesty-note">
          <strong>priors:</strong> {det.priorsLabel}
        </div>
      )}
      {det.note && <div className="honesty-note">{det.note}</div>}
    </section>
  )
})
