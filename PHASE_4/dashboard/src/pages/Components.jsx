// src/pages/Components.jsx
import { useComponents } from '../hooks/useTwin'
import GaugeChart from '../components/GaugeChart'
import { healthColor, healthLabel, formatPct, badgeClass, componentIcon } from '../utils/helpers'

function ComponentCard({ name, data }) {
  if (!data) return null
  const icon    = componentIcon(name)
  const color   = healthColor(data.health_score)
  const label   = healthLabel(data.health_score)

  // Build metric rows specific to each component
  const metrics = buildMetrics(name, data)

  return (
    <div className="card fade-in" style={{
      display: 'flex', flexDirection: 'column', gap: '1rem',
      borderColor: `${color}33`,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 22 }}>{icon}</span>
          <div>
            <h3 style={{ textTransform: 'capitalize', marginBottom: 0 }}>{name} System</h3>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Digital Twin Component</span>
          </div>
        </div>
        <span className={badgeClass(label)}>{label}</span>
      </div>

      {/* Gauge + metrics */}
      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <GaugeChart score={data.health_score} size={130} />
          <div style={{
            position: 'absolute', top: '36%', left: 0, right: 0,
            textAlign: 'center', pointerEvents: 'none',
          }}>
            <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1 }}>
              {data.health_score.toFixed(0)}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{label}</div>
          </div>
        </div>

        {/* Metrics grid */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem' }}>
          {metrics.map(({ key, label: mLabel, value, color: mColor }) => (
            <div key={key} style={{
              background: 'var(--bg-surface)', borderRadius: 8,
              padding: '0.5rem 0.75rem',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {mLabel}
              </div>
              <div style={{ fontSize: 15, fontWeight: 600, color: mColor || 'var(--text-primary)', marginTop: 2 }}>
                {value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Failure risk bar */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          <span>Failure Risk</span>
          <span style={{ color: data.failure_probability > 0.3 ? 'var(--health-critical)' : 'var(--health-good)' }}>
            {(data.failure_probability * 100).toFixed(1)}%
          </span>
        </div>
        <div style={{ height: 5, background: 'var(--bg-surface)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${(data.failure_probability * 100).toFixed(1)}%`,
            background: data.failure_probability > 0.3 ? 'var(--health-critical)' : 'var(--accent-primary)',
            borderRadius: 3,
            transition: 'width 0.8s ease',
          }} />
        </div>
      </div>

      {/* Recommendation */}
      {data.maintenance_recommendation && (
        <div style={{
          fontSize: 12, color: 'var(--text-secondary)',
          padding: '0.5rem 0.75rem',
          background: 'var(--bg-surface)',
          borderRadius: 8,
          borderLeft: `3px solid ${color}`,
        }}>
          {data.maintenance_recommendation}
        </div>
      )}
    </div>
  )
}

function buildMetrics(name, d) {
  switch (name) {
    case 'engine': return [
      { key: 'temp',  label: 'Temperature', value: `${d.temperature?.toFixed(1)}°C` },
      { key: 'rpm',   label: 'RPM',         value: d.rpm?.toFixed(0) },
      { key: 'press', label: 'Pressure',    value: `${d.pressure?.toFixed(1)} bar` },
      { key: 'vib',   label: 'Vibration',   value: `${d.vibration?.toFixed(3)} g` },
      { key: 'rul',   label: 'RUL Cycles',  value: d.remaining_useful_life_cycles, color: 'var(--accent-primary)' },
      { key: 'rulkm', label: 'RUL km',      value: d.remaining_useful_life_km?.toLocaleString(), color: 'var(--accent-primary)' },
    ]
    case 'battery': return [
      { key: 'volt',  label: 'Voltage',    value: `${d.voltage?.toFixed(2)} V` },
      { key: 'curr',  label: 'Current',    value: `${d.current?.toFixed(1)} A` },
      { key: 'temp',  label: 'Temp',       value: `${d.temperature?.toFixed(1)}°C` },
      { key: 'soc',   label: 'SOC',        value: `${d.state_of_charge?.toFixed(1)}%`, color: 'var(--accent-primary)' },
      { key: 'soh',   label: 'SOH',        value: `${d.state_of_health?.toFixed(1)}%`, color: 'var(--accent-primary)' },
      { key: 'rul',   label: 'RUL Cycles', value: d.remaining_useful_life_cycles },
    ]
    case 'fuel': return [
      { key: 'temp',  label: 'Temp Factor',  value: `${d.temperature_contribution?.toFixed(0)}` },
      { key: 'press', label: 'Press Factor', value: `${d.pressure_contribution?.toFixed(0)}` },
      { key: 'rpm',   label: 'RPM Factor',   value: `${d.rpm_contribution?.toFixed(0)}` },
      { key: 'vib',   label: 'Vib Factor',   value: `${d.vibration_contribution?.toFixed(0)}` },
      { key: 'fault', label: 'Fault Factor', value: `${d.fault_contribution?.toFixed(0)}` },
    ]
    case 'brake': return [
      { key: 'mileage', label: 'Est. Mileage',  value: `${d.estimated_mileage_km?.toFixed(0)} km` },
      { key: 'wear',    label: 'Pad Wear',       value: `${d.pad_wear_percentage?.toFixed(1)}%`,
        color: d.pad_wear_percentage > 70 ? 'var(--health-critical)' : 'var(--text-primary)' },
      { key: 'hb',      label: 'Hard Brakes',    value: d.hard_brake_event_count },
    ]
    default: return []
  }
}

export default function Components({ vehicleId }) {
  const { data, loading, error } = useComponents(vehicleId)

  if (loading) return <Loader />
  if (error)   return <Err msg={error} />
  if (!data)   return null

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h2>Component Health</h2>
        <p style={{ marginTop: 2, fontSize: 13 }}>
          Individual Digital Twin status for each vehicle subsystem —{' '}
          <span className="mono" style={{ color: 'var(--accent-primary)' }}>{vehicleId}</span>
        </p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
        {['engine', 'battery', 'fuel', 'brake'].map(name => (
          <ComponentCard key={name} name={name} data={data[name]} />
        ))}
      </div>
    </div>
  )
}

const Loader = () => (
  <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '3rem' }}>Loading components…</div>
)
const Err = ({ msg }) => (
  <div style={{ color: 'var(--health-critical)', padding: '1rem' }}>⚠️ {msg}</div>
)
