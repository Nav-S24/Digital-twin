// src/components/VehicleSelector.jsx
import { useState, useEffect } from 'react'
import { fetchVehicleIds } from '../utils/api'
import { Search, ChevronDown } from 'lucide-react'

export default function VehicleSelector({ value, onChange }) {
  const [ids,      setIds]      = useState([])
  const [query,    setQuery]    = useState('')
  const [open,     setOpen]     = useState(false)

  useEffect(() => {
    fetchVehicleIds()
      .then(d => setIds(d.vehicle_ids || []))
      .catch(() => {})
  }, [])

  const filtered = ids.filter(id =>
    id.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 50)

  return (
    <div style={{ position: 'relative', minWidth: 200 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-md)',
          padding: '0.5rem 0.875rem',
          color: 'var(--text-primary)',
          cursor: 'pointer',
          fontSize: 13.5,
          fontFamily: 'var(--font-mono)',
          width: '100%',
          justifyContent: 'space-between',
        }}
      >
        <span>{value || 'Select vehicle…'}</span>
        <ChevronDown size={14} color="var(--text-muted)" />
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-accent)',
          borderRadius: 'var(--radius-md)',
          zIndex: 999,
          boxShadow: 'var(--shadow-card)',
          overflow: 'hidden',
        }}>
          {/* Search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--border-subtle)' }}>
            <Search size={13} color="var(--text-muted)" />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search ID…"
              style={{
                background: 'transparent', border: 'none', outline: 'none',
                color: 'var(--text-primary)', fontSize: 13, width: '100%',
                fontFamily: 'var(--font-mono)',
              }}
            />
          </div>
          {/* List */}
          <div style={{ maxHeight: 220, overflowY: 'auto' }}>
            {filtered.map(id => (
              <button
                key={id}
                onClick={() => { onChange(id); setOpen(false); setQuery('') }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '0.45rem 0.875rem',
                  background: id === value ? 'var(--accent-glow)' : 'transparent',
                  color: id === value ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  border: 'none', cursor: 'pointer',
                  fontSize: 12.5, fontFamily: 'var(--font-mono)',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (id !== value) e.target.style.background = 'var(--bg-hover)' }}
                onMouseLeave={e => { if (id !== value) e.target.style.background = 'transparent' }}
              >
                {id}
              </button>
            ))}
            {filtered.length === 0 && (
              <div style={{ padding: '0.75rem', color: 'var(--text-muted)', fontSize: 12, textAlign: 'center' }}>
                No results
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
