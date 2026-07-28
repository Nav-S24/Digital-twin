// src/components/GaugeChart.jsx
import { healthColor, healthLabel } from '../utils/helpers'

const SIZE   = 180
const STROKE = 16
const R      = (SIZE - STROKE) / 2
const CIRC   = 2 * Math.PI * R
// We use 75% of the circle (270°)
const ARC    = CIRC * 0.75

export default function GaugeChart({ score = 0, label = '', size = SIZE }) {
  const scale      = size / SIZE
  const pct        = Math.min(100, Math.max(0, score)) / 100
  const arcLen     = ARC * pct
  const color      = healthColor(score)
  const cx         = size / 2
  const cy         = size / 2
  const r          = (size - STROKE * scale) / 2
  const circ       = 2 * Math.PI * r
  const arc        = circ * 0.75
  const fill       = arc * pct
  const gapStart   = circ * 0.625  // start of visible arc (135° offset)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
        style={{ transform: 'rotate(135deg)' }}>
        {/* Background arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={STROKE * scale}
          strokeDasharray={`${arc} ${circ - arc}`}
          strokeDashoffset={0}
          strokeLinecap="round"
        />
        {/* Value arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={color}
          strokeWidth={STROKE * scale}
          strokeDasharray={`${fill} ${circ - fill}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          style={{
            transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1), stroke 0.5s',
            filter: `drop-shadow(0 0 6px ${color}88)`
          }}
        />
      </svg>
      {/* Centre label */}
      <div style={{
        position: 'absolute',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        pointerEvents: 'none',
        marginTop: -(size * 0.52),
      }}>
        <span style={{ fontSize: size * 0.18, fontWeight: 700, color, lineHeight: 1 }}>
          {score.toFixed(0)}
        </span>
        <span style={{ fontSize: size * 0.09, color: 'var(--text-muted)', marginTop: 2 }}>
          {healthLabel(score)}
        </span>
      </div>
      {label && (
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500, marginTop: -size * 0.3 }}>
          {label}
        </span>
      )}
    </div>
  )
}
