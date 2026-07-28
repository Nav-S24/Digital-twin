// src/pages/Fleet.jsx
import { useState } from 'react'
import { useFleet, useVehicleList } from '../hooks/useTwin'
import { healthColor, healthLabel, badgeClass, urgencyColor } from '../utils/helpers'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts'
import { Zap, RefreshCw } from 'lucide-react'
import { refreshData } from '../utils/api'

const PIE_COLORS = {
  excellent: '#00d4aa',
  good:      '#4ade80',
  warning:   '#facc15',
  critical:  '#ef4444',
}

function FleetPie({ data }) {
  const pieData = [
    { name: 'Excellent', value: data.excellent_count, color: PIE_COLORS.excellent },
    { name: 'Good',      value: data.good_count,      color: PIE_COLORS.good },
    { name: 'Warning',   value: data.warning_count,   color: PIE_COLORS.warning },
    { name: 'Critical',  value: data.critical_count,  color: PIE_COLORS.critical },
  ].filter(d => d.value > 0)

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie data={pieData} cx="50%" cy="50%"
          innerRadius={55} outerRadius={85}
          paddingAngle={3} dataKey="value"
          strokeWidth={0}>
          {pieData.map((entry, i) => (
            <Cell key={i} fill={entry.color}
              style={{ filter: `drop-shadow(0 0 6px ${entry.color}55)` }} />
          ))}
        </Pie>
        <Tooltip
          formatter={(v, name) => [v, name]}
          contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-accent)', borderRadius: 8 }}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

export default function Fleet({ onSelectVehicle }) {
  const { data: fleet, loading: fL, error: fE, reload: reloadFleet } = useFleet()
  const [page,        setPage]        = useState(1)
  const [healthClass, setHealthClass] = useState('')
  const [urgency,     setUrgency]     = useState('')
  const [sortBy,      setSortBy]      = useState('overall_health')
  const [asc,         setAsc]         = useState(true)
  const [refreshing,  setRefreshing]  = useState(false)

  const { data: vehicles, loading: vL, reload: reloadVehicles } = useVehicleList({
    page, perPage: 25, healthClass: healthClass || undefined,
    urgency: urgency || undefined, sortBy, ascending: asc,
  })

  const handleRefresh = async () => {
    setRefreshing(true)
    try { await refreshData() } catch {}
    await Promise.all([reloadFleet(), reloadVehicles()])
    setRefreshing(false)
  }

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Zap size={20} color="var(--accent-primary)" />
          <div>
            <h2>Fleet Overview</h2>
            <p style={{ fontSize: 13, marginTop: 2 }}>All {fleet?.total_vehicles ?? '…'} vehicles</p>
          </div>
        </div>
        <button onClick={handleRefresh} disabled={refreshing}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '0.45rem 0.875rem',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-default)',
            borderRadius: 8, color: 'var(--text-secondary)',
            cursor: refreshing ? 'wait' : 'pointer', fontSize: 12.5,
          }}>
          <RefreshCw size={13} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
          Refresh data
        </button>
      </div>

      {/* Fleet summary cards */}
      {fleet && !fL && (
        <>
          <div className="grid-4">
            {[
              { label: 'Total Vehicles',      value: fleet.total_vehicles,           color: 'var(--accent-primary)' },
              { label: 'Mean Health',          value: `${fleet.mean_overall_health}`, color: healthColor(fleet.mean_overall_health) },
              { label: 'Urgent Service',       value: fleet.urgent_service_count,     color: 'var(--health-critical)' },
              { label: 'Service Within 7d',    value: fleet.service_within_7days,     color: 'var(--health-warning)' },
            ].map(({ label, value, color }) => (
              <div key={label} className="card" style={{ padding: '0.875rem' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 26, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
              </div>
            ))}
          </div>

          {/* Pie + bar */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: '1rem' }}>
            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                Health Class Distribution
              </div>
              <FleetPie data={fleet} />
              <div style={{ display: 'flex', justifyContent: 'center', gap: 12, flexWrap: 'wrap', marginTop: 4 }}>
                {[
                  { label: 'Excellent', count: fleet.excellent_count, color: PIE_COLORS.excellent },
                  { label: 'Good',      count: fleet.good_count,      color: PIE_COLORS.good },
                  { label: 'Warning',   count: fleet.warning_count,   color: PIE_COLORS.warning },
                  { label: 'Critical',  count: fleet.critical_count,  color: PIE_COLORS.critical },
                ].map(({ label, count, color }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
                    <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                    <span style={{ color, fontWeight: 700 }}>{count}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                Fleet Health Breakdown
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={[
                  { name: 'Critical', count: fleet.critical_count,  fill: '#ef4444' },
                  { name: 'Warning',  count: fleet.warning_count,   fill: '#facc15' },
                  { name: 'Good',     count: fleet.good_count,      fill: '#4ade80' },
                  { name: 'Excellent',count: fleet.excellent_count, fill: '#00d4aa' },
                ]} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="var(--border-subtle)" />
                  <YAxis tick={{ fontSize: 11 }} stroke="var(--border-subtle)" />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-accent)', borderRadius: 8 }}
                    formatter={(v) => [v, 'Vehicles']}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {[
                      { fill: '#ef4444' }, { fill: '#facc15' },
                      { fill: '#4ade80' }, { fill: '#00d4aa' },
                    ].map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <FilterSelect label="Health Class" value={healthClass} onChange={setHealthClass}
          options={['', 'Excellent', 'Good', 'Warning', 'Critical']} />
        <FilterSelect label="Urgency" value={urgency} onChange={setUrgency}
          options={['', 'LOW', 'MEDIUM', 'CRITICAL']} />
        <FilterSelect label="Sort By" value={sortBy} onChange={setSortBy}
          options={['overall_health', 'failure_probability', 'book_service_within_days', 'vehicle_id']} />
        <button onClick={() => setAsc(a => !a)}
          style={{ padding: '0.45rem 0.75rem', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 12 }}>
          {asc ? '↑ Asc' : '↓ Desc'}
        </button>
      </div>

      {/* Vehicle table */}
      {vL ? (
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '2rem' }}>Loading vehicles…</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-subtle)' }}>
                  {['Vehicle ID', 'Health', 'Class', 'Fail Prob.', 'RUL Cycles', 'Book Service', 'Urgency', 'Critical', ''].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '0.65rem 0.875rem', color: 'var(--text-muted)', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(vehicles?.items ?? []).map((v) => (
                  <tr key={v.vehicle_id}
                    style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer', transition: 'background 0.1s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    onClick={() => onSelectVehicle?.(v.vehicle_id)}
                  >
                    <td style={{ padding: '0.6rem 0.875rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-primary)' }}>{v.vehicle_id}</td>
                    <td style={{ padding: '0.6rem 0.875rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 50, height: 4, background: 'var(--bg-surface)', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ width: `${v.overall_health}%`, height: '100%', background: healthColor(v.overall_health), borderRadius: 2 }} />
                        </div>
                        <span style={{ color: healthColor(v.overall_health), fontWeight: 600 }}>
                          {v.overall_health?.toFixed(1)}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '0.6rem 0.875rem' }}>
                      <span className={badgeClass(v.health_class)} style={{ fontSize: 10 }}>{v.health_class}</span>
                    </td>
                    <td style={{ padding: '0.6rem 0.875rem', color: v.overall_failure_probability > 0.3 ? 'var(--health-critical)' : 'var(--health-good)' }}>
                      {(v.overall_failure_probability * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: '0.6rem 0.875rem', fontFamily: 'var(--font-mono)' }}>{v.overall_rul_cycles}</td>
                    <td style={{ padding: '0.6rem 0.875rem', color: v.book_service_within_days <= 7 ? 'var(--health-critical)' : 'var(--text-secondary)' }}>
                      {v.book_service_within_days}d
                    </td>
                    <td style={{ padding: '0.6rem 0.875rem', color: urgencyColor(v.urgency), fontWeight: 600 }}>{v.urgency}</td>
                    <td style={{ padding: '0.6rem 0.875rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>{v.critical_component}</td>
                    <td style={{ padding: '0.6rem 0.875rem' }}>
                      <button onClick={(e) => { e.stopPropagation(); onSelectVehicle?.(v.vehicle_id) }}
                        style={{ background: 'var(--accent-glow)', border: '1px solid var(--border-accent)', borderRadius: 6, color: 'var(--accent-primary)', padding: '0.25rem 0.625rem', cursor: 'pointer', fontSize: 11 }}>
                        View →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem 1rem', borderTop: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Page {page} · {vehicles?.total ?? 0} total vehicles
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <PagBtn onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} label="← Prev" />
              <PagBtn onClick={() => setPage(p => p + 1)} disabled={!vehicles || vehicles.items.length < 25} label="Next →" />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      style={{
        background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
        borderRadius: 8, color: 'var(--text-secondary)',
        padding: '0.45rem 0.75rem', fontSize: 12.5, cursor: 'pointer',
      }}>
      {options.map(o => <option key={o} value={o}>{o || label}</option>)}
    </select>
  )
}

function PagBtn({ onClick, disabled, label }) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{
        padding: '0.35rem 0.75rem',
        background: disabled ? 'var(--bg-surface)' : 'var(--bg-elevated)',
        border: '1px solid var(--border-default)',
        borderRadius: 6, color: disabled ? 'var(--text-muted)' : 'var(--text-secondary)',
        cursor: disabled ? 'default' : 'pointer', fontSize: 12,
      }}>
      {label}
    </button>
  )
}
