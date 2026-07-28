import { useState } from "react";
import { phase2 } from "../api/client";
import { PageHeader, Card, ErrorState, StatRow, Button, StatusPill, LoadingSkeleton } from "../components/ui";
import { useApi, errorMessage } from "../hooks/useApi";
import Gauge from "../components/Gauge";

const DEFAULTS = {
  temperature: 85, pressure: 28, rpm: 2800, vibration: 0.3,
  battery_voltage: 12.4, battery_current: 40, battery_temp: 30, fault_count: 1,
};

function Slider({ label, unit, value, min, max, step, onChange }) {
  return (
    <div className="mb-4">
      <div className="flex justify-between text-xs mb-1.5">
        <span className="text-ink-muted">{label}</span>
        <span className="font-mono text-ink">{value}{unit}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-accent h-1.5 cursor-pointer"
      />
    </div>
  );
}

export default function HealthScore() {
  const [reading, setReading] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [scoring, setScoring] = useState(false);

  const { data: summary, loading: summaryLoading, error: summaryError } =
    useApi(() => phase2.get("/fleet/summary").then((r) => r.data), []);

  const set = (key) => (val) => setReading((r) => ({ ...r, [key]: val }));

  async function computeScore() {
    setScoring(true);
    try {
      const { data } = await phase2.post("/score", reading);
      setResult(data);
    } catch {
      setResult(null);
    } finally {
      setScoring(false);
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        eyebrow="Phase 02"
        title="Health Score"
        description="Rule-based engine, battery, and vehicle health scoring, plus ML-derived health score and remaining useful life."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card title="Reference fleet">
          {summaryLoading ? <LoadingSkeleton rows={5} /> : summaryError ? (
            <ErrorState message={errorMessage(summaryError, "Health Score")} />
          ) : (
            <>
              <StatRow label="Total vehicles" value={summary.total_vehicles} />
              <StatRow label="Avg. vehicle health" value={summary.mean_vehicle_health} />
              <StatRow label="Avg. engine health" value={summary.mean_engine_health} />
              <StatRow label="Avg. battery health" value={summary.mean_battery_health} />
              <StatRow label="Failure rate" value={`${(summary.failure_rate * 100).toFixed(2)}%`} />
            </>
          )}
        </Card>

        <Card title="Health class distribution" className="lg:col-span-2">
          {summaryLoading ? <LoadingSkeleton rows={4} /> : summaryError ? (
            <ErrorState message="Health Score service is unreachable." />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {Object.entries(summary.health_class_counts).map(([cls, count]) => (
                <div key={cls} className="bg-base-inset rounded-lg p-3 text-center border border-base-border">
                  <div className="text-xl font-display font-semibold text-ink">{count}</div>
                  <div className="text-[11px] text-ink-muted mt-0.5">{cls}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Live sensor scorer">
          <Slider label="Temperature" unit="°C" value={reading.temperature} min={30} max={140} step={1} onChange={set("temperature")} />
          <Slider label="Pressure" unit=" PSI" value={reading.pressure} min={5} max={50} step={1} onChange={set("pressure")} />
          <Slider label="RPM" unit="" value={reading.rpm} min={0} max={7000} step={50} onChange={set("rpm")} />
          <Slider label="Vibration" unit="g" value={reading.vibration} min={0} max={2} step={0.05} onChange={set("vibration")} />
          <Slider label="Battery voltage" unit="V" value={reading.battery_voltage} min={9} max={14} step={0.1} onChange={set("battery_voltage")} />
          <Slider label="Battery current" unit="A" value={reading.battery_current} min={0} max={150} step={1} onChange={set("battery_current")} />
          <Slider label="Battery temp" unit="°C" value={reading.battery_temp} min={0} max={80} step={1} onChange={set("battery_temp")} />
          <Slider label="Fault codes" unit="" value={reading.fault_count} min={0} max={15} step={1} onChange={set("fault_count")} />
          <Button onClick={computeScore} disabled={scoring} className="w-full mt-2">
            {scoring ? "Computing…" : "Compute health score"}
          </Button>
        </Card>

        <Card title="Result">
          {!result ? (
            <p className="text-sm text-ink-faint text-center py-16">Adjust sensors and compute a score.</p>
          ) : (
            <div>
              <div className="flex justify-around mb-5">
                <Gauge value={result.engine_health} label="Engine" size={104} />
                <Gauge value={result.battery_health} label="Battery" size={104} />
                <Gauge value={result.vehicle_health} label="Vehicle" size={104} />
              </div>
              <div className="flex justify-center mb-4">
                <StatusPill level={result.health_class === "Excellent" || result.health_class === "Good" ? "good" : result.health_class === "Warning" ? "warn" : "crit"}>
                  {result.health_class}
                </StatusPill>
              </div>
              <StatRow label="Trip readiness" value={`${result.trip_readiness} (${result.trip_readiness_label})`} />
              {result.ml_health_score != null && <StatRow label="ML health score" value={result.ml_health_score} />}
              {result.predicted_rul != null && <StatRow label="Predicted RUL" value={`${result.predicted_rul} cycles`} />}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
