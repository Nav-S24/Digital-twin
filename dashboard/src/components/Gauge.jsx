// Gauge.jsx
// Circular instrument-cluster style gauge — the dashboard's signature
// element. Used everywhere a 0-100 score needs to read at a glance the
// way a tachometer or fuel gauge does, tying every phase's page back to
// the same "vehicle instrumentation" visual language.

const TRACK = "#E4E7EC";

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function colorFor(value, invert) {
  const v = invert ? 100 - value : value;
  if (v >= 75) return { stroke: "#12B76A", glow: "#12B76A33", label: "good" };
  if (v >= 50) return { stroke: "#F79009", glow: "#F7900933", label: "warn" };
  return { stroke: "#F04438", glow: "#F0443833", label: "crit" };
}

export default function Gauge({
  value = 0,
  max = 100,
  size = 128,
  label,
  sublabel,
  invert = false, // true for "risk"-style values where LOW is good
  strokeWidth = 10,
}) {
  const pct = clamp(value / max, 0, 1);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  // 270-degree sweep (instrument-cluster style), starting at -225deg
  const sweep = 0.75;
  const dash = circumference * sweep;
  const offset = dash * (1 - pct);
  const { stroke, glow } = colorFor((value / max) * 100, invert);

  return (
    <div className="flex flex-col items-center justify-center" style={{ width: size }}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-[225deg]" aria-hidden>
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke={TRACK} strokeWidth={strokeWidth}
            strokeDasharray={`${dash} ${circumference}`}
            strokeLinecap="round"
          />
          <circle
            cx={size / 2} cy={size / 2} r={radius}
            fill="none" stroke={stroke} strokeWidth={strokeWidth}
            strokeDasharray={`${dash} ${circumference}`}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 4px ${glow})`, transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-display font-semibold text-2xl leading-none text-ink" style={{ color: stroke }}>
            {Number.isFinite(value) ? Math.round(value) : "—"}
          </span>
          {sublabel && <span className="text-[10px] text-ink-faint mt-1 font-mono">{sublabel}</span>}
        </div>
      </div>
      {label && <span className="eyebrow mt-2 text-center normal-case tracking-normal text-ink-muted">{label}</span>}
    </div>
  );
}
