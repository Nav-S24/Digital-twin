// src/components/MetricCard.jsx
import { healthColor } from '../utils/helpers'

export default function MetricCard({
  label, value, unit = '', sub, color, icon, trend, small = false
}) {
  const valColor = color || 'var(--text-primary)'
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 500 }}>
          {label}
        </span>
        {icon && <span style={{ fontSize: 16 }}>{icon}</span>}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
        <span style={{ fontSize: small ? 22 : 28, fontWeight: 700, color: valColor, lineHeight: 1 }}>
          {value ?? '--'}
        </span>
        {unit && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{unit}</span>}
      </div>
      {sub && (
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{sub}</span>
      )}
      {trend !== undefined && (
        <div style={{ fontSize: 11, color: trend >= 0 ? 'var(--health-good)' : 'var(--health-critical)' }}>
          {trend >= 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(1)}%
        </div>
      )}
    </div>
  )
}
