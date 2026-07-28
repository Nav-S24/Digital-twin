// src/components/Sidebar.jsx
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Cpu, AlertTriangle, TrendingUp,
  Activity, Car, RefreshCw, Zap
} from 'lucide-react'

const NAV = [
  { to: '/',           icon: LayoutDashboard, label: 'Overview' },
  { to: '/components', icon: Cpu,             label: 'Components' },
  { to: '/failure',    icon: AlertTriangle,   label: 'Failure Risk' },
  { to: '/simulation', icon: TrendingUp,      label: 'Simulation' },
  { to: '/history',    icon: Activity,        label: 'History' },
  { to: '/twin',       icon: Car,             label: 'Digital Twin' },
  { to: '/fleet',      icon: Zap,             label: 'Fleet' },
]

export default function Sidebar({ vehicleId }) {
  return (
    <aside style={{
      width: 220,
      minHeight: '100vh',
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      padding: '1.5rem 0',
      position: 'sticky',
      top: 0,
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '0 1.25rem 1.5rem', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, flexShrink: 0,
          }}>🚗</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.2 }}>
              Digital Twin
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Vehicle Health
            </div>
          </div>
        </div>
      </div>

      {/* Vehicle ID tag */}
      {vehicleId && (
        <div style={{ padding: '0.75rem 1.25rem', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Active Vehicle
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent-primary)', fontWeight: 600 }}>
            {vehicleId}
          </div>
        </div>
      )}

      {/* Nav */}
      <nav style={{ flex: 1, padding: '0.75rem 0.75rem', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '0.55rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: 13.5,
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
              background: isActive ? 'var(--accent-glow)' : 'transparent',
              border: isActive ? '1px solid var(--border-accent)' : '1px solid transparent',
              textDecoration: 'none',
              transition: 'all 0.15s',
            })}
          >
            <Icon size={16} strokeWidth={isActive => isActive ? 2.5 : 1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Phase 4 · Digital Twin
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
          Powered by Tata iRA / TETHER
        </div>
      </div>
    </aside>
  )
}
