// src/utils/helpers.js

export function healthClass(score) {
  if (score >= 85) return 'excellent'
  if (score >= 65) return 'good'
  if (score >= 40) return 'warning'
  return 'critical'
}

export function healthColor(score) {
  if (score >= 85) return 'var(--health-excellent)'
  if (score >= 65) return 'var(--health-good)'
  if (score >= 40) return 'var(--health-warning)'
  return 'var(--health-critical)'
}

export function healthLabel(score) {
  if (score >= 85) return 'Excellent'
  if (score >= 65) return 'Good'
  if (score >= 40) return 'Warning'
  return 'Critical'
}

export function urgencyColor(urgency) {
  switch (urgency?.toUpperCase()) {
    case 'CRITICAL': return 'var(--health-critical)'
    case 'HIGH':     return 'var(--health-warning)'
    case 'MEDIUM':   return '#f97316'
    default:         return 'var(--health-good)'
  }
}

export function formatPct(val, decimals = 1) {
  return `${(val * 100).toFixed(decimals)}%`
}

export function formatScore(val) {
  return typeof val === 'number' ? val.toFixed(1) : '--'
}

export function badgeClass(label) {
  switch (label?.toLowerCase()) {
    case 'excellent': return 'badge badge-excellent'
    case 'good':      return 'badge badge-good'
    case 'warning':   return 'badge badge-warning'
    case 'critical':  return 'badge badge-critical'
    default:          return 'badge badge-info'
  }
}

export function componentIcon(name) {
  switch (name) {
    case 'engine':  return '⚙️'
    case 'battery': return '🔋'
    case 'fuel':    return '⛽'
    case 'brake':   return '🛑'
    default:        return '📊'
  }
}

export function timeAgo(isoString) {
  if (!isoString) return 'N/A'
  const diff = Date.now() - new Date(isoString).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60)  return `${s}s ago`
  if (s < 3600) return `${Math.floor(s/60)}m ago`
  return `${Math.floor(s/3600)}h ago`
}
