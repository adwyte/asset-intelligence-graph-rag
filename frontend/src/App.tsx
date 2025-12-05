import React, { useEffect, useState, useMemo } from "react";
import {
  fetchProducts,
  sendQuery,
  fetchProductCompat,
  fetchNewPartCompat,
  uploadDocument,
  uploadYaml,
  ProductInfo,
  QueryResponse,
  CompatPair,
  NewPartCompatResult,
  NewPartCompatRequest,
} from "./api";

import AudioRecorder from "./components/AudioRecorder";

import "./styles.css";

type Mode = "rag" | "compat_existing" | "compat_new";

const App: React.FC = () => {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string>("ALL");

  const [mode, setMode] = useState<Mode>("rag");

  const [question, setQuestion] = useState("");
  const [ragResponse, setRagResponse] = useState<QueryResponse | null>(null);

  const [compatPairs, setCompatPairs] = useState<CompatPair[]>([]);
  const [newPartDesc, setNewPartDesc] = useState("");
  const [newPartCategory, setNewPartCategory] = useState("");
  const [newPartResults, setNewPartResults] = useState<NewPartCompatResult[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentProductName =
    selectedProduct === "ALL" ? null : selectedProduct;

  // -----------------------------
  // Load products on mount
  // -----------------------------
  useEffect(() => {
    fetchProducts()
      .then((list) => {
        setProducts(list);
      })
      .catch((err) => console.error(err));
  }, []);

  // -----------------------------
  // Handlers
  // -----------------------------

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setRagResponse(null);

    try {
      const res = await sendQuery(question.trim(), currentProductName);
      setRagResponse(res);
    } catch (err: any) {
      setError(err.message ?? "Unknown error");
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
    } catch (err: any) {
      setError(err.message ?? "Unknown error");
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
    } catch (err: any) {
      setError(err.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleUploadDoc = async (file: File) => {
    try {
      await uploadDocument(file);
      alert("Document uploaded successfully.");
    } catch (err: any) {
      alert("Upload failed: " + err.message);
    }
  };

  const handleUploadYaml = async (file: File) => {
    try {
      await uploadYaml(file);
      alert("YAML uploaded + ingested!");
    } catch (err: any) {
      alert("YAML upload failed: " + err.message);
    }
  };

  // -----------------------------
  // Markdown download
  // -----------------------------
  const downloadMarkdown = () => {
    if (!ragResponse) return;

    const md = `# Query Result\n\n**Question:** ${ragResponse.context.question}\n\n## Answer\n${ragResponse.answer}\n`;
    const blob = new Blob([md], { type: "text/markdown" });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "query_result.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  // -----------------------------
  // Stats
  // -----------------------------
  const ragStats = useMemo(() => {
    if (!ragResponse) return null;
    const parts = ragResponse.context.parts || [];
    if (!parts.length) return null;

    const scores = parts.map((p) => p.score);
    return {
      count: parts.length,
      maxScore: Math.max(...scores),
      avgScore: scores.reduce((a, b) => a + b, 0) / parts.length,
    };
  }, [ragResponse]);

  // =======================================================
  //                    UI Rendering
  // =======================================================

  return (
    <div className="app-container">

      {/* HEADER SECTION */}
      <header style={{ textAlign: "center", marginBottom: 32 }}>
        <h1 style={{ fontSize: 32, marginBottom: 6 }}>
          Asset Intelligence Graph-RAG
        </h1>
        <p className="text-muted" style={{ fontSize: 15 }}>
          Industrial Lathe Digital Thread • Graph + RAG + Compatibility
        </p>
      </header>
      {/* CONTROL PANEL */}
      <section
        className="controls-wrapper"
      >
        {/* Product Dropdown */}
        <div>
          <label className="small">Product   </label>
          <select
            value={selectedProduct}
            onChange={(e) => setSelectedProduct(e.target.value)}
            className="input"
            style={{ width: 250 }}
          >
            <option value="ALL">SELECT Product</option>
            {products.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Mode Switch */}
        <div>
          <label className="small">Mode    </label>
          <div className="mode-switch">
            <button
              className={mode === "rag" ? "active" : ""}
              onClick={() => setMode("rag")}
            >
              RAG Query
            </button>

            <button
              className={mode === "compat_existing" ? "active" : ""}
              onClick={() => setMode("compat_existing")}
            >
              Compatibility (Existing)
            </button>

            <button
              className={mode === "compat_new" ? "active" : ""}
              onClick={() => setMode("compat_new")}
            >
              Compatibility (New Part)
            </button>
          </div>
        </div>
      </section>

      {/* ERROR BANNER */}
      {error && (
        <div
          className="card"
          style={{
            borderColor: "#ffb3b3",
            background: "#ffe5e5",
            textAlign: "center",
          }}
        >
          <span style={{ color: "#a00" }}>{error}</span>
        </div>
      )}

      {/* -----------------------------------------------------------
          MODE: RAG QUERY
      ----------------------------------------------------------- */}
      {mode === "rag" && (
        <section className="grid-2" style={{ marginTop: 16 }}>
          {/* LEFT SIDE — QUERY INPUT */}
          <div className="card">
            <h2 style={{ fontSize: 20 }}>Ask a question</h2>
            <p className="small text-muted">
              Ask about assemblies, parts, specs, compatibility, documents.
            </p>

            <form onSubmit={handleAsk} style={{ marginTop: 10 }}>
              <textarea
                className="input"
                rows={4}
                placeholder="e.g. Which spindle parts and bearings are used, and what alternatives exist?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <div className="row" style={{ marginTop: 12 }}>
                <button className="button" type="submit" disabled={loading}>
                  {loading ? "Thinking..." : "Run query"}
                </button>
                <AudioRecorder
                  onTranscription={(txt) =>
                    setQuestion((p) => (p ? p + "\n" + txt : txt))
                  }
                />
              </div>
            </form>

            {/* Upload Section */}
            <div style={{ marginTop: 24 }}>
              <h3 style={{ fontSize: 16, marginBottom: 4 }}>Upload Documents</h3>
              <p className="small text-muted">
                Upload <strong>BOMs, datasheets, manuals, images, PDFs</strong>  
                (stored, not ingested yet).  
                Upload a <strong>YAML</strong> file to auto-ingest a new product.
              </p>

              <div className="row" style={{ marginTop: 12 }}>
                <label className="button secondary small" style={{ cursor: "pointer" }}>
                  Upload Docs
                  <input
                    type="file"
                    style={{ display: "none" }}
                    onChange={(e) =>
                      e.target.files?.[0] && handleUploadDoc(e.target.files[0])
                    }
                  />
                </label>

                <label className="button secondary small" style={{ cursor: "pointer" }}>
                  Upload YAML
                  <input
                    type="file"
                    accept=".yaml,.yml"
                    style={{ display: "none" }}
                    onChange={(e) =>
                      e.target.files?.[0] && handleUploadYaml(e.target.files[0])
                    }
                  />
                </label>
              </div>
            </div>

            {/* Export markdown */}
            {ragResponse && (
              <div style={{ marginTop: 20 }}>
                <button className="button secondary small" onClick={downloadMarkdown}>
                  Download .md
                </button>
              </div>
            )}
          </div>

          {/* RIGHT SIDE — ANSWER + GRAPH + RESULTS */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Answer */}
            <div className="card">
              <h2 style={{ fontSize: 20, marginBottom: 8 }}>Answer</h2>
              {ragResponse ? (
                <p style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>
                  {ragResponse.answer}
                </p>
              ) : (
                <p className="small text-muted">Run a query to view results.</p>
              )}
            </div>

            {/* Retrieved Parts */}
            <div className="card">
              <h3 style={{ fontSize: 16 }}>Retrieved Parts</h3>
              {ragStats && (
                <p className="small text-muted">
                  {ragStats.count} parts • max {ragStats.maxScore.toFixed(3)} • avg{" "}
                  {ragStats.avgScore.toFixed(3)}
                </p>
              )}

              <div className="scroll">
                {ragResponse?.context.parts?.map((p) => (
                  <div key={p.part_id} className="card" style={{ background: "#fafafa" }}>
                    <div style={{ fontWeight: 600 }}>
                      {p.part_id} — {p.name}{" "}
                      <span className="text-muted">({p.category})</span>
                    </div>
                    <div className="small" style={{ marginTop: 4 }}>
                      Score {p.score.toFixed(3)} • {p.source}
                    </div>
                    <p style={{ marginTop: 6 }}>{p.description}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Compatibility */}
            <div className="card">
              <h3 style={{ fontSize: 16 }}>Compatibility among retrieved parts</h3>
              {ragResponse &&
              Object.keys(ragResponse.context.compatibility || {}).length > 0 ? (
                <div className="scroll">
                  {Object.entries(ragResponse.context.compatibility).map(
                    ([from, list]) => (
                      <div key={from} style={{ marginBottom: 8 }}>
                        <div style={{ fontWeight: 600 }}>{from}</div>
                        <ul className="small" style={{ marginLeft: 20 }}>
                          {list.map((rel) => (
                            <li key={`${from}-${rel.to_id}`}>
                              ↔ {rel.to_id} — {rel.score.toFixed(2)}  
                              • {rel.explanations.join("; ")}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <p className="small text-muted">No compatibility edges yet.</p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* -----------------------------------------------------------
          MODE: EXISTING COMPAT
      ----------------------------------------------------------- */}
      {mode === "compat_existing" && (
        <section className="card" style={{ marginTop: 20 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2 style={{ fontSize: 20 }}>Compatibility — existing parts</h2>
            <button
              className="button small"
              onClick={handleLoadCompatExisting}
              disabled={loading || !currentProductName}
            >
              {loading ? "Loading..." : "Load Compatibility"}
            </button>
          </div>

          <div className="scroll-tall" style={{ marginTop: 16 }}>
            {compatPairs.map((pair) => (
              <div key={`${pair.part_a_id}-${pair.part_b_id}`} className="card">
                <div style={{ fontWeight: 600 }}>
                  {pair.part_a_id} ↔ {pair.part_b_id}
                </div>
                <div className="small">{pair.part_a_name} ↔ {pair.part_b_name}</div>
                <div className="small" style={{ marginTop: 4 }}>
                  score {pair.score.toFixed(2)} • mech {pair.mechanical.toFixed(2)} • func{" "}
                  {pair.functional.toFixed(2)} • sem {pair.semantic.toFixed(2)} • hier{" "}
                  {pair.hierarchy.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* -----------------------------------------------------------
          MODE: NEW PART COMPAT
      ----------------------------------------------------------- */}
      {mode === "compat_new" && (
        <section className="grid-2" style={{ marginTop: 20 }}>
          {/* Input */}
          <div className="card">
            <h2 style={{ fontSize: 20 }}>New Part Compatibility</h2>
            <p className="small text-muted">
              Describe a part and check compatibility with the selected product’s parts.
            </p>

            <form onSubmit={handleCheckNewPart} style={{ marginTop: 16 }}>
              <label className="small">Description</label>
              <textarea
                className="input"
                rows={4}
                value={newPartDesc}
                onChange={(e) => setNewPartDesc(e.target.value)}
              />

              <label className="small" style={{ marginTop: 12 }}>
                Category (optional)
              </label>
              <input
                className="input"
                value={newPartCategory}
                onChange={(e) => setNewPartCategory(e.target.value)}
              />

              <button className="button" style={{ marginTop: 16 }}>
                Check Compatibility
              </button>
            </form>
          </div>

          {/* Results */}
          <div className="card">
            <h3 style={{ fontSize: 16 }}>Results</h3>

            <div className="scroll-tall" style={{ marginTop: 12 }}>
              {newPartResults.map((r) => (
                <div
                  key={r.existing_part_id}
                  className={`card ${
                    r.score >= 0.8
                      ? "compat-high"
                      : r.score >= 0.5
                      ? "compat-medium"
                      : "compat-low"
                  }`}
                >
                  <div style={{ fontWeight: 600 }}>
                    {r.existing_part_id} — {r.existing_part_name}
                  </div>
                  <div className="small">
                    {r.existing_part_category} • {r.assemblies.join(", ")}
                  </div>

                  <div className="small" style={{ marginTop: 4 }}>
                    score {r.score.toFixed(2)} • mech {r.mechanical.toFixed(2)} • func{" "}
                    {r.functional.toFixed(2)} • sem {r.semantic.toFixed(2)} • hier{" "}
                    {r.hierarchy.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default App;
