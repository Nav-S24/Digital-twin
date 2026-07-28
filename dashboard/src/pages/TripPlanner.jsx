import { useState } from "react";
import { MapPin, Fuel, CloudRain, ShieldAlert } from "lucide-react";
import { phase8 } from "../api/client";
import { PageHeader, Card, Button, StatusPill, ErrorState } from "../components/ui";
import { useVehicle } from "../context/VehicleContext";
import Gauge from "../components/Gauge";

const STATUS_LEVEL = { GO: "good", CAUTION: "warn", "NO-GO": "crit" };

export default function TripPlanner() {
  const { vehicleId } = useVehicle();
  const [source, setSource] = useState("Pune");
  const [destination, setDestination] = useState("Mumbai");
  const [fuelLevel, setFuelLevel] = useState(40);
  const [driverScore, setDriverScore] = useState(75);
  const [assessing, setAssessing] = useState(false);
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState(null);

  async function assess() {
    setAssessing(true);
    setError(null);
    try {
      const { data } = await phase8.post("/trip/assess/by_vehicle_id", {
        vehicle_id: vehicleId, source, destination,
        fuel_level_l: fuelLevel, driver_behaviour_score: driverScore,
      });
      setTrip(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Trip assessment failed — is the Phase 8 service running?");
      setTrip(null);
    } finally {
      setAssessing(false);
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        eyebrow="Phase 08"
        title="Trip Planner"
        description="GO / CAUTION / NO-GO trip readiness, combining vehicle health, route, weather, fuel economics, and driver behaviour."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Plan a trip">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="text-xs text-ink-muted block mb-1.5">From</label>
              <input value={source} onChange={(e) => setSource(e.target.value)}
                className="w-full bg-base-inset border border-base-border rounded-lg px-3 py-2 text-sm outline-none text-ink" />
            </div>
            <div>
              <label className="text-xs text-ink-muted block mb-1.5">To</label>
              <input value={destination} onChange={(e) => setDestination(e.target.value)}
                className="w-full bg-base-inset border border-base-border rounded-lg px-3 py-2 text-sm outline-none text-ink" />
            </div>
          </div>

          <div className="mb-3">
            <div className="flex justify-between text-xs mb-1"><span className="text-ink-muted">Fuel level</span><span className="font-mono text-ink">{fuelLevel} L</span></div>
            <input type="range" min={0} max={80} value={fuelLevel} onChange={(e) => setFuelLevel(+e.target.value)} className="w-full accent-accent h-1.5 cursor-pointer" />
          </div>
          <div className="mb-5">
            <div className="flex justify-between text-xs mb-1"><span className="text-ink-muted">Driver behaviour score</span><span className="font-mono text-ink">{driverScore}</span></div>
            <input type="range" min={0} max={100} value={driverScore} onChange={(e) => setDriverScore(+e.target.value)} className="w-full accent-accent h-1.5 cursor-pointer" />
          </div>

          <Button onClick={assess} disabled={assessing} className="w-full">
            {assessing ? "Assessing…" : "Assess trip readiness"}
          </Button>
          {error && (
            <div className="mt-4">
              <ErrorState message={error} onRetry={assess} />
            </div>
          )}
        </Card>

        <Card title="Assessment">
          {!trip ? (
            <p className="text-sm text-ink-faint text-center py-16">Plan a trip to see its readiness.</p>
          ) : (
            <div>
              <div className="flex flex-wrap items-center justify-center gap-6 mb-5">
                <Gauge value={100 - trip.risk.risk_score} label="Readiness" size={104} />
                <StatusPill level={STATUS_LEVEL[trip.risk.trip_status] || "neutral"}>{trip.risk.trip_status}</StatusPill>
              </div>

              <p className="text-sm text-ink-muted mb-4 italic leading-relaxed">"{trip.natural_language_summary}"</p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
                <div className="bg-base-inset rounded-lg p-3 text-center border border-base-border">
                  <MapPin size={14} className="text-accent mx-auto mb-1" />
                  <div className="text-sm font-mono text-ink">{trip.route.distance_km.toFixed(0)} km</div>
                  <div className="text-[10px] text-ink-faint">{Math.round(trip.route.duration_min)} min</div>
                </div>
                <div className="bg-base-inset rounded-lg p-3 text-center border border-base-border">
                  <CloudRain size={14} className="text-accent mx-auto mb-1" />
                  <div className="text-sm font-mono text-ink">{trip.weather.temperature_c.toFixed(0)}°C</div>
                  <div className="text-[10px] text-ink-faint">{trip.weather.condition}</div>
                </div>
                <div className="bg-base-inset rounded-lg p-3 text-center border border-base-border">
                  <Fuel size={14} className="text-accent mx-auto mb-1" />
                  <div className="text-sm font-mono text-ink">₹{trip.fuel.fuel_cost.toFixed(0)}</div>
                  <div className="text-[10px] text-ink-faint">{trip.fuel.fuel_sufficient ? "sufficient" : "refuel needed"}</div>
                </div>
              </div>

              {trip.risk.contributing_factors?.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-xs font-semibold text-ink-muted mb-2 flex items-center gap-1.5"><ShieldAlert size={12} /> Contributing factors</h4>
                  <ul className="space-y-1">
                    {trip.risk.contributing_factors.map((f, i) => <li key={i} className="text-xs text-ink-muted">• {f}</li>)}
                  </ul>
                </div>
              )}

              {trip.service_centre_recommendation && (
                <div className="bg-warn/10 border border-warn/25 rounded-lg p-3 text-xs">
                  <span className="text-warn font-semibold">Service centre recommended: </span>
                  <span className="text-ink-muted">{trip.service_centre_recommendation.name} — {trip.service_centre_recommendation.distance_km.toFixed(1)} km away</span>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
