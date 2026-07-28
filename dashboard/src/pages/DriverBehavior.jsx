import { useState } from "react";
import { PlayCircle, TrendingUp } from "lucide-react";
import { phase9 } from "../api/client";
import { PageHeader, Card, Button, Loading, StatusPill, StatRow, ErrorState, GaugeSkeleton, LoadingSkeleton } from "../components/ui";
import { useApi, errorMessage } from "../hooks/useApi";
import Gauge from "../components/Gauge";

const PRIORITY_LEVEL = { high: "crit", medium: "warn", low: "good" };

export default function DriverBehavior() {
  const [pipelineReady, setPipelineReady] = useState(null); // null=unknown, false, true
  const [starting, setStarting] = useState(false);
  const [vehId, setVehId] = useState(8);

  const { data: health, error: healthError } = useApi(() => phase9.get("/health").then((r) => {
    setPipelineReady(r.data.pipeline_ready);
    return r.data;
  }), []);

  const { data: drivers } = useApi(
    () => pipelineReady ? phase9.get("/drivers").then((r) => r.data) : Promise.resolve(null),
    [pipelineReady]
  );

  const { data: profile, loading: profileLoading, error: profileError, refetch } = useApi(
    () => pipelineReady ? phase9.get("/driver/profile", { params: { veh_id: vehId } }).then((r) => r.data) : Promise.resolve(null),
    [pipelineReady, vehId]
  );
  const { data: score } = useApi(
    () => pipelineReady ? phase9.get("/driver/score", { params: { veh_id: vehId } }).then((r) => r.data) : Promise.resolve(null),
    [pipelineReady, vehId]
  );
  const { data: stats } = useApi(
    () => pipelineReady ? phase9.get("/driver/statistics", { params: { veh_id: vehId } }).then((r) => r.data) : Promise.resolve(null),
    [pipelineReady, vehId]
  );
  const { data: coaching, loading: coachingLoading } = useApi(
    () => pipelineReady ? phase9.get("/driver/coaching", { params: { veh_id: vehId, use_llm: false } }).then((r) => r.data) : Promise.resolve(null),
    [pipelineReady, vehId]
  );

  async function startPipeline() {
    setStarting(true);
    try {
      await phase9.post("/pipeline/run", null, { params: { source: "data/raw/VED_sample_small.csv" } });
      setPipelineReady(true);
    } catch {
      setPipelineReady(false);
    } finally {
      setStarting(false);
    }
  }

  if (healthError && pipelineReady === null) {
    return (
      <div className="max-w-6xl">
        <PageHeader eyebrow="Phase 09" title="Driver Behaviour" description="Driving-style profiling and coaching from trip telemetry." />
        <Card>
          <ErrorState message={errorMessage(healthError, "Driver Behaviour")} />
        </Card>
      </div>
    );
  }

  if (pipelineReady === false || pipelineReady === null) {
    return (
      <div className="max-w-6xl">
        <PageHeader eyebrow="Phase 09" title="Driver Behaviour" description="Driving-style profiling and coaching from trip telemetry." />
        <Card>
          <div className="flex flex-col items-center gap-4 py-12 px-4">
            <div className="w-14 h-14 rounded-full bg-brand-light flex items-center justify-center">
              <PlayCircle size={28} className="text-brand" />
            </div>
            <p className="text-sm text-ink-muted text-center max-w-sm leading-relaxed">
              This service processes trip data on demand. Run the pipeline once against the bundled sample dataset to populate driver profiles.
            </p>
            <Button onClick={startPipeline} disabled={starting}>{starting ? "Processing…" : "Run pipeline on sample data"}</Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-6xl">
      <PageHeader eyebrow="Phase 09" title="Driver Behaviour" description="Driving-style profiling and coaching from trip telemetry." />

      <div className="flex items-center gap-2 mb-5 flex-wrap">
        <span className="eyebrow text-brand">Driver</span>
        <select value={vehId} onChange={(e) => setVehId(+e.target.value)}
          className="bg-base-inset border border-base-border rounded-lg px-3 py-1.5 text-sm font-mono outline-none text-ink">
          {(drivers?.veh_ids || [vehId]).map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </div>

      {profileLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          {[1, 2, 3, 4].map((k) => <Card key={k}><GaugeSkeleton size={100} /></Card>)}
        </div>
      ) : profileError ? (
        <ErrorState message={errorMessage(profileError, "Driver Behaviour")} onRetry={refetch} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          <Card><div className="flex justify-center"><Gauge value={score?.driver_score ?? 0} label="Driver score" size={100} /></div></Card>
          <Card>
            <div className="flex flex-col items-center justify-center h-full min-h-[120px] gap-2">
              <StatusPill level="neutral">{profile?.profile}</StatusPill>
              <span className="text-[11px] text-ink-faint text-center">{profile?.trip_count} trips · {profile?.total_distance_km.toFixed(0)} km</span>
            </div>
          </Card>
          <Card title="Penalties / bonuses">
            <StatRow label="Total penalty" value={score?.total_penalty.toFixed(1)} />
            <StatRow label="Total bonus" value={score?.total_bonus.toFixed(1)} />
          </Card>
          <Card title="Eco driving">
            <div className="flex justify-center"><Gauge value={stats?.avg_eco_driving_score ?? 0} size={80} strokeWidth={7} /></div>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Driving statistics">
          {!stats ? <LoadingSkeleton rows={6} /> : (
            <>
              <StatRow label="Avg. speed" value={`${stats.avg_speed_kmh.toFixed(1)} km/h`} />
              <StatRow label="Harsh brakes" value={stats.total_harsh_brakes} />
              <StatRow label="Aggressive accelerations" value={stats.total_aggressive_accelerations} />
              <StatRow label="Sharp turns" value={stats.total_sharp_turns} />
              <StatRow label="Fuel efficiency" value={stats.avg_fuel_efficiency_km_per_l ? `${stats.avg_fuel_efficiency_km_per_l.toFixed(1)} km/L` : "—"} />
              <StatRow label="Total duration" value={`${stats.total_duration_hours.toFixed(1)} h`} />
            </>
          )}
        </Card>

        <Card title="Coaching">
          {coachingLoading ? <Loading label="Loading coaching tips…" /> : !coaching ? (
            <LoadingSkeleton rows={4} />
          ) : (
            <div className="space-y-2">
              {coaching.cards.map((c, i) => (
                <div key={i} className="bg-base-inset rounded-lg p-3 border border-base-border">
                  <div className="flex items-center justify-between mb-1 gap-2">
                    <span className="text-xs font-medium text-ink flex items-center gap-1.5">
                      <TrendingUp size={12} className="text-accent shrink-0" /> {c.category}
                    </span>
                    <StatusPill level={PRIORITY_LEVEL[c.priority?.toLowerCase()] || "neutral"}>{c.priority}</StatusPill>
                  </div>
                  <p className="text-xs text-ink-muted leading-relaxed">{c.message}</p>
                </div>
              ))}
              {coaching.narrative && (
                <p className="text-xs text-ink-muted italic pt-2 border-t border-base-border mt-3 leading-relaxed">{coaching.narrative}</p>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
