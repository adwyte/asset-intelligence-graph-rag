import React, { useState, useEffect } from "react";
import { sendQuery, QueryResponse } from "./api";
import { useSpeechRecognition } from "./hooks/useSpeechRecognition";

const App: React.FC = () => {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { listening, transcript, start } = useSpeechRecognition();

  useEffect(() => {
    if (transcript) {
      setQuestion(transcript);
    }
  }, [transcript]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await sendQuery(question.trim());
      setResponse(res);
    } catch (err: any) {
      setError(err.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>Asset Intelligence Graph-RAG Demo</h1>
      <p style={{ color: "#555" }}>
        Ask about Modulathe parts, reuse, and compatibility.
      </p>

      <form onSubmit={handleSubmit} style={{ marginTop: 16 }}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          style={{
            width: "100%",
            padding: 12,
            fontSize: 14,
            borderRadius: 6,
            border: "1px solid #ccc",
            resize: "vertical"
          }}
          placeholder="e.g. Which motor and bearings were used in Modulathe V2 spindle, and are there compatible alternatives?"
        />
        <div style={{ display: "flex", marginTop: 8, gap: 8, alignItems: "center" }}>
          <button
            type="submit"
            disabled={loading}
            style={{
              padding: "8px 16px",
              borderRadius: 6,
              border: "none",
              background: "#2563eb",
              color: "white",
              cursor: "pointer"
            }}
          >
            {loading ? "Thinking..." : "Ask"}
          </button>
          <button
            type="button"
            onClick={start}
            style={{
              padding: "8px 16px",
              borderRadius: 6,
              border: "1px solid #ccc",
              background: listening ? "#fee2e2" : "white",
              cursor: "pointer"
            }}
          >
            🎤 {listening ? "Listening..." : "Speak"}
          </button>
        </div>
      </form>

      {error && (
        <div style={{ marginTop: 16, color: "red" }}>
          Error: {error}
        </div>
      )}

      {response && (
        <div style={{ marginTop: 24 }}>
          <h2>Answer</h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{response.answer}</p>

          <h3 style={{ marginTop: 24 }}>Retrieved Parts</h3>
          {response.context.parts.map((p) => (
            <div
              key={p.part_id}
              style={{
                border: "1px solid #e5e7eb",
                padding: 12,
                borderRadius: 6,
                marginBottom: 8
              }}
            >
              <strong>{p.part_id}</strong> — {p.name}{" "}
              <span style={{ color: "#6b7280" }}>({p.category})</span>
              <div style={{ fontSize: 12, color: "#4b5563", marginTop: 4 }}>
                Score: {p.score.toFixed(3)} | Products: {p.products.join(", ")}
              </div>
              <p style={{ marginTop: 4 }}>{p.description}</p>
              <ul style={{ fontSize: 13, paddingLeft: 18 }}>
                {p.specs.map((s) => (
                  <li key={`${p.part_id}-${s.key}`}>
                    {s.key}: {String(s.value)} {s.unit}
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <h3 style={{ marginTop: 24 }}>Compatibility Among Retrieved Parts</h3>
          {Object.entries(response.context.compatibility).length === 0 && (
            <p>No compatibility edges among retrieved parts yet.</p>
          )}
          {Object.entries(response.context.compatibility).map(([from, list]) => (
            <div key={from} style={{ marginBottom: 12 }}>
              <strong>{from}</strong>
              <ul style={{ fontSize: 13, paddingLeft: 18 }}>
                {list.map((rel) => (
                  <li key={`${from}-${rel.to_id}`}>
                    ↔ {rel.to_id}: score {rel.score.toFixed(2)} —{" "}
                    {rel.explanations.join("; ")}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default App;
