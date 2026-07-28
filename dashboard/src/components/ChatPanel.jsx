import React, { useState, useRef, useEffect } from "react";
import "./ChatPanel.css";

/**
 * ChatPanel
 *
 * Drop this into your existing dashboard. Pass the currently selected
 * Vehicle_ID as a prop - when it changes, the panel automatically starts
 * a fresh session so old vehicle context can never leak into new answers.
 *
 * Props:
 *   vehicleId   - string | null  (e.g. "Vehicle_0042")
 *   apiBaseUrl  - string, defaults to "" (same-origin) - override if your
 *                 FastAPI backend runs on a different host/port in dev.
 */

const SUGGESTED_QUESTIONS = [
  "Why is my engine health dropping?",
  "What maintenance should I do next?",
  "What is my failure risk?",
  "How much useful life is left?",
  "Which sensor is causing the most risk?",
  "What does P0420 mean?",
  "Can I drive with P0101?",
];

function makeSessionId(vehicleId) {
  return `session_${vehicleId || "general"}_${Date.now()}`;
}

export default function ChatPanel({ vehicleId = null, apiBaseUrl = "" }) {
  const [sessionId, setSessionId] = useState(() => makeSessionId(vehicleId));
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);
  const prevVehicleRef = useRef(vehicleId);

  // Reset session whenever the dashboard's selected vehicle changes.
  useEffect(() => {
    if (prevVehicleRef.current !== vehicleId) {
      prevVehicleRef.current = vehicleId;
      setSessionId(makeSessionId(vehicleId));
      setMessages([]);
      setError(null);
    }
  }, [vehicleId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${apiBaseUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vehicle_id: vehicleId,
          session_id: sessionId,
          message: trimmed,
        }),
      });

      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          intent: data.intent,
          sources: data.data_sources || [],
          obdCodes: data.obd_codes || [],
        },
      ]);
    } catch (err) {
      setError(err.message || "Something went wrong reaching the assistant.");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    sendMessage(input);
  }

  async function handleClearChat() {
    try {
      await fetch(`${apiBaseUrl}/chat/clear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      // clearing server-side memory failing shouldn't block clearing the UI
    }
    setMessages([]);
    setError(null);
    setSessionId(makeSessionId(vehicleId));
  }

  return (
    <div className="chat-panel">
      <div className="chat-panel__header">
        <div>
          <div className="chat-panel__title">Vehicle Assistant</div>
          <div className="chat-panel__vehicle">
            {vehicleId ? `Selected: ${vehicleId}` : "No vehicle selected"}
          </div>
        </div>
        <button
          className="chat-panel__clear-btn"
          onClick={handleClearChat}
          disabled={messages.length === 0}
          type="button"
        >
          Clear chat
        </button>
      </div>

      <div className="chat-panel__messages" ref={scrollRef}>
        {messages.length === 0 && !loading && (
          <div className="chat-panel__empty">
            <p>Ask about vehicle health, maintenance, failure risk, RUL, or an OBD code.</p>
            <div className="chat-panel__suggestions">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  className="chat-panel__suggestion"
                  onClick={() => sendMessage(q)}
                  type="button"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg--${m.role}`}>
            <div className="chat-msg__bubble">
              <div className="chat-msg__content">{m.content}</div>
              {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                <div className="chat-msg__sources">
                  {m.sources.map((s) => (
                    <span key={s} className="chat-msg__source-tag">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-msg chat-msg--assistant">
            <div className="chat-msg__bubble chat-msg__bubble--loading">
              Thinking...
            </div>
          </div>
        )}

        {error && <div className="chat-panel__error">⚠ {error}</div>}
      </div>

      <form className="chat-panel__input-row" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this vehicle..."
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
