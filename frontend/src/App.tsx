import React, { useEffect, useMemo, useState } from "react";
import {
  fetchProducts,
  fetchProductCompat,
  fetchNewPartCompat,
  sendQuery,
  ProductInfo,
  QueryResponse,
  CompatPair,
  NewPartCompatRequest,
  NewPartCompatResult,
} from "./api";
import AudioRecorder from "./components/AudioRecorder";

type Mode = "rag" | "compat_existing" | "compat_new";

const App: React.FC = () => {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string | "ALL">("ALL");
  const [mode, setMode] = useState<Mode>("rag");

  const [question, setQuestion] = useState("");
  const [ragResponse, setRagResponse] = useState<QueryResponse | null>(null);

  const [compatPairs, setCompatPairs] = useState<CompatPair[]>([]);
  const [newPartDesc, setNewPartDesc] = useState("");
  const [newPartCategory, setNewPartCategory] = useState("");
  const [newPartResults, setNewPartResults] = useState<NewPartCompatResult[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load products on mount
  useEffect(() => {
    (async () => {
      try {
        const list = await fetchProducts();
        setProducts(list);
        if (list.length > 0 && selectedProduct === "ALL") {
          setSelectedProduct(list[0].name);
        }
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  const currentProductName =
    selectedProduct === "ALL" ? null : (selectedProduct as string);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setRagResponse(null);
    try {
      const res = await sendQuery(question.trim(), currentProductName);
      setRagResponse(res);
    } catch (e: any) {
      setError(e.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadCompatExisting = async () => {
    if (!currentProductName) return;
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchProductCompat(currentProductName);
      setCompatPairs(rows);
    } catch (e: any) {
      setError(e.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckNewPart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentProductName || !newPartDesc.trim()) return;
    setLoading(true);
    setError(null);
    setNewPartResults([]);
    try {
      const payload: NewPartCompatRequest = {
        product_name: currentProductName,
        description: newPartDesc.trim(),
        category: newPartCategory || undefined,
        top_k: 10,
      };
      const results = await fetchNewPartCompat(payload);
      setNewPartResults(results);
    } catch (e: any) {
      setError(e.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const ragStats = useMemo(() => {
    if (!ragResponse) return null;
    const parts = ragResponse.context.parts || [];
    if (!parts.length) return { count: 0, maxScore: 0, avgScore: 0 };
    const scores = parts.map((p) => p.score);
    const maxScore = Math.max(...scores);
    const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;
    return { count: parts.length, maxScore, avgScore };
  }, [ragResponse]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f4f4f5",
        padding: "24px 16px",
        fontFamily: "Inter, sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: 1120,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {/* Header */}
        <header style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 24 }}>Asset Intelligence Graph-RAG</h1>
            <p style={{ margin: "4px 0", color: "#71717a", fontSize: 14 }}>
              Industrial Lathe digital thread • Graph + RAG + Compatibility
            </p>
          </div>
        </header>

        {/* Controls row */}
        <section
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            alignItems: "center",
          }}
        >
          <div>
            <label
              style={{
                display: "block",
                fontSize: 12,
                fontWeight: 500,
                color: "#52525b",
                marginBottom: 4,
              }}
            >
              Product
            </label>
            <select
              value={selectedProduct}
              onChange={(e) => setSelectedProduct(e.target.value as any)}
              style={{
                padding: "6px 10px",
                borderRadius: 8,
                border: "1px solid #d4d4d8",
                fontSize: 14,
                background: "#ffffff",
              }}
            >
              {products.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              style={{
                display: "block",
                fontSize: 12,
                fontWeight: 500,
                color: "#52525b",
                marginBottom: 4,
              }}
            >
              Mode
            </label>
            <div
              style={{
                display: "inline-flex",
                borderRadius: 999,
                border: "1px solid #e4e4e7",
                overflow: "hidden",
              }}
            >
              <button
                type="button"
                onClick={() => setMode("rag")}
                style={{
                  padding: "6px 14px",
                  border: "none",
                  background: mode === "rag" ? "#111827" : "#ffffff",
                  color: mode === "rag" ? "#ffffff" : "#111827",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                RAG Query
              </button>
              <button
                type="button"
                onClick={() => setMode("compat_existing")}
                style={{
                  padding: "6px 14px",
                  border: "none",
                  background: mode === "compat_existing" ? "#111827" : "#ffffff",
                  color: mode === "compat_existing" ? "#ffffff" : "#111827",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Compat (Existing)
              </button>
              <button
                type="button"
                onClick={() => setMode("compat_new")}
                style={{
                  padding: "6px 14px",
                  border: "none",
                  background: mode === "compat_new" ? "#111827" : "#ffffff",
                  color: mode === "compat_new" ? "#ffffff" : "#111827",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Compat (New Part)
              </button>
            </div>
          </div>
        </section>

        {error && (
          <div
            style={{
              borderRadius: 10,
              border: "1px solid #fecaca",
              background: "#fee2e2",
              padding: 12,
              fontSize: 13,
              color: "#b91c1c",
            }}
          >
            {error}
          </div>
        )}

        {/* Mode Panels */}
        {mode === "rag" && (
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1.2fr)",
              gap: 16,
            }}
          >
            {/* Left: Query input */}
            <div
              style={{
                background: "#ffffff",
                borderRadius: 12,
                border: "1px solid #e4e4e7",
                padding: 16,
              }}
            >
              <h2 style={{ fontSize: 16, margin: "0 0 8px" }}>Ask a question</h2>
              <p style={{ margin: "0 0 8px", fontSize: 13, color: "#71717a" }}>
                Natural language query over lathe assemblies, parts, specs, and
                compatibility.
              </p>
              <form onSubmit={handleAsk}>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  rows={4}
                  style={{
                    width: "100%",
                    padding: 10,
                    borderRadius: 8,
                    border: "1px solid #d4d4d8",
                    fontSize: 14,
                    resize: "vertical",
                    outline: "none",
                  }}
                  placeholder="e.g. Which spindle parts and bearings are used in the Industrial Lathe, and what compatible alternatives exist?"
                />
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginTop: 10,
                  }}
                >
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <button
                      type="submit"
                      disabled={loading}
                      style={{
                        padding: "8px 16px",
                        borderRadius: 999,
                        border: "none",
                        background: "#111827",
                        color: "#ffffff",
                        fontSize: 14,
                        cursor: "pointer",
                      }}
                    >
                      {loading ? "Thinking..." : "Run query"}
                    </button>
                    <AudioRecorder
                      onTranscription={(text) => setQuestion((prev) =>
                        prev ? prev + "\n" + text : text
                      )}
                    />
                  </div>
                </div>
              </form>
            </div>

            {/* Right: Answer + context */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div
                style={{
                  background: "#ffffff",
                  borderRadius: 12,
                  border: "1px solid #e4e4e7",
                  padding: 16,
                  minHeight: 120,
                }}
              >
                <h2 style={{ fontSize: 16, margin: "0 0 8px" }}>Answer</h2>
                {ragResponse ? (
                  <p style={{ whiteSpace: "pre-wrap", fontSize: 14, margin: 0 }}>
                    {ragResponse.answer}
                  </p>
                ) : (
                  <p style={{ fontSize: 13, color: "#a1a1aa", margin: 0 }}>
                    Run a query to see an answer.
                  </p>
                )}
              </div>

              <div
                style={{
                  background: "#ffffff",
                  borderRadius: 12,
                  border: "1px solid #e4e4e7",
                  padding: 16,
                }}
              >
                <h3 style={{ fontSize: 14, margin: "0 0 8px" }}>Retrieved Parts</h3>
                {ragStats && (
                  <div style={{ fontSize: 12, color: "#71717a", marginBottom: 6 }}>
                    {ragStats.count} parts • max score{" "}
                    {ragStats.maxScore.toFixed(3)} • avg score{" "}
                    {ragStats.avgScore.toFixed(3)}
                  </div>
                )}
                <div style={{ maxHeight: 260, overflowY: "auto", paddingRight: 4 }}>
                  {ragResponse?.context.parts.map((p) => (
                    <div
                      key={p.part_id}
                      style={{
                        borderRadius: 10,
                        border: "1px solid #e4e4e7",
                        padding: 10,
                        marginBottom: 8,
                        background: "#fafafa",
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>
                        {p.part_id} — {p.name}{" "}
                        <span style={{ color: "#71717a" }}>({p.category})</span>
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          color: "#6b7280",
                          marginTop: 2,
                          display: "flex",
                          gap: 8,
                          flexWrap: "wrap",
                        }}
                      >
                        <span>Score: {p.score.toFixed(3)}</span>
                        <span>Source: {(p as any).source}</span>
                        {p.products.length > 0 && (
                          <span>Products: {p.products.join(", ")}</span>
                        )}
                      </div>
                      <p
                        style={{
                          margin: "4px 0 4px",
                          fontSize: 13,
                          color: "#3f3f46",
                        }}
                      >
                        {p.description}
                      </p>
                      {p.specs.length > 0 && (
                        <ul
                          style={{
                            margin: 0,
                            paddingLeft: 16,
                            fontSize: 12,
                            color: "#52525b",
                          }}
                        >
                          {p.specs.map((s) => (
                            <li key={`${p.part_id}-${s.key}`}>
                              {s.key}: {String(s.value)} {s.unit}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                  {!ragResponse && (
                    <p style={{ fontSize: 12, color: "#a1a1aa" }}>
                      Retrieved parts and compatibility context will appear here.
                    </p>
                  )}
                </div>
              </div>

              <div
                style={{
                  background: "#ffffff",
                  borderRadius: 12,
                  border: "1px solid #e4e4e7",
                  padding: 16,
                }}
              >
                <h3 style={{ fontSize: 14, margin: "0 0 8px" }}>
                  Compatibility among retrieved parts
                </h3>
                {ragResponse &&
                Object.keys(ragResponse.context.compatibility || {}).length > 0 ? (
                  <div
                    style={{
                      maxHeight: 180,
                      overflowY: "auto",
                      paddingRight: 4,
                      fontSize: 12,
                    }}
                  >
                    {Object.entries(ragResponse.context.compatibility).map(
                      ([from, list]) => (
                        <div key={from} style={{ marginBottom: 6 }}>
                          <div style={{ fontWeight: 600 }}>{from}</div>
                          <ul style={{ margin: 0, paddingLeft: 16 }}>
                            {list.map((rel) => (
                              <li key={`${from}-${rel.to_id}`}>
                                ↔ {rel.to_id}: score {rel.score.toFixed(2)} —{" "}
                                {rel.explanations.join("; ")}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ),
                    )}
                  </div>
                ) : (
                  <p style={{ fontSize: 12, color: "#a1a1aa", margin: 0 }}>
                    No compatibility edges among retrieved parts yet.
                  </p>
                )}
              </div>
            </div>
          </section>
        )}

        {mode === "compat_existing" && (
          <section
            style={{
              background: "#ffffff",
              borderRadius: 12,
              border: "1px solid #e4e4e7",
              padding: 16,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 8,
              }}
            >
              <h2 style={{ fontSize: 16, margin: 0 }}>Compatibility — existing parts</h2>
              <button
                type="button"
                onClick={handleLoadCompatExisting}
                disabled={loading || !currentProductName}
                style={{
                  padding: "6px 12px",
                  borderRadius: 999,
                  border: "none",
                  background: "#111827",
                  color: "#ffffff",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                {loading ? "Loading..." : "Load compatibility"}
              </button>
            </div>
            <p style={{ fontSize: 13, color: "#71717a" }}>
              Shows precomputed compatibility pairs within the selected product.
            </p>
            <div
              style={{
                marginTop: 8,
                maxHeight: 420,
                overflowY: "auto",
              }}
            >
              {compatPairs.map((pair) => (
                <div
                  key={`${pair.part_a_id}-${pair.part_b_id}`}
                  style={{
                    borderRadius: 10,
                    border: "1px solid #e4e4e7",
                    padding: 10,
                    marginBottom: 6,
                    fontSize: 13,
                  }}
                >
                  <div style={{ fontWeight: 600 }}>
                    {pair.part_a_id} ↔ {pair.part_b_id}
                  </div>
                  <div style={{ fontSize: 12, color: "#71717a" }}>
                    {pair.part_a_name} ↔ {pair.part_b_name}
                  </div>
                  <div
                    style={{
                      marginTop: 4,
                      fontSize: 11,
                      display: "flex",
                      gap: 8,
                      flexWrap: "wrap",
                      color: "#52525b",
                    }}
                  >
                    <span>score {pair.score.toFixed(2)}</span>
                    <span>mech {pair.mechanical.toFixed(2)}</span>
                    <span>func {pair.functional.toFixed(2)}</span>
                    <span>sem {pair.semantic.toFixed(2)}</span>
                    <span>hier {pair.hierarchy.toFixed(2)}</span>
                  </div>
                  <details style={{ marginTop: 4 }}>
                    <summary style={{ fontSize: 11, cursor: "pointer" }}>
                      Explanations
                    </summary>
                    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
                      {pair.explanations.map((e, idx) => (
                        <li key={idx}>{e}</li>
                      ))}
                    </ul>
                  </details>
                </div>
              ))}
              {!compatPairs.length && (
                <p style={{ fontSize: 12, color: "#a1a1aa" }}>
                  Click &quot;Load compatibility&quot; to view pair scores.
                </p>
              )}
            </div>
          </section>
        )}

        {mode === "compat_new" && (
          <section
            style={{
              background: "#ffffff",
              borderRadius: 12,
              border: "1px solid #e4e4e7",
              padding: 16,
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1.2fr)",
              gap: 16,
            }}
          >
            {/* Input */}
            <div>
              <h2 style={{ fontSize: 16, margin: "0 0 8px" }}>
                New part compatibility check
              </h2>
              <p style={{ fontSize: 13, color: "#71717a", margin: "0 0 8px" }}>
                Describe a new part (e.g., a ballscrew or bearing) and see how well it
                matches existing parts in the selected product.
              </p>
              <form onSubmit={handleCheckNewPart}>
                <label
                  style={{
                    display: "block",
                    fontSize: 12,
                    fontWeight: 500,
                    color: "#52525b",
                    marginBottom: 4,
                  }}
                >
                  Description
                </label>
                <textarea
                  value={newPartDesc}
                  onChange={(e) => setNewPartDesc(e.target.value)}
                  rows={4}
                  style={{
                    width: "100%",
                    padding: 10,
                    borderRadius: 8,
                    border: "1px solid #d4d4d8",
                    fontSize: 14,
                    resize: "vertical",
                    outline: "none",
                    marginBottom: 8,
                  }}
                  placeholder="e.g. DFU1605 ballscrew, 16mm diameter, 5mm pitch, 650mm length, C5 double-nut"
                />
                <label
                  style={{
                    display: "block",
                    fontSize: 12,
                    fontWeight: 500,
                    color: "#52525b",
                    marginBottom: 4,
                  }}
                >
                  Category (optional)
                </label>
                <input
                  value={newPartCategory}
                  onChange={(e) => setNewPartCategory(e.target.value)}
                  placeholder="e.g. Z Axis, Spindle, Bearings"
                  style={{
                    width: "100%",
                    padding: 8,
                    borderRadius: 8,
                    border: "1px solid #d4d4d8",
                    fontSize: 13,
                    outline: "none",
                    marginBottom: 10,
                  }}
                />
                <button
                  type="submit"
                  disabled={loading || !currentProductName}
                  style={{
                    padding: "8px 16px",
                    borderRadius: 999,
                    border: "none",
                    background: "#111827",
                    color: "#ffffff",
                    fontSize: 14,
                    cursor: "pointer",
                  }}
                >
                  {loading ? "Checking..." : "Check compatibility"}
                </button>
              </form>
            </div>

            {/* Results */}
            <div>
              <h3 style={{ fontSize: 14, margin: "0 0 8px" }}>Matches</h3>
              <div
                style={{
                  maxHeight: 420,
                  overflowY: "auto",
                }}
              >
                {newPartResults.map((r) => (
                  <div
                    key={r.existing_part_id}
                    style={{
                      borderRadius: 10,
                      border: "1px solid #e4e4e7",
                      padding: 10,
                      marginBottom: 8,
                      fontSize: 13,
                      background:
                        r.score >= 0.8
                          ? "#ecfdf3"
                          : r.score >= 0.5
                          ? "#fef9c3"
                          : "#fef2f2",
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>
                      {r.existing_part_id} — {r.existing_part_name}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: "#52525b",
                        margin: "2px 0 4px",
                      }}
                    >
                      category {r.existing_part_category} • assemblies:{" "}
                      {r.assemblies.join(", ")}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        display: "flex",
                        gap: 8,
                        flexWrap: "wrap",
                        marginBottom: 4,
                      }}
                    >
                      <span>score {r.score.toFixed(2)}</span>
                      <span>mech {r.mechanical.toFixed(2)}</span>
                      <span>func {r.functional.toFixed(2)}</span>
                      <span>sem {r.semantic.toFixed(2)}</span>
                      <span>hier {r.hierarchy.toFixed(2)}</span>
                    </div>
                    <details>
                      <summary style={{ fontSize: 11, cursor: "pointer" }}>
                        Explanations
                      </summary>
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
                        {r.explanations.map((e, idx) => (
                          <li key={idx}>{e}</li>
                        ))}
                      </ul>
                    </details>
                  </div>
                ))}
                {!newPartResults.length && (
                  <p style={{ fontSize: 12, color: "#a1a1aa" }}>
                    Run a check to see the best matching parts.
                  </p>
                )}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default App;
