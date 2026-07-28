// src/pages/Overview.jsx
import { useVehicleState } from '../hooks/useTwin'
import GaugeChart from '../components/GaugeChart'
import MetricCard from '../components/MetricCard'
import { healthColor, healthLabel, formatPct, badgeClass } from '../utils/helpers'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip
} from 'recharts'

export default function Overview({ vehicleId }) {
  const { data, loading, error } = useVehicleState(vehicleId)

  if (loading) return <PageLoader />
  if (error)   return <ErrorMsg msg={error} />
  if (!data)   return null

  const { engine, battery, fuel, brake } = data

  const radarData = [
    { component: 'Engine',  score: engine?.health_score  ?? 0 },
    { component: 'Battery', score: battery?.health_score ?? 0 },
    { component: 'Fuel',    score: fuel?.health_score    ?? 0 },
    { component: 'Brake',   score: brake?.health_score   ?? 0 },
  ]

  const urgencyColor = {
    CRITICAL: 'var(--health-critical)',
    MEDIUM:   'var(--health-warning)',
    LOW:      'var(--health-good)',
  }[data.urgency] || 'var(--health-good)'

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2>Vehicle Overview</h2>
          <p style={{ marginTop: 2, fontSize: 13 }}>
            Real-time digital twin state for{' '}
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)' }}>{vehicleId}</span>
          </p>
        </div>
        <span className={badgeClass(data.health_class)}>
          {data.health_class}
        </span>
      </div>

      {/* Hero gauges */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '1rem',
      }}>
        {/* Main gauge */}
        <div className="card" style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 8, padding: '2rem',
          background: 'linear-gradient(135deg, var(--bg-card), var(--bg-elevated))',
        }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Overall Vehicle Health
          </div>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <GaugeChart score={data.overall_health} size={200} />
            <div style={{
              position: 'absolute', display: 'flex', flexDirection: 'column',
              alignItems: 'center', marginTop: -10,
            }}>
              <span style={{ fontSize: 40, fontWeight: 800, color: healthColor(data.overall_health), lineHeight: 1 }}>
                {data.overall_health.toFixed(0)}
              </span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
                {healthLabel(data.overall_health)}
              </span>
            </div>
          </div>
        </div>

        {/* Radar */}
        <div className="card">
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Component Health Radar
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="var(--border-subtle)" />
              <PolarAngleAxis dataKey="component" tick={{ fontSize: 11, fill: 'var(--text-secondary)' }} />
              <Radar name="Health" dataKey="score" stroke="var(--accent-primary)"
                fill="var(--accent-primary)" fillOpacity={0.18} strokeWidth={2} />
              <Tooltip
                contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-accent)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--text-primary)' }}
                formatter={(v) => [`${v.toFixed(1)}`, 'Health']}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid-4">
        <MetricCard
          label="Failure Probability"
          value={formatPct(data.overall_failure_probability)}
          color={data.overall_failure_probability > 0.3 ? 'var(--health-critical)' : 'var(--health-good)'}
          icon="⚠️"
        />
        <MetricCard
          label="RUL (Cycles)"
          value={data.overall_rul_cycles}
          sub={`${data.overall_rul_km?.toLocaleString()} km`}
          color="var(--accent-primary)"
          icon="🔁"
        />
        <MetricCard
          label="Trip Readiness"
          value={`${data.trip_readiness?.toFixed(0)}%`}
          color={data.trip_readiness >= 70 ? 'var(--health-good)' : 'var(--health-warning)'}
          icon="🚦"
        />
        <MetricCard
          label="Book Service"
          value={`${data.book_service_within_days}d`}
          color={data.book_service_within_days <= 7 ? 'var(--health-critical)' : 'var(--text-primary)'}
          sub={data.maintenance_priority}
          icon="🔧"
        />
      </div>

      {/* Status cards */}
      <div className="grid-3">
        {/* Urgency */}
        <div className="card" style={{ borderColor: urgencyColor + '44' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Urgency</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: urgencyColor }}>{data.urgency}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{data.recommended_action}</div>
        </div>

        {/* Critical component */}
        <div className="card">
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Critical Component</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--health-warning)', textTransform: 'capitalize' }}>
            {data.critical_component ?? 'None'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Requires attention</div>
        </div>

        {/* ML Health Score */}
        <div className="card">
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>ML Health Score</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: healthColor(data.ml_health_score) }}>
            {data.ml_health_score?.toFixed(1)}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Phase 2 prediction</div>
        </div>
      </div>

      {/* Recommended Action */}
      {data.recommended_action && (
        <div className="card" style={{
          background: 'linear-gradient(135deg, rgba(0,212,255,0.05), rgba(0,102,255,0.05))',
          borderColor: 'var(--border-accent)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            📋 Recommended Action
          </div>
          <p style={{ color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.6 }}>
            {data.recommended_action}
          </p>
        </div>
      )}
    </div>
  )
}

function PageLoader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300, color: 'var(--text-muted)' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>⚙️</div>
        <div>Loading twin state…</div>
      </div>
    </div>
  )
}

function ErrorMsg({ msg }) {
  return (
    <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 12, padding: '1.5rem', color: 'var(--health-critical)' }}>
      ⚠️ {msg}
    </div>
  )
}
