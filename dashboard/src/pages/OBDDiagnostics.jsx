import { useState } from "react";
import { Search } from "lucide-react";
import { phase5 } from "../api/client";
import { PageHeader, Card, Button, StatusPill, StatRow, Loading, ErrorState } from "../components/ui";

const SEVERITY_LEVEL = { Critical: "crit", High: "crit", Medium: "warn", Low: "good", Unknown: "neutral" };

export default function OBDDiagnostics() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);

  const [codes, setCodes] = useState("P0420, P0300");
  const [engine, setEngine] = useState({ temperature: 305, rpm: 2200, torque: 45, tool_wear: 120 });
  const [diagnosis, setDiagnosis] = useState(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagError, setDiagError] = useState(null);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(false);
    try {
      const { data } = await phase5.get("/obd/search", { params: { q: query } });
      setResults(data);
    } catch {
      setResults(null);
      setSearchError(true);
    } finally {
      setSearching(false);
    }
  }

  async function runDiagnosis() {
    setDiagnosing(true);
    setDiagError(null);
    try {
      const { data } = await phase5.post("/diagnose", {
        fault_codes: codes.split(",").map((c) => c.trim()).filter(Boolean),
        ...engine,
      });
      setDiagnosis(data);
    } catch (err) {
      setDiagnosis(null);
      setDiagError(err.response?.data?.detail || "OBD Diagnostics service is unreachable.");
    } finally {
      setDiagnosing(false);
    }
  }

  return (
    <div className="max-w-6xl">
      <PageHeader
        eyebrow="Phase 05"
        title="OBD-II Diagnostics"
        description="Look up any diagnostic trouble code, or run the full diagnostic pipeline combining fault codes with live engine telemetry."
      />

      <Card title="Code lookup" className="mb-6">
        <div className="flex flex-col sm:flex-row gap-2 mb-4">
          <div className="flex-1 flex items-center gap-2 bg-base-inset border border-base-border rounded-lg px-3">
            <Search size={14} className="text-ink-faint shrink-0" />
            <input
              value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="Search by symptom, e.g. 'misfire' or a code like P0420"
              className="flex-1 bg-transparent py-2.5 text-sm outline-none text-ink min-w-0"
            />
          </div>
          <Button onClick={search} disabled={searching}>{searching ? "Searching…" : "Search"}</Button>
        </div>
        {searchError && <ErrorState message="OBD Diagnostics service is unreachable." onRetry={search} />}
        {results && !searchError && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {results.length === 0 && <p className="text-sm text-ink-faint col-span-2">No matches.</p>}
            {results.slice(0, 8).map((r) => (
              <div key={r.code} className="bg-base-inset rounded-lg p-3 border border-base-border">
                <div className="flex justify-between items-center mb-1 gap-2">
                  <span className="font-mono text-sm text-accent font-medium">{r.code}</span>
                  <StatusPill level={SEVERITY_LEVEL[r.severity] || "neutral"}>{r.severity}</StatusPill>
                </div>
                <p className="text-xs text-ink-muted leading-relaxed">{r.description}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Run diagnostic pipeline">
          <label className="text-xs text-ink-muted block mb-1.5">Fault codes (comma-separated)</label>
          <input
            value={codes} onChange={(e) => setCodes(e.target.value)}
            className="w-full bg-base-inset border border-base-border rounded-lg px-3 py-2 text-sm font-mono outline-none mb-4 text-ink"
          />
          {Object.entries(engine).map(([key, val]) => (
            <div key={key} className="mb-3">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-ink-muted capitalize">{key.replace(/_/g, " ")}</span>
                <span className="font-mono text-ink">{val}</span>
              </div>
              <input type="range" className="w-full accent-accent h-1.5 cursor-pointer"
                min={key === "temperature" ? 250 : 0}
                max={key === "temperature" ? 400 : key === "rpm" ? 7000 : key === "tool_wear" ? 250 : 200}
                value={val}
                onChange={(e) => setEngine((s) => ({ ...s, [key]: +e.target.value }))} />
            </div>
          ))}
          <Button onClick={runDiagnosis} disabled={diagnosing} className="w-full mt-2">
            {diagnosing ? "Diagnosing…" : "Run diagnosis"}
          </Button>
        </Card>

        <Card title="Diagnosis">
          {diagnosing ? <Loading /> : diagError ? (
            <ErrorState message={diagError} onRetry={runDiagnosis} />
          ) : !diagnosis ? (
            <p className="text-sm text-ink-faint text-center py-16">Run a diagnosis to see results.</p>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
                <StatusPill level={diagnosis.trip_status === "OK" ? "good" : diagnosis.trip_status === "CAUTION" ? "warn" : "crit"}>
                  {diagnosis.trip_status}
                </StatusPill>
                <span className="text-xs font-mono text-ink-muted">{(diagnosis.failure_probability * 100).toFixed(1)}% failure risk</span>
              </div>
              <StatRow label="Description" value={diagnosis.description} mono={false} />
              <StatRow label="Remaining life" value={`${diagnosis.remaining_life} cycles`} />
              <StatRow label="Maintenance urgency" value={diagnosis.maintenance_urgency} />
              {diagnosis.obd_details?.length > 0 && (
                <div className="mt-4 space-y-2">
                  {diagnosis.obd_details.map((d, i) => (
                    <div key={i} className="bg-base-inset rounded-lg p-3 text-xs border border-base-border">
                      <span className="font-mono text-accent font-medium">{d.code}</span>
                      <p className="text-ink-muted mt-1">{d.description}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
