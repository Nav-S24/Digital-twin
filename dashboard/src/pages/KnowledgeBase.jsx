import { useState, useRef, useEffect } from "react";
import { Send, FileText } from "lucide-react";
import { phase6 } from "../api/client";
import { PageHeader, Card, Loading, ErrorState, LoadingSkeleton } from "../components/ui";
import { useApi, errorMessage } from "../hooks/useApi";

const CATEGORIES = [
  { value: "", label: "All documents" },
  { value: "manuals", label: "Manuals" },
  { value: "obd_docs", label: "OBD docs" },
  { value: "service_guides", label: "Service guides" },
  { value: "maintenance_guides", label: "Maintenance guides" },
];

export default function KnowledgeBase() {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Ask me anything about vehicle manuals, OBD codes, service procedures, or maintenance guidelines — every answer is grounded in retrieved documents." },
  ]);
  const [input, setInput] = useState("");
  const [category, setCategory] = useState("");
  const [asking, setAsking] = useState(false);
  const bottomRef = useRef(null);

  const { data: docs, loading: docsLoading, error: docsError, refetch } = useApi(
    () => phase6.get("/documents").then((r) => r.data),
    []
  );

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function ask() {
    const question = input.trim();
    if (!question || asking) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setAsking(true);
    try {
      const { data } = await phase6.post("/ask", { question, category: category || null });
      setMessages((m) => [...m, { role: "assistant", text: data.answer, sources: data.sources, confidence: data.confidence }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", text: err.response?.data?.detail || "The knowledge base service is unreachable.", error: true }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:h-[calc(100vh-140px)] max-w-6xl">
      <div className="lg:col-span-2 flex flex-col min-h-[420px] lg:min-h-0">
        <PageHeader
          eyebrow="Phase 06"
          title="Knowledge Base"
          description="Retrieval-augmented Q&A grounded in ingested manuals, OBD-II docs, and service guides."
        />

        <div className="panel flex-1 flex flex-col overflow-hidden min-h-[320px]">
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-brand text-white"
                    : m.error
                    ? "bg-crit/10 text-crit border border-crit/20"
                    : "bg-base-inset text-ink border border-base-border"
                }`}>
                  <p className="whitespace-pre-wrap">{m.text}</p>
                  {m.sources?.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-base-border space-y-1">
                      {m.sources.map((s, j) => (
                        <div key={j} className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                          <FileText size={11} className="text-accent shrink-0" />
                          <span className="truncate">{s.file_name}{s.page != null && ` · p${s.page}`}</span>
                          <span className="ml-auto font-mono text-ink-faint shrink-0">{(s.score).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {asking && <Loading label="Retrieving & generating…" />}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-base-border p-3 flex flex-col sm:flex-row items-stretch sm:items-center gap-2 bg-white">
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="bg-base-inset border border-base-border rounded-lg text-xs px-2 py-2.5 outline-none text-ink-muted sm:max-w-[140px]">
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <input
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              placeholder="e.g. What should I do if my brake fluid is low?"
              className="flex-1 bg-base-inset border border-base-border rounded-lg px-3 py-2.5 text-sm outline-none text-ink min-w-0"
            />
            <button
              type="button"
              onClick={ask}
              disabled={asking}
              className="w-full sm:w-10 sm:h-10 h-10 rounded-lg bg-brand text-white flex items-center justify-center disabled:opacity-40 shrink-0"
              aria-label="Send question"
            >
              <Send size={15} />
            </button>
          </div>
        </div>
      </div>

      <div className="lg:pt-[76px]">
        <Card title="Indexed documents">
          {docsLoading ? <LoadingSkeleton rows={6} /> : docsError ? (
            <ErrorState message={errorMessage(docsError, "Knowledge Base")} onRetry={refetch} />
          ) : (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto">
              {docs.documents.map((d) => (
                <div key={d.file_name} className="bg-base-inset rounded-lg p-3 border border-base-border">
                  <div className="text-xs text-ink font-medium truncate">{d.file_name}</div>
                  <div className="text-[10px] text-ink-faint mt-0.5">{d.category} · {d.chunk_count} chunks</div>
                </div>
              ))}
              {docs.documents.length === 0 && (
                <p className="text-xs text-ink-faint">No documents ingested yet — run <code className="font-mono text-ink-muted">build_vectordb.py</code>.</p>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
