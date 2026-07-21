export default function SavePanel({ form, slug, seed, allPicked, dupes, saving, saveError, onSave }) {
  const canSave = allPicked && !!slug && !saving;
  return (
    <div className="pane">
      <h4><span className="n">03</span> Save</h4>
      <div className="body">
        {dupes && dupes.length > 0 && (
          <div className="alert warn">
            <b>{Math.round(dupes[0].score * 100)}% similar to “{dupes[0].slug}.”</b> {dupes[0].reason} Reuse it instead of creating a near-duplicate?
          </div>
        )}
        <div className="save-grid">
          <div className="field">
            <label>Provenance</label>
            <div className="provenance">
              <label className="radio on"><input type="radio" name="prov" checked readOnly /><span>Synthetic<small>fictional, release-free</small></span></label>
              <label className="radio"><input type="radio" name="prov" disabled /><span>Consented real<small>requires a release record · phase 2</small></span></label>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div className="kv"><span>slug</span><span>{slug || "—"}</span></div>
              <div className="kv"><span>seed</span><span>{seed}</span></div>
              <div className="kv"><span>name</span><span>{form.name || "—"}</span></div>
              <div className="kv"><span>status</span><span>card</span></div>
            </div>
            {saveError && <div className="alert warn"><b>Save failed.</b> {saveError}</div>}
            <button className="btn ok" style={{ width: "100%", justifyContent: "center" }} disabled={!canSave} onClick={onSave}>
              {saving ? "Saving…" : "Save to collection"}
            </button>
            {!slug && <div className="note"><span className="dot"></span><span>Enter a name to set the slug before saving.</span></div>}
            {slug && !allPicked && <div className="note"><span className="dot"></span><span>Pick one frame for each of the four angles to enable save.</span></div>}
            <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled>Promote to LoRA · phase 2</button>
          </div>
        </div>
      </div>
    </div>
  );
}
