import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { phase4 } from "../api/client";
import { PageHeader, Card, Loading, ErrorState, Button, StatusPill, CHART, GaugeSkeleton, LoadingSkeleton } from "../components/ui";
import { useApi, errorMessage } from "../hooks/useApi";
import { useVehicle } from "../context/VehicleContext";
import Gauge from "../components/Gauge";

export default function DigitalTwin() {
  const { vehicleId } = useVehicle();
  const [simDays, setSimDays] = useState(30);
  const [simData, setSimData] = useState(null);
  const [simulating, setSimulating] = useState(false);

  const { data: fleet, loading: fleetLoading, error: fleetError } =
    useApi(() => phase4.get("/fleet").then((r) => r.data), []);

  const { data: current, loading: curLoading, error: curError, refetch } =
    useApi(() => phase4.get(`/current/${vehicleId}`).then((r) => r.data), [vehicleId]);

  const { data: components, loading: compLoading, error: compError } =
    useApi(() => phase4.get(`/components/${vehicleId}`).then((r) => r.data), [vehicleId]);

  async function runSimulation() {
    setSimulating(true);
    try {
      const { data } = await phase4.post("/simulate", { vehicle_id: vehicleId, days: simDays });
      setSimData(data.trajectory.map((p) => ({ day: p.day, health: p.vehicle_health, risk: +(p.failure_probability * 100).toFixed(1) })));
    } catch {
      setSimData(null);
    } finally {
      setSimulating(false);
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        eyebrow="Phase 04"
        title="Digital Twin"
        description="Live per-component simulation (engine, battery, fuel, brake) with a forward-looking failure-probability projection."
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <Card title="Fleet">
          {fleetLoading ? <LoadingSkeleton rows={3} /> : fleetError ? (
            <ErrorState message={errorMessage(fleetError, "Digital Twin")} />
          ) : fleet && (
            <>
              <div className="text-2xl font-display font-semibold text-ink">{fleet.total_vehicles}</div>
              <div className="text-[11px] text-ink-muted mb-3">vehicles simulated</div>
              <div className="flex flex-wrap gap-3 text-[11px]">
                <span className="text-good">● {fleet.excellent_count} exc.</span>
                <span className="text-accent">● {fleet.good_count} good</span>
                <span className="text-warn">● {fleet.warning_count} warn</span>
                <span className="text-crit">● {fleet.critical_count} crit</span>
              </div>
            </>
          )}
        </Card>

        {curLoading ? (
          <>
            <Card><GaugeSkeleton size={100} /></Card>
            <Card><GaugeSkeleton size={100} /></Card>
            <Card><LoadingSkeleton rows={2} /></Card>
          </>
        ) : curError ? (
          <div className="sm:col-span-2 xl:col-span-3 panel p-0 overflow-hidden">
            <ErrorState message={errorMessage(curError, "Digital Twin")} onRetry={refetch} />
          </div>
        ) : current && (
          <>
            <Card><div className="flex justify-center"><Gauge value={current.overall_health} label="Overall health" size={100} /></div></Card>
            <Card><div className="flex justify-center"><Gauge value={current.overall_failure_probability * 100} label="Failure risk" invert size={100} /></div></Card>
            <Card>
              <div className="flex flex-col items-center justify-center h-full min-h-[120px] gap-2">
                <StatusPill level={current.overall_failure_probability > 0.5 ? "crit" : current.overall_failure_probability > 0.2 ? "warn" : "good"}>
                  {current.health_class}
                </StatusPill>
                <span className="text-[11px] text-ink-faint font-mono">{vehicleId}</span>
              </div>
            </Card>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <Card title="Component breakdown">
          {compLoading ? <Loading label="Loading components…" /> : compError ? (
            <ErrorState message={errorMessage(compError, "Digital Twin")} />
          ) : components ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {["engine", "battery", "fuel", "brake"].map((c) => (
                components[c] && (
                  <div key={c} className="flex items-center gap-3 bg-base-inset rounded-lg p-3 border border-base-border">
                    <Gauge value={components[c].health_score} size={64} strokeWidth={6} />
                    <div>
                      <div className="text-xs font-semibold text-ink capitalize">{c}</div>
                      <div className="text-[10px] text-ink-faint font-mono">
                        risk {(components[c].failure_probability * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                )
              ))}
            </div>
          ) : null}
        </Card>

        <Card title="Forward simulation" right={
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <input type="number" min={7} max={180} value={simDays}
              onChange={(e) => setSimDays(+e.target.value)}
              className="w-16 bg-base-inset border border-base-border rounded px-2 py-1 text-xs font-mono text-ink" />
            <Button onClick={runSimulation} disabled={simulating}>{simulating ? "Simulating…" : "Simulate"}</Button>
          </div>
        }>
          {simData ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={simData}>
                <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
                <XAxis dataKey="day" stroke={CHART.axis} fontSize={11} tickLine={false} />
                <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} />
                <Tooltip contentStyle={CHART.tooltip} />
                <Line type="monotone" dataKey="health" stroke={CHART.primary} strokeWidth={2} dot={false} name="Vehicle health" />
                <Line type="monotone" dataKey="risk" stroke={CHART.danger} strokeWidth={2} dot={false} name="Failure risk %" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-ink-faint text-center py-16">Run a simulation to project this vehicle forward.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
