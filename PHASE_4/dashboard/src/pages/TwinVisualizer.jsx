// src/pages/TwinVisualizer.jsx
import { useState } from 'react'
import { useVehicleState } from '../hooks/useTwin'
import { healthColor, healthLabel, formatPct } from '../utils/helpers'

/* ─── Colour helper ─────────────────────────────────────────────────── */
function statusColor(score) {
  if (score >= 85) return '#00d4aa'
  if (score >= 65) return '#4ade80'
  if (score >= 40) return '#facc15'
  return '#ef4444'
}

/* ─── Animated node ─────────────────────────────────────────────────── */
function SubsystemNode({ name, score, icon, cx, cy, r = 44, onClick, selected }) {
  const color = statusColor(score)
  const glow  = selected ? `0 0 22px ${color}` : `0 0 10px ${color}55`
  return (
    <g
      onClick={() => onClick(name)}
      style={{ cursor: 'pointer', userSelect: 'none' }}
    >
      {/* Outer ring — animated for critical */}
      {score < 40 && (
        <circle cx={cx} cy={cy} r={r + 10} fill="none"
          stroke={color} strokeWidth={1.5} opacity={0.4}
          style={{ animation: 'ping 1.4s ease-in-out infinite' }}>
          <animate attributeName="r"     from={r+8}  to={r+18} dur="1.4s" repeatCount="indefinite" />
          <animate attributeName="opacity" from={0.5} to={0}    dur="1.4s" repeatCount="indefinite" />
        </circle>
      )}
      {/* Background circle */}
      <circle cx={cx} cy={cy} r={r}
        fill={selected ? `${color}22` : 'rgba(15,22,41,0.9)'}
        stroke={color}
        strokeWidth={selected ? 3 : 2}
        style={{ filter: `drop-shadow(${glow})`, transition: 'all 0.3s' }}
      />
      {/* Progress arc */}
      <circle cx={cx} cy={cy} r={r - 8}
        fill="none"
        stroke={color}
        strokeWidth={4}
        strokeDasharray={`${(score / 100) * 2 * Math.PI * (r - 8)} ${2 * Math.PI * (r - 8)}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`}
        opacity={0.7}
        style={{ transition: 'stroke-dasharray 0.8s ease' }}
      />
      {/* Icon */}
      <text x={cx} y={cy - 4} textAnchor="middle" fontSize={20} dominantBaseline="middle">
        {icon}
      </text>
      {/* Score */}
      <text x={cx} y={cy + 18} textAnchor="middle" fontSize={11} fontWeight={700}
        fill={color} fontFamily="Inter">
        {score.toFixed(0)}
      </text>
      {/* Label */}
      <text x={cx} y={cy + r + 16} textAnchor="middle" fontSize={11}
        fill="var(--text-secondary)" fontFamily="Inter" fontWeight={500}>
        {name.charAt(0).toUpperCase() + name.slice(1)}
      </text>
    </g>
  )
}

/* ─── Connector line ────────────────────────────────────────────────── */
function Connector({ x1, y1, x2, y2, color }) {
  return (
    <line x1={x1} y1={y1} x2={x2} y2={y2}
      stroke={color} strokeWidth={1.5} strokeDasharray="5 3" opacity={0.4}
      style={{ transition: 'stroke 0.4s' }}
    />
  )
}

/* ─── Detail panel ──────────────────────────────────────────────────── */
function DetailPanel({ name, data, onClose }) {
  if (!data) return null
  const color  = statusColor(data.health_score)
  const fields = buildFields(name, data)

  return (
    <div style={{
      position: 'absolute', top: 0, right: 0, width: 300,
      background: 'var(--bg-elevated)',
      border: `1px solid ${color}55`,
      borderRadius: 'var(--radius-lg)',
      padding: '1.25rem',
      boxShadow: `0 8px 32px rgba(0,0,0,0.5), 0 0 20px ${color}22`,
      zIndex: 10,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 20 }}>{componentIcon(name)}</span>
          <div>
            <div style={{ fontWeight: 700, textTransform: 'capitalize', color: 'var(--text-primary)' }}>{name} System</div>
            <div style={{ fontSize: 11, color }}>● {healthLabel(data.health_score)}</div>
          </div>
        </div>
        <button onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>✕</button>
      </div>

      {/* Health bar */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          <span>Health Score</span>
          <span style={{ color }}>{data.health_score.toFixed(1)}</span>
        </div>
        <div style={{ height: 6, background: 'var(--bg-surface)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${data.health_score}%`,
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 3, transition: 'width 0.8s ease',
          }} />
        </div>
      </div>

      {/* Metrics */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {fields.map(({ label, value, mono }) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '0.35rem 0',
            borderBottom: '1px solid var(--border-subtle)',
            fontSize: 12.5,
          }}>
            <span style={{ color: 'var(--text-muted)' }}>{label}</span>
            <span style={{
              color: 'var(--text-primary)', fontWeight: 600,
              fontFamily: mono ? 'var(--font-mono)' : 'inherit',
            }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Recommendation */}
      {data.maintenance_recommendation && (
        <div style={{
          marginTop: 12, padding: '0.65rem 0.75rem',
          background: 'var(--bg-surface)', borderRadius: 8,
          borderLeft: `3px solid ${color}`,
          fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.6,
        }}>
          {data.maintenance_recommendation}
        </div>
      )}
    </div>
  )
}

function componentIcon(n) {
  return { engine: '⚙️', battery: '🔋', fuel: '⛽', brake: '🛑' }[n] || '📊'
}

function buildFields(name, d) {
  const fp = { label: 'Failure Risk', value: `${(d.failure_probability * 100).toFixed(1)}%` }
  switch (name) {
    case 'engine': return [
      { label: 'Temperature', value: `${d.temperature?.toFixed(1)}°C`, mono: true },
      { label: 'RPM',         value: `${d.rpm?.toFixed(0)}`,          mono: true },
      { label: 'Pressure',    value: `${d.pressure?.toFixed(1)} bar`, mono: true },
      { label: 'Vibration',   value: `${d.vibration?.toFixed(3)} g`,  mono: true },
      { label: 'RUL (cycles)',value: d.remaining_useful_life_cycles,   mono: true },
      { label: 'RUL (km)',    value: d.remaining_useful_life_km?.toLocaleString(), mono: true },
      fp,
    ]
    case 'battery': return [
      { label: 'Voltage',   value: `${d.voltage?.toFixed(2)} V`,     mono: true },
      { label: 'Current',   value: `${d.current?.toFixed(1)} A`,     mono: true },
      { label: 'Temp',      value: `${d.temperature?.toFixed(1)}°C`, mono: true },
      { label: 'SOC',       value: `${d.state_of_charge?.toFixed(1)}%` },
      { label: 'SOH',       value: `${d.state_of_health?.toFixed(1)}%` },
      fp,
    ]
    case 'fuel': return [
      { label: 'Temp Factor',     value: d.temperature_contribution?.toFixed(1) },
      { label: 'Pressure Factor', value: d.pressure_contribution?.toFixed(1) },
      { label: 'RPM Factor',      value: d.rpm_contribution?.toFixed(1) },
      { label: 'Vibration Factor',value: d.vibration_contribution?.toFixed(1) },
      { label: 'Fault Factor',    value: d.fault_contribution?.toFixed(1) },
      fp,
    ]
    case 'brake': return [
      { label: 'Pad Wear',    value: `${d.pad_wear_percentage?.toFixed(1)}%` },
      { label: 'Est. Mileage',value: `${d.estimated_mileage_km?.toFixed(0)} km`, mono: true },
      { label: 'Hard Brakes', value: d.hard_brake_event_count },
      fp,
    ]
    default: return []
  }
}

/* ─── SVG vehicle diagram ───────────────────────────────────────────── */
const SVG_W = 600
const SVG_H = 360

// Node positions: [cx, cy]
const NODES = {
  engine:  [300, 155],
  battery: [150, 250],
  fuel:    [450, 250],
  brake:   [300, 300],
}
const CENTER = [300, 180]

/* ─── Main page ─────────────────────────────────────────────────────── */
export default function TwinVisualizer({ vehicleId }) {
  const { data, loading, error } = useVehicleState(vehicleId)
  const [selected, setSelected]  = useState(null)

  if (loading) return <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '3rem' }}>Loading twin…</div>
  if (error)   return <div style={{ color: 'var(--health-critical)', padding: '1rem' }}>⚠️ {error}</div>
  if (!data)   return null

  const comp  = { engine: data.engine, battery: data.battery, fuel: data.fuel, brake: data.brake }
  const selData = selected ? comp[selected] : null

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div>
        <h2>Digital Twin Visualisation</h2>
        <p style={{ fontSize: 13, marginTop: 2 }}>
          Interactive subsystem diagram — click any component for details.{' '}
          <span className="mono" style={{ color: 'var(--accent-primary)' }}>{vehicleId}</span>
        </p>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
        {[
          { label: 'Excellent (85–100)', color: '#00d4aa' },
          { label: 'Good (65–84)',       color: '#4ade80' },
          { label: 'Warning (40–64)',    color: '#facc15' },
          { label: 'Critical (0–39)',    color: '#ef4444' },
        ].map(({ label, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}` }} />
            <span style={{ color: 'var(--text-muted)' }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Diagram + detail */}
      <div className="card" style={{ padding: 0, overflow: 'hidden', position: 'relative' }}>
        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          width="100%"
          style={{ display: 'block', background: 'radial-gradient(ellipse at center, rgba(0,102,255,0.05) 0%, transparent 70%)' }}
        >
          <defs>
            <radialGradient id="bgGrad" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="#0f1629" />
              <stop offset="100%" stopColor="#0a0e1a" />
            </radialGradient>
          </defs>
          <rect width={SVG_W} height={SVG_H} fill="url(#bgGrad)" />

          {/* Vehicle silhouette (simplified) */}
          <g opacity={0.08}>
            <rect x={180} y={140} width={240} height={100} rx={18} fill="#00d4ff" />
            <rect x={210} y={110} width={180} height={55}  rx={12} fill="#00d4ff" />
            <ellipse cx={225} cy={250} rx={28} ry={28} fill="#334" />
            <ellipse cx={375} cy={250} rx={28} ry={28} fill="#334" />
          </g>

          {/* Grid lines for professional look */}
          {[100,160,220,280,340].map(y => (
            <line key={y} x1={0} y1={y} x2={SVG_W} y2={y}
              stroke="rgba(255,255,255,0.03)" strokeWidth={1} />
          ))}
          {[100,200,300,400,500].map(x => (
            <line key={x} x1={x} y1={0} x2={x} y2={SVG_H}
              stroke="rgba(255,255,255,0.03)" strokeWidth={1} />
          ))}

          {/* Connectors: centre vehicle → each component */}
          {Object.entries(NODES).map(([name, [cx, cy]]) => (
            <Connector key={name}
              x1={CENTER[0]} y1={CENTER[1]}
              x2={cx} y2={cy}
              color={statusColor(comp[name]?.health_score ?? 100)}
            />
          ))}

          {/* Centre: overall health */}
          <g>
            <circle cx={CENTER[0]} cy={CENTER[1]} r={58}
              fill="rgba(0,212,255,0.05)"
              stroke={statusColor(data.overall_health)}
              strokeWidth={2}
              style={{ filter: `drop-shadow(0 0 14px ${statusColor(data.overall_health)}55)` }}
            />
            <text x={CENTER[0]} y={CENTER[1] - 14} textAnchor="middle"
              fontSize={30} fontWeight={800} fill={statusColor(data.overall_health)} fontFamily="Inter">
              {data.overall_health.toFixed(0)}
            </text>
            <text x={CENTER[0]} y={CENTER[1] + 8} textAnchor="middle"
              fontSize={10} fill="var(--text-muted)" fontFamily="Inter" letterSpacing={1.5}>
              VEHICLE
            </text>
            <text x={CENTER[0]} y={CENTER[1] + 22} textAnchor="middle"
              fontSize={10} fill="var(--text-muted)" fontFamily="Inter" letterSpacing={1.5}>
              HEALTH
            </text>
          </g>

          {/* Component nodes */}
          {Object.entries(NODES).map(([name, [cx, cy]]) => (
            <SubsystemNode
              key={name}
              name={name}
              score={comp[name]?.health_score ?? 100}
              icon={componentIcon(name)}
              cx={cx} cy={cy}
              onClick={setSelected}
              selected={selected === name}
            />
          ))}

          {/* Urgency label */}
          <text x={SVG_W - 10} y={20} textAnchor="end"
            fontSize={10} fill="var(--text-muted)" fontFamily="Inter">
            Urgency: {data.urgency} · Class: {data.health_class}
          </text>
          <text x={10} y={20} textAnchor="start"
            fontSize={10} fill="var(--text-muted)" fontFamily="Inter">
            Critical: {data.critical_component?.toUpperCase() ?? 'NONE'}
          </text>
        </svg>

        {/* Detail overlay */}
        {selected && selData && (
          <div style={{ position: 'absolute', top: 12, right: 12 }}>
            <DetailPanel name={selected} data={selData} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>

      {/* Quick stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
        {Object.entries(comp).map(([name, d]) => (
          <button
            key={name}
            onClick={() => setSelected(selected === name ? null : name)}
            style={{
              background: selected === name ? `${statusColor(d.health_score)}15` : 'var(--bg-card)',
              border: `1px solid ${selected === name ? statusColor(d.health_score) : 'var(--border-default)'}`,
              borderRadius: 'var(--radius-md)',
              padding: '0.875rem',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 0.2s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 18 }}>{componentIcon(name)}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', textTransform: 'capitalize' }}>{name}</span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, color: statusColor(d.health_score), lineHeight: 1 }}>
              {d.health_score.toFixed(0)}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
              {healthLabel(d.health_score)} · Risk {(d.failure_probability * 100).toFixed(1)}%
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
