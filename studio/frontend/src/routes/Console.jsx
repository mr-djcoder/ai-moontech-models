import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { generateDescribe, pollUntilDone, saveModel } from "../api.js";
import CandidateGrid from "../components/CandidateGrid.jsx";
import SavePanel from "../components/SavePanel.jsx";

const ANGLES = ["front", "34", "profile", "body"];
const EMPTY = { name: "", gender: "Female", age_band: "", race_ethnicity: "", height: "", build: "", hair: "", distinctive_face: "", distinctive_body: "", personality: "" };

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
const randSeed = () => Math.floor(Math.random() * 90000) + 10000;

export default function Console() {
  const nav = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [seed, setSeed] = useState(randSeed());
  const [candidates, setCandidates] = useState([]);
  const [picked, setPicked] = useState({});
  const [busy, setBusy] = useState(false);
  const [genError, setGenError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const identity = assembleIdentity(form);
  const slug = slugify(form.name);
  const allPicked = ANGLES.every((a) => picked[a]);

  async function generate() {
    setBusy(true); setGenError(null); setCandidates([]); setPicked({});
    try {
      const { job_id } = await generateDescribe({ identity_string: identity, seed, count: 2 });
      const job = await pollUntilDone(job_id);
      if (job.status === "error") { setGenError(job.error || "generation failed"); return; }
      setCandidates(job.candidates);
    } catch (e) { setGenError(e.message); }
    finally { setBusy(false); }
  }

  async function save() {
    setSaving(true); setSaveError(null);
    try {
      const res = await saveModel({
        slug, name: form.name, gender: form.gender, identity_string: identity, seed,
        attributes: {
          race_ethnicity: form.race_ethnicity, age_band: form.age_band, height: form.height,
          build: form.build, hair: form.hair, distinctive_face: form.distinctive_face,
          distinctive_body: form.distinctive_body, personality: form.personality,
        },
        provenance: "synthetic",
        picked,
      });
      if (!res.ok) { setSaveError(res.reason || "save rejected"); return; }
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
              <button className="on">Describe</button>
              <button disabled title="needs image upload — phase 2">From reference</button>
            </div>
            <div className="field"><label>Name</label><input className="inp" value={form.name} onChange={set("name")} placeholder="Nadia" /></div>
            <div className="row2">
              <div className="field"><label>Gender</label><input className="inp" value={form.gender} onChange={set("gender")} /></div>
              <div className="field"><label>Age band</label><input className="inp" value={form.age_band} onChange={set("age_band")} placeholder="early 30s" /></div>
            </div>
            <div className="field"><label>Race / ethnicity</label><input className="inp" value={form.race_ethnicity} onChange={set("race_ethnicity")} /></div>
            <div className="row2">
              <div className="field"><label>Height</label><input className="inp" value={form.height} onChange={set("height")} /></div>
              <div className="field"><label>Build</label><input className="inp" value={form.build} onChange={set("build")} placeholder="lean athletic" /></div>
            </div>
            <div className="field"><label>Hair</label><input className="inp" value={form.hair} onChange={set("hair")} /></div>
            <div className="field"><label>Distinctive face</label><input className="inp" value={form.distinctive_face} onChange={set("distinctive_face")} /></div>
            <div className="field"><label>Distinctive body</label><input className="inp" value={form.distinctive_body} onChange={set("distinctive_body")} /></div>
            <div className="field"><label>Personality</label><input className="inp" value={form.personality} onChange={set("personality")} /></div>
            <div className="drop">Reference-image seeding<br /><span style={{ fontSize: 11 }}>phase 2 · describe mode only for now</span></div>
          </div>
        </div>

        <div className="pane">
          <h4><span className="n">02</span> Base sheet <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", textTransform: "none", letterSpacing: 0, color: "var(--muted)" }}>seed {seed}</span></h4>
          <div className="body">
            <div className="sheet-head">
              <button className="btn primary" onClick={generate} disabled={busy || !form.age_band}>{busy ? "Generating…" : "⟳ Generate 8"}</button>
              <button className="btn ghost" onClick={() => setSeed(randSeed())} disabled={busy}>Re-roll seed</button>
              <span className="note" style={{ marginLeft: "auto" }}><span className="dot"></span><span>Plain underwear base — dressed per build</span></span>
            </div>
            {!form.age_band && <div className="note"><span className="dot"></span><span>Age band is required before generating.</span></div>}
            {genError && <div className="alert warn"><b>Generation failed.</b> {genError}</div>}
            {candidates.length > 0
              ? <CandidateGrid candidates={candidates} picked={picked} onPick={(a, f) => setPicked({ ...picked, [a]: f })} />
              : <div className="note"><span className="dot"></span><span>Fill the brief and hit Generate to shoot the base sheet (front · 3/4 · profile · body).</span></div>}
          </div>
        </div>

        <SavePanel form={form} slug={slug} seed={seed} allPicked={allPicked} saving={saving} saveError={saveError} onSave={save} />
      </div>

      <footer>
        <div className="legal"><span className="sh">Rails</span><span>Adults only — photoreal minors refused. Real-person references blocked without a logged AI-likeness release; celebrities and stock faces refused. Base sheets are plain underwear (wardrobe-neutral), not lingerie or nude.</span></div>
      </footer>
    </section>
  );
}
