import { useState, useLayoutEffect, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { generateDescribe, generateReference, uploadReference, pollUntilDone, saveModel, dedupCheck } from "../api.js";
import CandidateGrid from "../components/CandidateGrid.jsx";
import SavePanel from "../components/SavePanel.jsx";

const ANGLES = ["front", "34", "profile", "body"];
const EMPTY = { name: "", gender: "Female", age_band: "", race_ethnicity: "", height: "", build: "", hair: "", distinctive_face: "", distinctive_body: "", personality: "" };

// A generated sheet costs minutes to render, so it's stashed here and auto-restored
// if the user navigates away (or refreshes) before saving. Cleared on Save or Discard.
const PENDING_KEY = "moontech.pendingSheet";

function timeAgo(ts) {
  if (!ts) return "";
  const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

function genderWord(g) {
  const s = (g || "").toLowerCase();
  if (s.startsWith("f")) return "woman";
  if (s.startsWith("m")) return "man";
  return "person";
}
function assembleIdentity(f) {
  const parts = [f.race_ethnicity, f.age_band, f.build && `${f.build} build`, f.hair, f.distinctive_face, f.distinctive_body].filter(Boolean);
  return [`a synthetic ${genderWord(f.gender)}`, ...parts].join(", ");
}
function slugify(name) {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}
function buildAttributes(f) {
  return {
    race_ethnicity: f.race_ethnicity, age_band: f.age_band, height: f.height,
    build: f.build, hair: f.hair, distinctive_face: f.distinctive_face,
    distinctive_body: f.distinctive_body, personality: f.personality,
  };
}
const randSeed = () => Math.floor(Math.random() * 90000) + 10000;

// Textarea that grows to fit its content — for the free-text brief fields that
// can hold a sentence or two rather than a couple of words.
function AutoText({ value, onChange, ...rest }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el) { el.style.height = "auto"; el.style.height = `${el.scrollHeight}px`; }
  }, [value]);
  return <textarea ref={ref} className="inp" rows={1} value={value} onChange={onChange} {...rest} />;
}

export default function Console() {
  const nav = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [mode, setMode] = useState("describe");
  const [refFile, setRefFile] = useState(null);
  const [seed, setSeed] = useState(randSeed());
  const [count, setCount] = useState(4);
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState({});
  const [dupes, setDupes] = useState([]);
  const [busy, setBusy] = useState(false);
  const [genError, setGenError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [sheetTs, setSheetTs] = useState(null);
  const [resumed, setResumed] = useState(false);

  // Restore an unsaved sheet on mount, before the first paint of an empty grid.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(PENDING_KEY);
      if (!raw) return;
      const s = JSON.parse(raw);
      if (!s || !Array.isArray(s.candidates) || s.candidates.length === 0) return;
      setForm(s.form ?? EMPTY);
      setMode(s.mode ?? "describe");
      setSeed(s.seed ?? randSeed());
      setCount(s.count ?? 4);
      setCandidates(s.candidates);
      setPicked(s.picked ?? {});
      setDupes(s.dupes ?? []);
      setSheetTs(s.ts ?? Date.now());
      setResumed(true);
    } catch { /* ignore corrupt storage */ }
  }, []);

  // Persist the sheet whenever it or the picks change; skip while there's nothing
  // shot yet so we never clobber a saved sheet with an empty one.
  useEffect(() => {
    if (candidates.length === 0) return;
    try {
      localStorage.setItem(PENDING_KEY, JSON.stringify({
        v: 1, ts: sheetTs, form, mode, seed, count, candidates, picked, dupes,
      }));
    } catch { /* quota / disabled storage — non-fatal */ }
  }, [candidates, picked, dupes, form, mode, seed, count, sheetTs]);

  function clearPending() {
    try { localStorage.removeItem(PENDING_KEY); } catch { /* non-fatal */ }
  }

  function discardSheet() {
    clearPending();
    setCandidates([]); setPicked({}); setDupes([]); setResumed(false); setSheetTs(null);
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const identity = assembleIdentity(form);
  const slug = slugify(form.name);
  const allPicked = ANGLES.every((a) => picked[a]);

  async function generate() {
    setBusy(true); setGenError(null); setCandidates([]); setPicked({}); setDupes([]);
    setResumed(false); clearPending();
    try {
      let job_id;
      if (mode === "reference") {
        if (!refFile) { setGenError("choose a reference image first"); return; }
        const { ref_image } = await uploadReference(refFile);
        // Send the written description too: it shapes the body (physique, hair,
        // age) so the full-body shot matches the model, not a generic build.
        ({ job_id } = await generateReference({ ref_image, identity_string: identity, seed, count }));
      } else {
        ({ job_id } = await generateDescribe({ identity_string: identity, seed, count }));
      }
      const job = await pollUntilDone(job_id);
      if (job.status === "error") { setGenError(job.error || "generation failed"); return; }
      setSheetTs(Date.now());
      setCandidates(job.candidates);
      // Advisory near-duplicate check; needs age_band, returns [] until #16 lands.
      if (form.age_band) {
        try { const d = await dedupCheck(buildAttributes(form)); setDupes(d.matches || []); } catch { /* non-fatal */ }
      }
    } catch (e) { setGenError(e.message); }
    finally { setBusy(false); }
  }

  async function save() {
    setSaving(true); setSaveError(null);
    try {
      const res = await saveModel({
        slug, name: form.name, gender: form.gender, identity_string: identity, seed,
        attributes: buildAttributes(form),
        provenance: "synthetic",
        picked,
      });
      if (!res.ok) { setSaveError(res.reason || "save rejected"); return; }
      if (res.warning) console.warn(`Model saved but: ${res.warning}`);
      clearPending();
      nav(`/model/${slug}`);
    } catch (e) { setSaveError(e.message); }
    finally { setSaving(false); }
  }

  return (
    <section id="console">
      <div className="sec-head">
        <h2>Casting Console</h2>
        <div className="grow"></div>
        <p>Describe a look, shoot the base sheet, pick one frame per angle, save.</p>
      </div>

      <div className="console">
        <div className="pane">
          <h4><span className="n">01</span> Brief</h4>
          <div className="body">
            <div className="seg">
              <button className={mode === "describe" ? "on" : ""} onClick={() => setMode("describe")}>Describe</button>
              <button className={mode === "reference" ? "on" : ""} onClick={() => setMode("reference")}>From reference</button>
            </div>
            <div className="field-grid">
              <div className="field"><label>Name</label><input className="inp" value={form.name} onChange={set("name")} placeholder="Nadia" /></div>
              <div className="field"><label>Gender</label><input className="inp" value={form.gender} onChange={set("gender")} /></div>
              <div className="field"><label>Age band</label><input className="inp" value={form.age_band} onChange={set("age_band")} placeholder="early 30s" /></div>
              <div className="field"><label>Race / ethnicity</label><input className="inp" value={form.race_ethnicity} onChange={set("race_ethnicity")} /></div>
              <div className="field"><label>Height</label><input className="inp" value={form.height} onChange={set("height")} /></div>
              <div className="field"><label>Build</label><input className="inp" value={form.build} onChange={set("build")} placeholder="lean athletic" /></div>
              <div className="field"><label>Hair</label><input className="inp" value={form.hair} onChange={set("hair")} /></div>
              <div className="field span"><label>Distinctive face</label><AutoText value={form.distinctive_face} onChange={set("distinctive_face")} placeholder="e.g. strong brows, small scar on the bridge of the nose, freckled cheeks" /></div>
              <div className="field span"><label>Distinctive body</label><AutoText value={form.distinctive_body} onChange={set("distinctive_body")} placeholder="e.g. freckled shoulders, small wrist tattoo, faint collarbone scar" /></div>
              <div className="field span"><label>Personality</label><AutoText value={form.personality} onChange={set("personality")} placeholder="e.g. warm, quick-witted, a little guarded" /></div>
            </div>
            {mode === "reference" ? (
              <>
                <label className="drop" style={{ cursor: "pointer" }}>
                  {refFile ? <b>{refFile.name}</b> : <>Click to choose a <b>reference image</b></>}
                  <br /><span style={{ fontSize: 11 }}>seeds the look · synthetic output</span>
                  <input type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => setRefFile(e.target.files?.[0] || null)} />
                </label>
                <div className="note"><span className="dot"></span><span>The reference seeds identity; each angle is re-shot as a neutral studio frame with the same face.</span></div>
              </>
            ) : (
              <div className="note"><span className="dot"></span><span>Describe mode — the brief is enriched into a photoreal prompt at generation.</span></div>
            )}
          </div>
        </div>

        <div className="pane">
          <h4><span className="n">02</span> Base sheet <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", textTransform: "none", letterSpacing: 0, color: "var(--muted)" }}>seed {seed}</span></h4>
          <div className="body">
            <div className="sheet-head">
              <button className="btn primary" onClick={generate} disabled={busy || (mode === "describe" && !form.age_band) || (mode === "reference" && !refFile)}>{busy ? "Generating…" : `⟳ Generate ${count * 4}`}</button>
              <button className="btn ghost" onClick={() => setSeed(randSeed())} disabled={busy}>Re-roll seed</button>
              <div className="seg" style={{ width: "auto", flex: "0 0 auto" }} title="candidates per angle">
                {[2, 4, 6].map((n) => (
                  <button key={n} className={count === n ? "on" : ""} onClick={() => setCount(n)} disabled={busy}>{n}/angle</button>
                ))}
              </div>
              <span className="note" style={{ marginLeft: "auto" }}><span className="dot"></span><span>Plain underwear base — dressed per build</span></span>
            </div>
            {mode === "describe" && !form.age_band && <div className="note"><span className="dot"></span><span>Age band is required before generating.</span></div>}
            {mode === "reference" && !refFile && <div className="note"><span className="dot"></span><span>Choose a reference image before generating.</span></div>}
            {genError && <div className="alert warn"><b>Generation failed.</b> {genError}</div>}
            {resumed && candidates.length > 0 && (
              <div className="alert warn" style={{ alignItems: "center" }}>
                <span style={{ flex: 1 }}>Resumed your last unsaved shoot{sheetTs ? ` from ${timeAgo(sheetTs)}` : ""}. Pick your frames and save, or discard to start fresh.</span>
                <button className="btn ghost" onClick={discardSheet}>Discard</button>
              </div>
            )}
            {candidates.length > 0 ? (
              <CandidateGrid candidates={candidates} picked={picked} onPick={(a, f) => setPicked({ ...picked, [a]: f })} />
            ) : (
              <>
                <div className="ghost-sheet">
                  {["front", "3/4", "profile", "body"].map((a) => <div key={a} className="ghost-slot">{a}</div>)}
                </div>
                <div className="note"><span className="dot"></span><span>Fill the brief and hit Generate to shoot the base sheet.</span></div>
              </>
            )}
          </div>
        </div>

        <SavePanel form={form} slug={slug} seed={seed} allPicked={allPicked} dupes={dupes} saving={saving} saveError={saveError} onSave={save} />
      </div>

      <footer>
        <div className="legal"><span className="sh">Rails</span><span>Adults only — photoreal minors refused. Real-person references blocked without a logged AI-likeness release; celebrities and stock faces refused. Base sheets are plain underwear (wardrobe-neutral), not lingerie or nude.</span></div>
      </footer>
    </section>
  );
}
