import { useState } from "react";
import { phase2, phase3 } from "../api/client";
import { PageHeader, Card, Button, StatusPill, StatRow, ErrorState } from "../components/ui";
import { useVehicle } from "../context/VehicleContext";
import Gauge from "../components/Gauge";

const DEFAULT_SENSORS = {
  temperature: 85, pressure: 28, rpm: 2800, vibration: 0.3,
  battery_voltage: 12.4, battery_current: 40, battery_temp: 30, fault_count: 3,
};

const URGENCY_LEVEL = { CRITICAL: "crit", HIGH: "crit", MEDIUM: "warn", LOW: "good" };

export default function PredictiveMaintenance() {
  const { vehicleId } = useVehicle();
  const [sensors, setSensors] = useState(DEFAULT_SENSORS);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [step, setStep] = useState("");
  const [error, setError] = useState(null);

  const set = (key) => (e) => setSensors((s) => ({ ...s, [key]: parseFloat(e.target.value) }));

  async function runPipeline() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setStep("Scoring health (Phase 2)…");
      const { data: health } = await phase2.post("/score", sensors);

      setStep("Predicting failure risk (Phase 3)…");
      const { data: prediction } = await phase3.post("/predict", {
        vehicle_id: vehicleId,
        ...sensors,
        engine_health: health.engine_health,
        battery_health: health.battery_health,
        vehicle_health: health.vehicle_health,
        ml_health_score: health.ml_health_score ?? 50,
        trip_readiness: health.trip_readiness,
        health_class_id: health.health_class_id,
      });

      setResult({ health, prediction });
    } catch (err) {
      setError(err.response?.data?.detail || "Pipeline failed — check that Phase 2 and Phase 3 services are running.");
    } finally {
      setRunning(false);
      setStep("");
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        eyebrow="Phase 03"
        title="Predictive Maintenance"
        description="Failure probability, remaining useful life, and prioritised recommendations — computed from live sensor readings scored by Phase 2, then fed into Phase 3's trained failure model."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Sensor input">
          {Object.entries(sensors).map(([key, val]) => (
            <div key={key} className="mb-3">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-ink-muted capitalize">{key.replace(/_/g, " ")}</span>
                <span className="font-mono text-ink">{val}</span>
              </div>
              <input type="range" className="w-full accent-accent h-1.5 cursor-pointer"
                min={key === "fault_count" ? 0 : key.includes("voltage") ? 9 : 0}
                max={key === "rpm" ? 7000 : key === "fault_count" ? 15 : key.includes("temp") ? 140 : key.includes("current") ? 150 : 50}
                step={key === "vibration" || key.includes("voltage") ? 0.1 : 1}
                value={val} onChange={set(key)} />
            </div>
          ))}
          <Button onClick={runPipeline} disabled={running} className="w-full mt-2">
            {running ? step || "Running…" : "Run Phase 2 → Phase 3 pipeline"}
          </Button>
          {error && (
            <div className="mt-4">
              <ErrorState message={error} onRetry={runPipeline} />
            </div>
          )}
        </Card>

        <Card title="Prediction">
          {!result ? (
            <p className="text-sm text-ink-faint text-center py-16">Run the pipeline to see a prediction.</p>
          ) : (
            <div>
              <div className="flex flex-wrap justify-around gap-4 mb-5">
                <Gauge value={result.prediction.predictions.failure_probability * 100} label="Failure risk" invert size={104} />
                <Gauge value={Math.min(100, result.prediction.predictions.rul_cycles / 3)} sublabel={`${Math.round(result.prediction.predictions.rul_cycles)}c`} label="RUL" size={104} />
              </div>
              <div className="flex justify-center mb-4">
                <StatusPill level={URGENCY_LEVEL[result.prediction.predictions.urgency] || "neutral"}>
                  {result.prediction.predictions.urgency} urgency
                </StatusPill>
              </div>

              <h4 className="text-xs font-semibold text-ink-muted mb-2 mt-5">Top risk sensors</h4>
              {result.prediction.top_risk_sensors.map((s, i) => (
                <StatRow key={i} label={s.sensor} value={s.shap_value.toFixed(3)} />
              ))}

              <h4 className="text-xs font-semibold text-ink-muted mb-2 mt-5">Recommendations</h4>
              <div className="space-y-2">
                {result.prediction.recommendations.map((r, i) => (
                  <div key={i} className="bg-base-inset rounded-lg p-3 text-xs border border-base-border">
                    <div className="flex justify-between mb-1 gap-2">
                      <span className="text-ink font-medium">{r.action}</span>
                      <span className="text-ink-faint font-mono shrink-0">within {r.book_within_days}d</span>
                    </div>
                    <p className="text-ink-muted">{r.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
