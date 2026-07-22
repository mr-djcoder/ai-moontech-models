import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { getModel, deleteModel, imageUrl } from "../api.js";

const ANGLE_LABEL = { "front.png": "front", "34.png": "3/4", "profile.png": "profile", "body.png": "body" };

export default function ModelDetail() {
  const { slug } = useParams();
  const nav = useNavigate();
  const [model, setModel] = useState(null);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  useEffect(() => {
    getModel(slug).then(setModel).catch((e) => setError(e.message));
  }, [slug]);

  function closeConfirm() {
    if (deleting) return;
    setConfirming(false); setTyped(""); setDeleteError(null);
  }

  // The confirm label uppercases the slug via CSS, so accept any case (+ stray
  // whitespace) rather than forcing an exact lowercase match the user can't see.
  const confirmMatches = typed.trim().toLowerCase() === (slug || "").toLowerCase();

  async function confirmDelete() {
    if (!confirmMatches || deleting) return;
    setDeleting(true); setDeleteError(null);
    try {
      await deleteModel(slug);
      nav("/");
    } catch (e) {
      setDeleteError(e.message);
      setDeleting(false);
    }
  }

  if (error) return <section><div className="sec-head"><h2>Not found</h2></div><div className="alert warn">{error}</div><Link className="btn" to="/">← Roster</Link></section>;
  if (!model) return <section><div className="sec-head"><h2>Loading…</h2></div></section>;

  return (
    <section>
      <div className="sec-head">
        <h2>{model.name}</h2>
        <div className="grow"></div>
        <Link className="btn primary" to={`/model/${slug}/train`}>Promote to LoRA →</Link>
        <button className="btn danger ghost" onClick={() => setConfirming(true)}>Delete</button>
        <Link className="btn ghost" to="/">← Roster</Link>
      </div>

      <div className="console" style={{ gridTemplateColumns: "1fr 280px" }}>
        <div className="pane">
          <h4>Reference sheet</h4>
          <div className="body">
            <div className="sheet">
              {model.reference_images.map((p) => {
                const file = p.split("/").pop();
                return (
                  <div key={p} className="frame" onClick={() => setZoom(imageUrl(model.slug, p))}>
                    <img src={imageUrl(model.slug, p)} alt={ANGLE_LABEL[file] || file} />
                    <span className="fl">{ANGLE_LABEL[file] || file}</span>
                  </div>
                );
              })}
            </div>
            <div className="note"><span className="dot"></span><span>Neutral reference. Re-seed from these for any wardrobe or expression per ad.</span></div>
          </div>
        </div>

        <div className="pane">
          <h4>Identity</h4>
          <div className="body">
            <div className="note"><span className="dot"></span><span>{model.identity_string}</span></div>
            <div>
              <div className="kv"><span>slug</span><span>{model.slug}</span></div>
              <div className="kv"><span>seed</span><span>{model.seed}</span></div>
              <div className="kv"><span>gender</span><span>{model.gender}</span></div>
              <div className="kv"><span>status</span><span>{model.status}</span></div>
              <div className="kv"><span>provenance</span><span>{model.provenance}</span></div>
              <div className="kv"><span>created</span><span>{model.created}</span></div>
            </div>
          </div>
        </div>
      </div>

      {zoom && (
        <div
          onClick={() => setZoom(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(3,3,8,.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999, cursor: "zoom-out" }}
        >
          <img src={zoom} alt="enlarged" style={{ maxWidth: "90vw", maxHeight: "90vh", borderRadius: 12 }} />
        </div>
      )}

      {confirming && (
        <div
          onClick={closeConfirm}
          style={{ position: "fixed", inset: 0, background: "rgba(3,3,8,.85)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999 }}
        >
          <div className="pane" onClick={(e) => e.stopPropagation()} style={{ width: 400, maxWidth: "90vw" }}>
            <h4>Delete {model.name}?</h4>
            <div className="body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="note"><span className="dot"></span><span>This permanently removes the <b>models/{slug}/</b> folder from disk. This cannot be undone.</span></div>
              <div className="field">
                <label>Type <b>{slug}</b> to confirm</label>
                <input
                  className="inp"
                  autoFocus
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") confirmDelete(); }}
                  placeholder={slug}
                />
              </div>
              {deleteError && <div className="alert warn"><span>{deleteError}</span></div>}
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button className="btn ghost" onClick={closeConfirm} disabled={deleting}>Cancel</button>
                <button className="btn danger" onClick={confirmDelete} disabled={!confirmMatches || deleting}>
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
