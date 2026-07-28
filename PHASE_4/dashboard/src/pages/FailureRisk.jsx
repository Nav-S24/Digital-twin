// src/pages/FailureRisk.jsx
import { useRisk } from '../hooks/useTwin'
import { useVehicleState } from '../hooks/useTwin'
import { healthColor, urgencyColor, formatPct } from '../utils/helpers'
import { AlertTriangle, Wrench, Clock, Cpu, Zap } from 'lucide-react'

function RiskMeter({ probability }) {
  const pct   = (probability * 100).toFixed(1)
  const color = probability > 0.5 ? 'var(--health-critical)'
              : probability > 0.2 ? 'var(--health-warning)'
              : 'var(--health-good)'
  const rings = [0.25, 0.5, 0.75, 1.0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <svg width={180} height={100} viewBox="0 0 180 100">
        {/* Semicircle track */}
        {rings.map((r, i) => (
          <path key={i}
            d={`M ${10 + i*0} 90 A ${80 - i*0} ${80 - i*0} 0 0 1 ${170 - i*0} 90`}
            fill="none"
            stroke={`rgba(255,255,255,0.04)`}
            strokeWidth={14 - i * 2}
          />
        ))}
        {/* Fill arc */}
        <path
          d={`M 10 90 A 80 80 0 0 1 170 90`}
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth={14}
        />
        <path
          d={`M 10 90 A 80 80 0 0 1 170 90`}
          fill="none"
          stroke={color}
          strokeWidth={14}
          strokeDasharray={`${probability * 251.3} 251.3`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s ease, stroke 0.5s', filter: `drop-shadow(0 0 6px ${color}88)` }}
        />
        {/* Value */}
        <text x="90" y="80" textAnchor="middle" fill={color}
          fontSize="26" fontWeight="800" fontFamily="Inter">
          {pct}%
        </text>
        <text x="90" y="96" textAnchor="middle" fill="var(--text-muted)" fontSize="10">
          FAILURE PROBABILITY
        </text>
      </svg>
      <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-muted)' }}>
        <span>0%</span>
        <span style={{ flex: 1, textAlign: 'center' }}>Risk Level</span>
        <span>100%</span>
      </div>
    </div>
  )
}

export default function FailureRisk({ vehicleId }) {
  const { data: risk,    loading: rL, error: rE } = useRisk(vehicleId)
  const { data: vehicle, loading: vL }            = useVehicleState(vehicleId)

  if (rL || vL) return <div style={{ color: 'var(--text-muted)', padding: '3rem', textAlign: 'center' }}>Loading risk analysis…</div>
  if (rE)       return <div style={{ color: 'var(--health-critical)', padding: '1rem' }}>⚠️ {rE}</div>
  if (!risk)    return null

  const uc = urgencyColor(risk.urgency)

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <AlertTriangle size={20} color="var(--health-warning)" />
        <div>
          <h2>Failure Risk Analysis</h2>
          <p style={{ fontSize: 13, marginTop: 2 }}>
            Phase 3 predictive maintenance output —{' '}
            <span className="mono" style={{ color: 'var(--accent-primary)' }}>{vehicleId}</span>
          </p>
        </div>
      </div>

      {/* Critical alert banner */}
      {risk.urgency === 'CRITICAL' && (
        <div className="card pulse-critical" style={{
          background: 'rgba(239,68,68,0.1)',
          borderColor: 'rgba(239,68,68,0.4)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <AlertTriangle size={22} color="var(--health-critical)" />
          <div>
            <div style={{ fontWeight: 700, color: 'var(--health-critical)' }}>CRITICAL — Immediate Action Required</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{risk.recommended_action}</div>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        {/* Risk meter */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
          <RiskMeter probability={risk.failure_probability} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Risk Level</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: uc }}>{risk.urgency}</div>
          </div>
        </div>

        {/* Risk details */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {[
            { icon: <Cpu size={14}/>,      label: 'Top Risk Sensor',   value: risk.top_risk_sensor     || 'N/A' },
            { icon: <Zap size={14}/>,      label: 'Affected System',   value: risk.affected_system     || 'N/A' },
            { icon: <Wrench size={14}/>,   label: 'Priority',          value: risk.maintenance_priority || 'N/A' },
            { icon: <Clock size={14}/>,    label: 'Book Service',      value: `Within ${risk.book_service_within_days} days` },
          ].map(({ icon, label, value }) => (
            <div key={label} className="card" style={{ padding: '0.875rem', display: 'flex', gap: 12, alignItems: 'center' }}>
              <div style={{ color: 'var(--accent-primary)', flexShrink: 0 }}>{icon}</div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginTop: 2 }}>{value}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* SHAP Explanation */}
      {risk.reason && risk.reason !== 'N/A' && (
        <div className="card" style={{
          background: 'linear-gradient(135deg, rgba(0,102,255,0.06), rgba(0,212,255,0.04))',
          borderColor: 'var(--border-accent)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
            🧠 SHAP Explanation
          </div>
          <p style={{ color: 'var(--text-primary)', fontSize: 13.5, lineHeight: 1.7 }}>
            {risk.reason}
          </p>
          {risk.top_risk_shap_value != null && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              SHAP value: <span className="mono" style={{ color: 'var(--accent-primary)' }}>
                {risk.top_risk_shap_value.toFixed(4)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Recommended Action */}
      <div className="card" style={{ borderLeft: `4px solid ${uc}` }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>
          📋 Recommended Action
        </div>
        <p style={{ color: 'var(--text-primary)', fontSize: 14, lineHeight: 1.6 }}>
          {risk.recommended_action}
        </p>
      </div>
    </div>
  )
}
