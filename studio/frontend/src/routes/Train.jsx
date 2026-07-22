import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { generateDataset, pollUntilDone } from "../api.js";
import CandidateGrid from "../components/CandidateGrid.jsx";

const KEEP_MIN = 15;

export default function Train() {
  const { slug } = useParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [kept, setKept] = useState(() => new Set());

  async function run() {
    setBusy(true); setError(null); setCandidates([]); setKept(new Set());
    try {
      const { job_id } = await generateDataset(slug, 40);
      const job = await pollUntilDone(job_id);
      if (job.status === "error") { setError(job.error || "dataset failed"); return; }
      setCandidates(job.candidates || []);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function toggle(filename) {
    setKept((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  }

  return (
    <section id="train">
      <div className="sec-head">
        <h2>Train LoRA — {slug}</h2>
        <div className="grow"></div>
        <Link className="btn ghost" to={`/model/${slug}`}>← Model</Link>
      </div>
      <div className="pane">
        <div className="body">
          <button className="btn primary" onClick={run} disabled={busy}>
            {busy ? "Generating dataset…" : "⟳ Generate dataset (40)"}
          </button>
          {error && <div className="alert warn"><b>Failed.</b> {error}</div>}
          {candidates.length > 0 && (
            <>
              <div className="note">
                <span className="dot"></span>
                <span>Pick the on-identity keepers ({kept.size} kept · need ≥{KEEP_MIN}).</span>
              </div>
              <CandidateGrid
                candidates={candidates}
                selected={kept}
                onPick={(_, c) => toggle(c.filename)}
              />
              <button className="btn ok" disabled title="Phase B">
                Train LoRA · {kept.size} images
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
