import { Loader2, WifiOff } from "lucide-react";

/** Shared Recharts styling for light theme */
export const CHART = {
  grid: "#E4E7EC",
  axis: "#98A2B3",
  tooltip: {
    background: "#FFFFFF",
    border: "1px solid #E4E7EC",
    borderRadius: 8,
    fontSize: 12,
    color: "#101828",
  },
  primary: "#2E7DE1",
  danger: "#F04438",
};

export function PageHeader({ eyebrow, title, description }) {
  return (
    <div className="mb-6">
      <p className="eyebrow mb-1.5 text-brand">{eyebrow}</p>
      <h1 className="font-display font-semibold text-2xl text-ink tracking-tight">{title}</h1>
      {description && <p className="text-sm text-ink-muted mt-1.5 max-w-3xl leading-relaxed">{description}</p>}
    </div>
  );
}

export function Card({ children, className = "", title, right }) {
  return (
    <div className={`panel p-5 ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-4 gap-3">
          {title && <h3 className="text-sm font-semibold text-ink">{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatRow({ label, value, mono = true }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-base-border last:border-0 gap-4">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className={`text-sm text-ink text-right ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

export function StatusPill({ level, children }) {
  const styles = {
    good: "bg-good/10 text-good border-good/25",
    warn: "bg-warn/10 text-warn border-warn/25",
    crit: "bg-crit/10 text-crit border-crit/25",
    neutral: "bg-base-inset text-ink-muted border-base-border",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-medium border ${styles[level] || styles.neutral}`}>
      {children}
    </span>
  );
}

export function Skeleton({ className = "" }) {
  return <div className={`animate-pulse rounded-lg bg-base-inset ${className}`} aria-hidden />;
}

export function LoadingSkeleton({ rows = 3 }) {
  return (
    <div className="space-y-3 py-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-full" style={{ width: `${100 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function GaugeSkeleton({ size = 128 }) {
  return (
    <div className="flex flex-col items-center py-2">
      <Skeleton className="rounded-full" style={{ width: size, height: size }} />
      <Skeleton className="h-3 w-20 mt-3" />
    </div>
  );
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-2 text-ink-muted text-sm py-10 justify-center" role="status">
      <Loader2 size={16} className="animate-spin text-accent" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ message = "This service is unreachable right now.", onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 text-center py-10 px-4">
      <div className="w-11 h-11 rounded-full bg-crit/10 flex items-center justify-center">
        <WifiOff size={20} className="text-crit" aria-hidden />
      </div>
      <p className="text-sm font-medium text-ink">Service unavailable</p>
      <p className="text-sm text-ink-muted max-w-sm">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-semibold text-accent hover:text-accent-dim mt-1"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function Button({ children, className = "", variant = "primary", ...props }) {
  const variants = {
    primary: "bg-brand text-white font-medium hover:bg-brand-dark shadow-sm",
    ghost: "border border-base-border text-ink bg-white hover:bg-base-inset",
    accent: "bg-accent text-white font-medium hover:bg-accent-dim shadow-sm",
  };
  return (
    <button
      type="button"
      className={`px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${variants[variant] || variants.primary} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
