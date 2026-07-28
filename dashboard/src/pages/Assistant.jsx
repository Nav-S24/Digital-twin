import { useState, useRef, useEffect } from "react";
import { Send, RotateCcw } from "lucide-react";
import { phase7 } from "../api/client";
import { PageHeader, StatusPill, Loading } from "../components/ui";
import { useVehicle } from "../context/VehicleContext";

const SUGGESTIONS = [
  "Why is my engine health dropping?",
  "What does P0420 mean?",
  "Can I drive with P0101?",
  "What maintenance should I do next?",
];

export default function Assistant() {
  const { vehicleId } = useVehicle();
  const sessionId = useRef(`dash-${Math.random().toString(36).slice(2, 10)}`);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send(text) {
    const message = (text ?? input).trim();
    if (!message || sending) return;
    setMessages((m) => [...m, { role: "user", text: message }]);
    setInput("");
    setSending(true);
    try {
      const { data } = await phase7.post("/chat", { vehicle_id: vehicleId, session_id: sessionId.current, message });
      setMessages((m) => [...m, {
        role: "assistant", text: data.answer, intent: data.intent,
        sources: data.data_sources, codes: data.obd_codes,
      }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", text: err.response?.data?.detail || "The assistant service is unreachable.", error: true }]);
    } finally {
      setSending(false);
    }
  }

  async function clearChat() {
    try { await phase7.post("/chat/clear", { session_id: sessionId.current }); } catch { /* ignore */ }
    setMessages([]);
  }

  return (
    <div className="h-[calc(100vh-100px)] flex flex-col">
      <PageHeader
        eyebrow="phase 07"
        title="Assistant"
        description="Conversational vehicle Q&A — health explanations, fault diagnosis, maintenance queries, and general vehicle knowledge, in one chat."
      />

      <div className="panel flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-base-border">
          <span className="text-xs text-ink-faint font-mono">vehicle: {vehicleId}</span>
          <button onClick={clearChat} className="flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink">
            <RotateCcw size={12} /> Clear session
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-wrap gap-2 justify-center pt-10">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="text-xs px-3 py-2 rounded-lg bg-base-panel border border-base-border text-ink-muted hover:border-accent/40 hover:text-ink">
                  {s}
                </button>
              ))}
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm ${
                m.role === "user" ? "bg-accent text-base" : m.error ? "bg-crit/10 text-crit" : "bg-base-panel text-ink"
              }`}>
                <p className="whitespace-pre-wrap">{m.text}</p>
                {m.intent && (
                  <div className="mt-2 pt-2 border-t border-white/10 flex flex-wrap items-center gap-1.5">
                    <StatusPill level="neutral">{m.intent}</StatusPill>
                    {m.codes?.map((c) => <StatusPill key={c} level="warn">{c}</StatusPill>)}
                  </div>
                )}
              </div>
            </div>
          ))}
          {sending && <Loading label="Thinking…" />}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-base-border p-3 flex items-center gap-2">
          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask about your vehicle…"
            className="flex-1 bg-base-panel border border-base-border rounded-lg px-3 py-2 text-sm outline-none"
          />
          <button onClick={() => send()} disabled={sending} className="w-9 h-9 rounded-lg bg-accent text-base flex items-center justify-center disabled:opacity-40">
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
