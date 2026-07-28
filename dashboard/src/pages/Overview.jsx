import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  HeartPulse, Wrench, Boxes, ScanLine, BookOpen, Map, Gauge as GaugeIcon, ArrowRight,
} from "lucide-react";
import { phase2 } from "../api/client";
import { PageHeader, Card, ErrorState, GaugeSkeleton } from "../components/ui";
import Gauge from "../components/Gauge";

const PHASES = [
  { to: "/health", n: "02", title: "Health Score", desc: "Engine, battery & vehicle health scoring", icon: HeartPulse },
  { to: "/maintenance", n: "03", title: "Predictive Maintenance", desc: "Failure probability & remaining useful life", icon: Wrench },
  { to: "/twin", n: "04", title: "Digital Twin", desc: "Live component simulation & fleet view", icon: Boxes },
  { to: "/obd", n: "05", title: "OBD Diagnostics", desc: "Fault code lookup & full diagnostic pipeline", icon: ScanLine },
  { to: "/knowledge", n: "06", title: "Knowledge Base", desc: "RAG-grounded manuals & service docs", icon: BookOpen },
  { to: "/trip", n: "08", title: "Trip Planner", desc: "GO / CAUTION / NO-GO trip readiness", icon: Map },
  { to: "/driver", n: "09", title: "Driver Behaviour", desc: "Driving-style profiling & coaching", icon: GaugeIcon },
];

function MetricCard({ title, loading, error, children }) {
  return (
    <Card title={title}>
      {loading ? <GaugeSkeleton size={112} /> : error ? (
        <ErrorState message="Health Score service is unreachable. Is Phase 2 running?" />
      ) : children}
    </Card>
  );
}

export default function Overview() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    phase2.get(`/fleet/vehicle/0`)
      .then((r) => { if (!cancelled) setHealth(r.data); })
      .catch(() => { if (!cancelled) { setHealth(null); setError(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="max-w-6xl">
      <PageHeader
        eyebrow="Platform overview"
        title="Vehicle Intelligence Platform"
        description="One instrumentation layer over seven active services — health scoring, predictive maintenance, a live digital twin, OBD-II diagnostics, a grounded knowledge base, trip planning, and driver-behaviour analytics."
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <MetricCard title="Reference vehicle" loading={loading} error={error && !health}>
          {health && (
            <div className="flex justify-center"><Gauge value={health.vehicle_health} label="Vehicle health" size={112} /></div>
          )}
        </MetricCard>
        <MetricCard title="Engine" loading={loading} error={error && !health}>
          {health && <div className="flex justify-center"><Gauge value={health.engine_health} label="Engine health" size={112} /></div>}
        </MetricCard>
        <MetricCard title="Battery" loading={loading} error={error && !health}>
          {health && <div className="flex justify-center"><Gauge value={health.battery_health} label="Battery health" size={112} /></div>}
        </MetricCard>
        <MetricCard title="Trip readiness" loading={loading} error={error && !health}>
          {health && (
            <div className="flex justify-center">
              <Gauge value={health.trip_readiness} label={health.trip_readiness_label} size={112} />
            </div>
          )}
        </MetricCard>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PHASES.map(({ to, n, title, desc, icon: Icon }) => (
          <Link key={to} to={to} className="panel p-5 flex items-center gap-4 hover:border-accent/50 hover:shadow-md transition-all group">
            <div className="w-11 h-11 rounded-lg bg-brand-light flex items-center justify-center shrink-0">
              <Icon size={19} className="text-brand" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-ink-faint">P{n}</span>
                <h3 className="text-sm font-semibold text-ink">{title}</h3>
              </div>
              <p className="text-xs text-ink-muted mt-0.5 leading-relaxed">{desc}</p>
            </div>
            <ArrowRight size={16} className="text-ink-faint group-hover:text-accent group-hover:translate-x-0.5 transition-all shrink-0" />
          </Link>
        ))}
      </div>
    </div>
  );
}
