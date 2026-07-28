// src/pages/History.jsx
import { useHistory } from '../hooks/useTwin'
import { healthColor } from '../utils/helpers'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Brush
} from 'recharts'
import { Activity } from 'lucide-react'

const CHARTS = [
  {
    title: 'Health Scores Over Time',
    lines: [
      { key: 'engine_health',  label: 'Engine',  color: '#4ade80' },
      { key: 'battery_health', label: 'Battery', color: '#facc15' },
      { key: 'fuel_health',    label: 'Fuel',    color: '#f97316' },
      { key: 'brake_health',   label: 'Brake',   color: '#a78bfa' },
      { key: 'vehicle_health', label: 'Vehicle', color: '#00d4ff', width: 2.5 },
    ],
    yDomain: [0, 100],
    height: 280,
  },
  {
    title: 'Failure Probability',
    lines: [
      { key: 'failure_probability', label: 'Failure Prob.', color: '#ef4444', formatter: v => `${(v*100).toFixed(2)}%` },
    ],
    yDomain: [0, 1],
    yTickFmt: v => `${(v*100).toFixed(0)}%`,
    height: 180,
  },
  {
    title: 'Engine Temperature & RPM',
    lines: [
      { key: 'temperature', label: 'Temp (°C)', color: '#fb923c', yAxisId: 'temp' },
      { key: 'rpm',         label: 'RPM',        color: '#60a5fa', yAxisId: 'rpm' },
    ],
    dual: true,
    height: 200,
  },
  {
    title: 'Battery Voltage',
    lines: [
      { key: 'battery_voltage', label: 'Voltage (V)', color: '#facc15' },
    ],
    yDomain: [11, 14],
    height: 160,
  },
  {
    title: 'Remaining Useful Life (Cycles)',
    lines: [
      { key: 'rul_cycles', label: 'RUL Cycles', color: '#00d4ff' },
    ],
    height: 160,
  },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-elevated)', border: '1px solid var(--border-accent)',
      borderRadius: 10, padding: '0.65rem 0.875rem', fontSize: 11.5, maxWidth: 220,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 5, fontSize: 10 }}>Update #{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 2 }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
            {typeof p.value === 'number'
              ? (p.value < 2 ? `${(p.value * 100).toFixed(2)}%` : p.value.toFixed(2))
              : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}

function TrendChart({ title, lines, yDomain, yTickFmt, height = 200, dual = false, data }) {
  return (
    <div className="card">
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
        {title}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey="idx" tick={{ fontSize: 10 }} stroke="var(--border-subtle)" />
          {dual ? (
            <>
              <YAxis yAxisId="temp" tick={{ fontSize: 10 }} stroke="var(--border-subtle)" />
              <YAxis yAxisId="rpm"  orientation="right" tick={{ fontSize: 10 }} stroke="var(--border-subtle)" />
            </>
          ) : (
            <YAxis domain={yDomain} tickFormatter={yTickFmt}
              tick={{ fontSize: 10 }} stroke="var(--border-subtle)" />
          )}
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 11.5, paddingTop: 4 }} />
          {lines.map(({ key, label, color, width = 1.5, yAxisId }) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              name={label}
              stroke={color}
              strokeWidth={width}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
              yAxisId={yAxisId}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function History({ vehicleId }) {
  const { data, loading, error } = useHistory(vehicleId)

  if (loading) return (
    <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '3rem' }}>
      <Activity size={28} style={{ margin: '0 auto 10px', display: 'block', color: 'var(--accent-primary)' }} />
      Loading historical data…
    </div>
  )
  if (error) return <div style={{ color: 'var(--health-critical)', padding: '1rem' }}>⚠️ {error}</div>

  const items = data?.items ?? []

  if (items.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        <Activity size={32} style={{ margin: '0 auto 12px', color: 'var(--text-muted)' }} />
        <div style={{ fontSize: 15 }}>No history yet</div>
        <div style={{ fontSize: 12, marginTop: 6 }}>
          History accumulates after the twin receives updates.
          The initial snapshot is loaded when the server starts.
        </div>
      </div>
    )
  }

  // Index the history rows for X axis
  const chartData = items.map((row, i) => ({ ...row, idx: i + 1 }))

  const latest = items[items.length - 1]
  const oldest = items[0]
  const delta  = (val) => {
    const first = oldest[val] ?? 0
    const last  = latest[val] ?? 0
    return (last - first).toFixed(1)
  }

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Activity size={20} color="var(--accent-primary)" />
          <div>
            <h2>Historical Trends</h2>
            <p style={{ fontSize: 13, marginTop: 2 }}>
              {items.length} data points —{' '}
              <span className="mono" style={{ color: 'var(--accent-primary)' }}>{vehicleId}</span>
            </p>
          </div>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Tip: charts support zoom via scroll
        </div>
      </div>

      {/* Delta summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.75rem' }}>
        {[
          { label: 'Engine Health Δ',  key: 'engine_health',  color: '#4ade80' },
          { label: 'Battery Health Δ', key: 'battery_health', color: '#facc15' },
          { label: 'Vehicle Health Δ', key: 'vehicle_health', color: '#00d4ff' },
          { label: 'Failure Prob. Δ',  key: 'failure_probability', color: '#ef4444' },
          { label: 'RUL Cycles Δ',     key: 'rul_cycles',    color: '#a78bfa' },
        ].map(({ label, key, color }) => {
          const d = parseFloat(delta(key))
          return (
            <div key={key} className="card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: d >= 0 ? '#4ade80' : '#ef4444', lineHeight: 1 }}>
                {d >= 0 ? '+' : ''}{d}
              </div>
            </div>
          )
        })}
      </div>

      {/* Charts */}
      {CHARTS.map(cfg => (
        <TrendChart key={cfg.title} {...cfg} data={chartData} />
      ))}
    </div>
  )
}
