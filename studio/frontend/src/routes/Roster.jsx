import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listModels } from "../api.js";
import ModelCard from "../components/ModelCard.jsx";

const FILTERS = ["All", "Female", "Male", "Card", "LoRA"];

export default function Roster() {
  const [models, setModels] = useState([]);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");

  useEffect(() => {
    listModels().then(setModels).catch((e) => setError(e.message));
  }, []);

  const shown = models.filter((m) => {
    if (query && !m.name.toLowerCase().includes(query.toLowerCase())) return false;
    if (filter === "Female" || filter === "Male") return m.gender.toLowerCase() === filter.toLowerCase();
    if (filter === "Card") return m.status === "card";
    if (filter === "LoRA") return m.status === "lora";
    return true;
  });

  return (
    <section id="roster">
      <div className="sec-head">
        <h2>The Roster</h2>
        <div className="grow"></div>
        <p>Reusable synthetic actors. One locked face and seed per model, dressed per build.</p>
      </div>

      <div className="toolbar">
        <div className="searchbox">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3-3" /></svg>
          <input
            className="inp"
            style={{ border: 0, background: "transparent", padding: 0, flex: 1 }}
            placeholder="Search talent…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {FILTERS.map((f) => (
          <span key={f} className={`chip ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>{f}</span>
        ))}
        <Link className="btn primary" to="/new">+ New model</Link>
      </div>

      {error && <div className="alert warn"><b>Could not load models.</b> {error}</div>}

      <div className="grid">
        {shown.map((m, i) => <ModelCard key={m.slug} model={m} index={i} />)}
        <Link className="new-card" to="/new">+ New model</Link>
      </div>
    </section>
  );
}
