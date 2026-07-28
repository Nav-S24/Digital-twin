// src/pages/Simulation.jsx
import { useState } from 'react'
import { useSimulation } from '../hooks/useTwin'
import { healthColor, healthLabel } from '../utils/helpers'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { TrendingDown, Calendar, AlertTriangle } from 'lucide-react'

const HORIZONS = [30, 60, 90, 180, 365]

const LINE_CFG = [
  { key: 'vehicle_health',  label: 'Vehicle',  color: '#00d4ff', width: 2.5 },
  { key: 'engine_health',   label: 'Engine',   color: '#4ade80', width: 1.5 },
  { key: 'battery_health',  label: 'Battery',  color: '#facc15', width: 1.5 },
  { key: 'fuel_health',     label: 'Fuel',     color: '#f97316', width: 1.5 },
  { key: 'brake_health',    label: 'Brake',    color: '#a78bfa', width: 1.5 },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-elevated)', border: '1px solid var(--border-accent)',
      borderRadius: 10, padding: '0.75rem 1rem', fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 6 }}>Day {label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 2 }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 600 }}>{p.value?.toFixed(1)}</span>
        </div>
      ))}
    </div>
  )
}

export default function Simulation({ vehicleId }) {
  const [days, setDays] = useState(90)
  const [triggered, setTriggered] = useState(true)
  const { result, loading, error, run } = useSimulation(
    triggered ? vehicleId : null,
    triggered ? days     : null,
  )

  const handleRun = (d) => {
    setDays(d)
    setTriggered(false)
    setTimeout(() => { run(vehicleId, d) }, 50)
  }

  // Thin trajectory for chart (sample every N days to avoid 365 points)
  const chartData = result?.trajectory
    ? result.trajectory.filter((_, i) => i % Math.max(1, Math.floor(result.trajectory.length / 60)) === 0)
    : []

  const last = result?.trajectory?.at(-1)

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <TrendingDown size={20} color="var(--accent-primary)" />
          <div>
            <h2>Future Degradation Simulation</h2>
            <p style={{ fontSize: 13, marginTop: 2 }}>
              Projected component health — <span className="mono" style={{ color: 'var(--accent-primary)' }}>{vehicleId}</span>
            </p>
          </div>
        </div>

        {/* Horizon selector */}
        <div style={{ display: 'flex', gap: 6 }}>
          {HORIZONS.map(d => (
            <button
              key={d}
              onClick={() => handleRun(d)}
              disabled={loading}
              style={{
                padding: '0.4rem 0.875rem',
                borderRadius: 8,
                border: days === d && result ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                background: days === d && result ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                color: days === d && result ? 'var(--accent-primary)' : 'var(--text-secondary)',
                cursor: loading ? 'wait' : 'pointer',
                fontSize: 13, fontWeight: 500,
                transition: 'all 0.15s',
              }}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Simulation result summary */}
      {result && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.875rem' }}>
          {[
            { label: 'Baseline Health',    value: `${result.baseline_health?.toFixed(1)}`,    color: healthColor(result.baseline_health),  sub: 'at simulation start' },
            { label: `Day ${days} Health`, value: `${last?.vehicle_health?.toFixed(1) ?? '--'}`, color: healthColor(last?.vehicle_health ?? 0), sub: `after ${days} days` },
            { label: 'Projected Fail Day', value: result.projected_failure_day ? `Day ${result.projected_failure_day}` : 'None',
              color: result.projected_failure_day ? 'var(--health-critical)' : 'var(--health-good)', sub: 'health < 40' },
            { label: 'RUL at Horizon',     value: last?.rul_cycles ?? '--', color: 'var(--accent-primary)', sub: 'cycles remaining' },
          ].map(({ label, value, color, sub }) => (
            <div key={label} className="card" style={{ padding: '0.875rem' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>⏳</div>
          Running {days}-day simulation…
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 12, padding: '1rem', color: 'var(--health-critical)' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Main chart */}
      {result && chartData.length > 0 && (
        <div className="card">
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Health Trajectory — All Components
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="var(--border-subtle)"
                label={{ value: 'Days', position: 'insideBottom', offset: -2, fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="var(--border-subtle)" />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
              {/* Warning threshold */}
              <ReferenceLine y={40} stroke="rgba(239,68,68,0.4)" strokeDasharray="4 4"
                label={{ value: 'Critical', position: 'right', fontSize: 10, fill: 'var(--health-critical)' }} />
              <ReferenceLine y={65} stroke="rgba(250,204,21,0.3)" strokeDasharray="4 4"
                label={{ value: 'Warning', position: 'right', fontSize: 10, fill: 'var(--health-warning)' }} />
              {LINE_CFG.map(({ key, label, color, width }) => (
                <Line key={key} type="monotone" dataKey={key} name={label}
                  stroke={color} strokeWidth={width} dot={false}
                  activeDot={{ r: 4, strokeWidth: 0 }} />
              ))}
              {/* Projected failure marker */}
              {result.projected_failure_day && (
                <ReferenceLine x={result.projected_failure_day}
                  stroke="var(--health-critical)" strokeDasharray="6 3"
                  label={{ value: '⚠ Failure', position: 'top', fontSize: 10, fill: 'var(--health-critical)' }} />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Failure probability chart */}
      {result && chartData.length > 0 && (
        <div className="card">
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Failure Probability Trend
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="var(--border-subtle)" />
              <YAxis domain={[0, 1]} tickFormatter={v => `${(v*100).toFixed(0)}%`}
                tick={{ fontSize: 11 }} stroke="var(--border-subtle)" />
              <Tooltip
                formatter={(v) => [`${(v*100).toFixed(2)}%`, 'Failure Prob.']}
                contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-accent)', borderRadius: 8 }} />
              <Line type="monotone" dataKey="failure_probability" name="Failure Prob."
                stroke="var(--health-critical)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Day-by-day table (last 10 days) */}
      {result && result.trajectory.length > 0 && (
        <div className="card">
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            Projected State — Last 10 Days of Horizon
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  {['Day', 'Date', 'Vehicle', 'Engine', 'Battery', 'Fuel', 'Brake', 'Fail%', 'RUL', 'Status'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '0.4rem 0.6rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.trajectory.slice(-10).map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.4rem 0.6rem', fontFamily: 'var(--font-mono)' }}>{row.day}</td>
                    <td style={{ padding: '0.4rem 0.6rem', color: 'var(--text-muted)' }}>{row.date}</td>
                    {['vehicle_health', 'engine_health', 'battery_health', 'fuel_health', 'brake_health'].map(k => (
                      <td key={k} style={{ padding: '0.4rem 0.6rem', color: healthColor(row[k]), fontWeight: 600 }}>
                        {row[k]?.toFixed(1)}
                      </td>
                    ))}
                    <td style={{ padding: '0.4rem 0.6rem', color: row.failure_probability > 0.3 ? 'var(--health-critical)' : 'var(--health-good)' }}>
                      {(row.failure_probability * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: '0.4rem 0.6rem', color: 'var(--accent-primary)' }}>{row.rul_cycles}</td>
                    <td style={{ padding: '0.4rem 0.6rem' }}>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{row.maintenance_status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Idle prompt */}
      {!result && !loading && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
          <Calendar size={32} style={{ margin: '0 auto 12px', color: 'var(--accent-primary)' }} />
          <div style={{ fontSize: 15, marginBottom: 6 }}>Select a simulation horizon above</div>
          <div style={{ fontSize: 12 }}>30 · 60 · 90 · 180 · 365 days</div>
        </div>
      )}
    </div>
  )
}
