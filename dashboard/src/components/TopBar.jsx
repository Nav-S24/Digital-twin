import { useEffect, useState } from "react";
import { Car } from "lucide-react";
import { ALL_SERVICES } from "../api/client";
import { useVehicle } from "../context/VehicleContext";

function ServiceStatus() {
  const [status, setStatus] = useState({}); // id -> "up" | "down" | "checking"

  useEffect(() => {
    let cancelled = false;

    async function check(svc) {
      try {
        await svc.client.get(svc.healthPath, { timeout: 5000 });
        if (!cancelled) setStatus((s) => ({ ...s, [svc.id]: "up" }));
      } catch {
        if (!cancelled) setStatus((s) => ({ ...s, [svc.id]: "down" }));
      }
    }

    ALL_SERVICES.forEach(check);
    const interval = setInterval(() => ALL_SERVICES.forEach(check), 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const upCount = Object.values(status).filter((s) => s === "up").length;

  return (
    <div className="flex items-center gap-2 flex-wrap justify-end" title="Backend service status">
      <span className="eyebrow text-ink-faint hidden sm:inline">Services</span>
      <div className="flex items-center gap-1">
        {ALL_SERVICES.map((svc) => (
          <span
            key={svc.id}
            title={`${svc.name}: ${status[svc.id] ?? "checking"}`}
            className={`status-dot ${
              status[svc.id] === "up"
                ? "bg-good shadow-glow shadow-good"
                : status[svc.id] === "down"
                ? "bg-crit"
                : "bg-ink-faint animate-pulse"
            }`}
          />
        ))}
      </div>
      <span className="text-[11px] font-mono text-ink-faint">{upCount}/{ALL_SERVICES.length}</span>
    </div>
  );
}

export default function TopBar() {
  const { vehicleId, setVehicleId } = useVehicle();

  return (
    <header className="h-14 md:h-16 shrink-0 border-b border-base-border bg-white flex items-center justify-between px-4 md:px-6 shadow-sm">
      <div className="flex items-center gap-2.5 bg-base border border-base-border rounded-lg px-3 py-1.5">
        <Car size={15} className="text-brand shrink-0" />
        <label className="sr-only" htmlFor="vehicle-id">Vehicle ID</label>
        <input
          id="vehicle-id"
          value={vehicleId}
          onChange={(e) => setVehicleId(e.target.value)}
          spellCheck={false}
          className="bg-transparent text-sm font-mono text-ink outline-none w-28 sm:w-36"
          placeholder="Vehicle_0001"
        />
      </div>

      <ServiceStatus />
    </header>
  );
}
