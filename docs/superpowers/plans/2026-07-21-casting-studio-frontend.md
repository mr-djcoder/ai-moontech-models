# Casting Studio Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React + Vite Studio frontend so a user can browse the model roster and create a new synthetic model end-to-end (describe → generate → pick one frame per angle → save) against the existing FastAPI backend.

**Architecture:** A Vite/React SPA (dev server :5173) calls the FastAPI backend (:8800). The backend gains two additive changes — CORS for the dev origin and a static route serving saved model images from disk. The frontend ports the approved MoonTech mockup's CSS verbatim and translates its markup into wired components across three routes: Roster (`/`), Casting Console (`/new`), Model detail (`/model/:slug`).

**Tech Stack:** Python 3.12 / FastAPI / pytest (backend, existing). React 18 + Vite 5 + react-router-dom 6 (frontend, new). Node 26 / npm 11.

## Global Constraints

- Backend is localhost-only, no auth. Do not add auth, deployment, or non-localhost config.
- All 59 existing backend tests MUST stay green. Backend changes are additive only.
- Backend base URL for the frontend: `http://127.0.0.1:8800`. Dev origin allowed by CORS: `http://localhost:5173`.
- v1 scope: describe-mode create flow only. Reference-mode segment, dedup banner, likeness slider, and "Promote to LoRA" are rendered but inert (per spec).
- No turntable / 360 view. No expression generation.
- Port `studio/frontend/design/mockup.html`'s `<style>` block verbatim into `src/styles.css`. Match its class names so the ported CSS applies unchanged.
- Reference source of truth for design + markup: `studio/frontend/design/mockup.html`.
- Spec: `docs/superpowers/specs/2026-07-21-casting-studio-frontend-design.md`.
- Save contract: `POST /models` requires `picked` to contain exactly one frame for EACH of the four angles `front`, `34`, `profile`, `body`. `copy_reference_frames` KeyErrors if any is missing.
- `count` on `POST /generate` is frames-PER-ANGLE. Use `count: 2` so 4 angles × 2 = 8 candidates total (matches the mockup's "Generate 8" / 8-frame sheet).

---

### Task 1: Backend — CORS for the dev origin

**Files:**
- Modify: `studio/backend/app/main.py` (add CORS middleware near app creation, after line 24 `app = FastAPI(...)`)
- Test: `studio/backend/tests/test_api.py` (append)

**Interfaces:**
- Consumes: existing `app` from `app.main`.
- Produces: the running app now returns `access-control-allow-origin: http://localhost:5173` for requests carrying that `Origin`.

- [ ] **Step 1: Write the failing test**

Append to `studio/backend/tests/test_api.py`:

```python
def test_cors_allows_dev_origin():
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd studio/backend && ./.venv/Scripts/python.exe -m pytest tests/test_api.py::test_cors_allows_dev_origin -v`
Expected: FAIL — `access-control-allow-origin` header absent (KeyError/None).

- [ ] **Step 3: Add the middleware**

In `studio/backend/app/main.py`, add the import near the other fastapi import:

```python
from fastapi.middleware.cors import CORSMiddleware
```

Immediately after `app = FastAPI(title="Virtual Model Studio backend")` add:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd studio/backend && ./.venv/Scripts/python.exe -m pytest tests/test_api.py::test_cors_allows_dev_origin -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `cd studio/backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass (60 now).

- [ ] **Step 6: Commit**

```bash
git add studio/backend/app/main.py studio/backend/tests/test_api.py
git commit -m "feat(backend): allow CORS from the Vite dev origin"
```

---

### Task 2: Backend — serve saved model images

**Files:**
- Modify: `studio/backend/app/main.py` (add `import os`; add a route; reuse `MODELS_ROOT` already imported)
- Test: `studio/backend/tests/test_api.py` (append)

**Interfaces:**
- Consumes: `MODELS_ROOT` from `app.config` (already imported in main), `HTTPException` (already imported).
- Produces: `GET /models/{slug}/reference/{filename}` → 200 + `FileResponse` for an existing reference image; 404 for a missing file or any path-traversal attempt. The frontend reads reference images from `http://127.0.0.1:8800/models/<slug>/reference/<file>`.

The fixture `models/jess/reference/front.png` exists and is committed — the tests use it.

- [ ] **Step 1: Write the failing tests**

Append to `studio/backend/tests/test_api.py`:

```python
def test_serves_existing_reference_image():
    resp = client.get("/models/jess/reference/front.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 1000


def test_missing_reference_image_404():
    resp = client.get("/models/jess/reference/does-not-exist.png")
    assert resp.status_code == 404


def test_reference_image_rejects_traversal():
    resp = client.get("/models/jess/reference/..%2f..%2fcard.json")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd studio/backend && ./.venv/Scripts/python.exe -m pytest tests/test_api.py -k reference -v`
Expected: FAIL — route does not exist (404 for the existing image too, and the traversal test may 200 or error).

- [ ] **Step 3: Implement the route**

In `studio/backend/app/main.py` add near the top imports:

```python
import os
from fastapi.responses import FileResponse
```

Add this route (place it AFTER the existing `get_model` route so the more specific path is registered alongside the others):

```python
@app.get("/models/{slug}/reference/{filename}")
def model_reference_image(slug: str, filename: str):
    base = (MODELS_ROOT / slug / "reference").resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base) + os.sep) or not target.is_file():
        raise HTTPException(status_code=404, detail="reference image not found")
    return FileResponse(target)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd studio/backend && ./.venv/Scripts/python.exe -m pytest tests/test_api.py -k reference -v`
Expected: all three PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `cd studio/backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all pass (63 now).

- [ ] **Step 6: Commit**

```bash
git add studio/backend/app/main.py studio/backend/tests/test_api.py
git commit -m "feat(backend): serve saved model reference images with traversal guard"
```

---

### Task 3: Frontend — scaffold, styles, api client, app shell

**Files:**
- Create: `studio/frontend/package.json`
- Create: `studio/frontend/vite.config.js`
- Create: `studio/frontend/index.html`
- Create: `studio/frontend/.gitignore`
- Create: `studio/frontend/src/main.jsx`
- Create: `studio/frontend/src/App.jsx`
- Create: `studio/frontend/src/styles.css` (ported from `studio/frontend/design/mockup.html`)
- Create: `studio/frontend/src/api.js`

**Interfaces:**
- Produces (consumed by later tasks):
  - `src/api.js` exports:
    - `listModels(): Promise<Card[]>`
    - `getModel(slug): Promise<Card>`
    - `generateDescribe({ identity_string, seed, count }): Promise<{job_id}>`
    - `pollUntilDone(jobId): Promise<JobStatus>` (loops until status !== "running")
    - `saveModel(payload): Promise<SaveResponse>`
    - `dedupCheck(attributes): Promise<{matches: []}>`
    - `imageUrl(slug, refPath): string` — refPath is a card `reference_images` entry like `"reference/front.png"`.
  - `src/App.jsx` default export: the router shell with `<Outlet/>` and the sticky header. Routes are wired here.
  - Route components are imported from `./routes/Roster.jsx`, `./routes/Console.jsx`, `./routes/ModelDetail.jsx` (created in later tasks). For THIS task, create tiny placeholder versions inline so the app builds.

Types (from backend schema, for reference):
- `Card`: `{ slug, name, gender, status, identity_string, seed, attributes, base_wardrobe, reference_images: string[], provenance, release, created }`
- `Attributes`: `{ race_ethnicity, age_band, height, build, hair, distinctive_face, distinctive_body, personality }`
- `Candidate`: `{ url, filename, subfolder, angle, index }`
- `JobStatus`: `{ status: "running"|"done"|"error", candidates: Candidate[], error }`

- [ ] **Step 1: Create `studio/frontend/package.json`**

```json
{
  "name": "moontech-casting-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.8"
  }
}
```

- [ ] **Step 2: Create `studio/frontend/vite.config.js`**

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
```

- [ ] **Step 3: Create `studio/frontend/index.html`**

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>MoonTech Casting</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Create `studio/frontend/.gitignore`**

```
node_modules
dist
```

- [ ] **Step 5: Create `studio/frontend/src/styles.css`**

Copy the ENTIRE contents of the `<style>...</style>` block from `studio/frontend/design/mockup.html` (the CSS between the tags, not the tags themselves) into this file verbatim. Do not edit the rules. This is the MoonTech theme the components depend on.

- [ ] **Step 6: Create `studio/frontend/src/api.js`**

```js
const API = "http://127.0.0.1:8800";

async function jget(path) {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`GET ${path} -> ${r.status}`);
  return r.json();
}

async function jpost(path, body) {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${path} -> ${r.status}`);
  return r.json();
}

export const listModels = () => jget("/models");
export const getModel = (slug) => jget(`/models/${slug}`);

export const generateDescribe = ({ identity_string, seed, count }) =>
  jpost("/generate", { mode: "describe", identity_string, seed, count });

export const saveModel = (payload) => jpost("/models", payload);
export const dedupCheck = (attributes) => jpost("/dedup-check", { attributes });

export const imageUrl = (slug, refPath) => `${API}/models/${slug}/${refPath}`;

export async function pollUntilDone(jobId, { interval = 800, tries = 600 } = {}) {
  for (let i = 0; i < tries; i++) {
    const job = await jget(`/jobs/${jobId}`);
    if (job.status !== "running") return job;
    await new Promise((res) => setTimeout(res, interval));
  }
  throw new Error("job timed out");
}
```

- [ ] **Step 7: Create placeholder route components**

Create `studio/frontend/src/routes/Roster.jsx`:

```jsx
export default function Roster() {
  return <section><div className="sec-head"><h2>The Roster</h2></div><p>Roster — coming in Task 4.</p></section>;
}
```

Create `studio/frontend/src/routes/Console.jsx`:

```jsx
export default function Console() {
  return <section><div className="sec-head"><h2>Casting Console</h2></div><p>Console — coming in Task 6.</p></section>;
}
```

Create `studio/frontend/src/routes/ModelDetail.jsx`:

```jsx
export default function ModelDetail() {
  return <section><div className="sec-head"><h2>Model</h2></div><p>Detail — coming in Task 5.</p></section>;
}
```

- [ ] **Step 8: Create `studio/frontend/src/App.jsx`**

Port the mockup header verbatim (the `<header class="top">` block). Nav links go to `/` and `/new`.

```jsx
import { NavLink, Outlet } from "react-router-dom";

export default function App() {
  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="brand">
            <span className="mark" aria-hidden="true"><span className="moon"></span></span>
            <span>MoonTech Casting<small>virtual talent studio</small></span>
          </div>
          <nav className="tabs">
            <NavLink to="/" end className={({ isActive }) => (isActive ? "on" : "")}>Roster</NavLink>
            <NavLink to="/new" className={({ isActive }) => (isActive ? "on" : "")}>Casting console</NavLink>
          </nav>
        </div>
      </header>
      <main className="wrap">
        <Outlet />
      </main>
    </>
  );
}
```

- [ ] **Step 9: Create `studio/frontend/src/main.jsx`**

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App.jsx";
import Roster from "./routes/Roster.jsx";
import Console from "./routes/Console.jsx";
import ModelDetail from "./routes/ModelDetail.jsx";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Roster /> },
      { path: "new", element: <Console /> },
      { path: "model/:slug", element: <ModelDetail /> },
    ],
  },
]);

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
```

- [ ] **Step 10: Install and boot**

Run: `cd studio/frontend && npm install`
Then run the dev server (background): `cd studio/frontend && npm run dev`
Expected: Vite prints `Local: http://localhost:5173/`.

- [ ] **Step 11: Manual verification**

Ensure the backend is running (`cd studio/backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8800`). Open `http://localhost:5173/` in a browser (or drive with the browser tool). Expected: the MoonTech dark theme renders, the sticky header shows the brand + two nav tabs, and the Roster placeholder text is visible. Click "Casting console" → URL becomes `/new`, Console placeholder shows. No console errors.

- [ ] **Step 12: Commit**

```bash
git add studio/frontend
git commit -m "feat(frontend): scaffold Vite+React app shell, ported theme, api client"
```

---

### Task 4: Frontend — Roster view

**Files:**
- Create: `studio/frontend/src/components/ModelCard.jsx`
- Modify: `studio/frontend/src/routes/Roster.jsx` (replace placeholder)

**Interfaces:**
- Consumes: `listModels`, `imageUrl` from `../api.js`; `Card` shape.
- Produces: a working roster. `ModelCard` takes `{ model, index }` and renders one `.card`. Clicking a card navigates to `/model/:slug`; "+ New model" navigates to `/new`.

- [ ] **Step 1: Create `studio/frontend/src/components/ModelCard.jsx`**

Ports the mockup `.card` markup. Thumbnail is the model's front reference image; falls back to a tinted panel if it fails to load.

```jsx
import { Link } from "react-router-dom";
import { imageUrl } from "../api.js";

export default function ModelCard({ model, index }) {
  const front = model.reference_images?.find((p) => p.endsWith("front.png")) || model.reference_images?.[0];
  const stamp = model.status === "lora" ? "lora" : "card";
  return (
    <Link className="card" to={`/model/${model.slug}`} style={{ textDecoration: "none", color: "inherit" }}>
      <div className="shot">
        <span className="frameno">A{String(index + 1).padStart(2, "0")}</span>
        <span className={`stamp ${stamp}`}>{stamp === "lora" ? "LoRA" : "CARD"}</span>
        {front && <img src={imageUrl(model.slug, front)} alt={model.name} />}
      </div>
      <div className="card-body">
        <h3>{model.name}</h3>
        <div className="sub">seed {model.seed} · {model.provenance}</div>
        <div className="tags">
          <span className="tag">{model.gender}</span>
          {model.attributes?.age_band && <span className="tag">{model.attributes.age_band}</span>}
          {model.attributes?.build && <span className="tag">{model.attributes.build}</span>}
        </div>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Replace `studio/frontend/src/routes/Roster.jsx`**

Ports the mockup roster section: `.sec-head`, `.toolbar` (search box + gender/status filter chips, client-side), the `.grid`, and the "+ New model" card. Search filters by name; chips filter by gender/status.

```jsx
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
```

- [ ] **Step 3: Manual verification**

With backend + dev server running, open `http://localhost:5173/`. Expected: two cards (Jess, Steven) with real photo thumbnails from the backend. Type "jess" in search → only Jess shows. Click "Male" chip → only Steven. Click a card → navigates to `/model/steven` (placeholder for now). Click "+ New model" → `/new`.

- [ ] **Step 4: Commit**

```bash
git add studio/frontend/src/routes/Roster.jsx studio/frontend/src/components/ModelCard.jsx
git commit -m "feat(frontend): roster view with real thumbnails, search, and filters"
```

---

### Task 5: Frontend — Model detail view

**Files:**
- Modify: `studio/frontend/src/routes/ModelDetail.jsx` (replace placeholder)

**Interfaces:**
- Consumes: `getModel`, `imageUrl` from `../api.js`; `useParams` from react-router-dom; `Card` shape.
- Produces: the detail view — metadata key/values + the four reference angles as a gallery; clicking a frame enlarges it in an overlay.

- [ ] **Step 1: Replace `studio/frontend/src/routes/ModelDetail.jsx`**

```jsx
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getModel, imageUrl } from "../api.js";

const ANGLE_LABEL = { "front.png": "front", "34.png": "3/4", "profile.png": "profile", "body.png": "body" };

export default function ModelDetail() {
  const { slug } = useParams();
  const [model, setModel] = useState(null);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(null);

  useEffect(() => {
    getModel(slug).then(setModel).catch((e) => setError(e.message));
  }, [slug]);

  if (error) return <section><div className="sec-head"><h2>Not found</h2></div><div className="alert warn">{error}</div><Link className="btn" to="/">← Roster</Link></section>;
  if (!model) return <section><div className="sec-head"><h2>Loading…</h2></div></section>;

  return (
    <section>
      <div className="sec-head">
        <h2>{model.name}</h2>
        <div className="grow"></div>
        <Link className="btn ghost" to="/">← Roster</Link>
      </div>

      <div className="console" style={{ gridTemplateColumns: "1fr 280px" }}>
        <div className="pane">
          <h4><span className="n">01</span> Reference sheet</h4>
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
          <h4><span className="n">02</span> Identity</h4>
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
    </section>
  );
}
```

- [ ] **Step 2: Manual verification**

Open `http://localhost:5173/model/jess`. Expected: heading "Jess", the four reference frames (front/3-4/profile/body) rendered as real images, the identity string and key/values on the right. Click a frame → full-size overlay; click overlay → closes. "← Roster" returns to `/`.

- [ ] **Step 3: Commit**

```bash
git add studio/frontend/src/routes/ModelDetail.jsx
git commit -m "feat(frontend): model detail view with reference gallery and zoom"
```

---

### Task 6: Frontend — Casting Console (generate → pick → save)

**Files:**
- Create: `studio/frontend/src/components/CandidateGrid.jsx`
- Create: `studio/frontend/src/components/SavePanel.jsx`
- Modify: `studio/frontend/src/routes/Console.jsx` (replace placeholder)

**Interfaces:**
- Consumes: `generateDescribe`, `pollUntilDone`, `saveModel`, from `../api.js`; `useNavigate`.
- Produces: the full create loop. Helpers defined in `Console.jsx`:
  - `assembleIdentity(form): string`
  - `slugify(name): string`
  - `genderWord(gender): string`
  - Candidates grouped by `angle`; selection state `picked` maps angle → `{filename, subfolder}`.

The four angles, in order: `["front", "34", "profile", "body"]`.

- [ ] **Step 1: Create `studio/frontend/src/components/CandidateGrid.jsx`**

Groups candidates by angle into four columns; one selectable frame per angle. Uses the mockup `.frame` / `.sel` styles.

```jsx
import { imageUrl } from "../api.js";

const ANGLES = ["front", "34", "profile", "body"];
const ANGLE_LABEL = { front: "front", "34": "3/4", profile: "profile", body: "body" };

export default function CandidateGrid({ candidates, picked, onPick }) {
  const byAngle = ANGLES.map((a) => ({ angle: a, frames: candidates.filter((c) => c.angle === a) }));
  return (
    <div className="sheet" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
      {byAngle.map(({ angle, frames }) => (
        <div key={angle} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="sub" style={{ margin: 0 }}>{ANGLE_LABEL[angle]}</div>
          {frames.map((c) => {
            const isSel = picked[angle]?.filename === c.filename;
            return (
              <div
                key={c.filename}
                className={`frame ${isSel ? "sel" : ""}`}
                onClick={() => onPick(angle, { filename: c.filename, subfolder: c.subfolder })}
              >
                <img src={c.url} alt={`${angle} ${c.index}`} />
                <span className="fl">{ANGLE_LABEL[angle]} · {c.index + 1}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create `studio/frontend/src/components/SavePanel.jsx`**

Ports the mockup Save pane. Provenance is synthetic-only in v1 (the "consented real" radio is rendered but disabled). Dedup banner + LoRA button rendered inert.

```jsx
export default function SavePanel({ form, slug, seed, allPicked, saving, saveError, onSave }) {
  return (
    <div className="pane">
      <h4><span className="n">03</span> Save</h4>
      <div className="body">
        <div className="field">
          <label>Provenance</label>
          <div className="provenance">
            <label className="radio on"><input type="radio" name="prov" checked readOnly /><span>Synthetic<small>fictional, release-free</small></span></label>
            <label className="radio"><input type="radio" name="prov" disabled /><span>Consented real<small>requires a release record · phase 2</small></span></label>
          </div>
        </div>
        <div>
          <div className="kv"><span>slug</span><span>{slug || "—"}</span></div>
          <div className="kv"><span>seed</span><span>{seed}</span></div>
          <div className="kv"><span>name</span><span>{form.name || "—"}</span></div>
          <div className="kv"><span>status</span><span>card</span></div>
        </div>
        {saveError && <div className="alert warn"><b>Save failed.</b> {saveError}</div>}
        <button className="btn ok" style={{ width: "100%", justifyContent: "center" }} disabled={!allPicked || saving} onClick={onSave}>
          {saving ? "Saving…" : "Save to collection"}
        </button>
        {!allPicked && <div className="note"><span className="dot"></span><span>Pick one frame for each of the four angles to enable save.</span></div>}
        <button className="btn" style={{ width: "100%", justifyContent: "center" }} disabled>Promote to LoRA · phase 2</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Replace `studio/frontend/src/routes/Console.jsx`**

The three-pane console: Brief form (left), Base sheet + generate + candidate picker (middle), Save (right). Ports mockup markup; wires describe generate → poll → pick → save.

```jsx
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
```

- [ ] **Step 4: Manual verification — full create loop against the live stack**

Prereqs: backend (:8800), ComfyUI (:8188), and the Vite dev server (:5173) all running. Open `http://localhost:5173/new`.

1. Fill the brief: Name "Testa", Gender "Female", Age band "late 20s", Build "athletic", Hair "dark bob". (Age band is required.)
2. Click "⟳ Generate 8". Button shows "Generating…" for ~60s (four angles synchronously), then a 4-column grid appears with 2 real candidate images per angle.
3. Click one frame in each of the four columns — each shows the violet "✓ PICK" badge. The Save button enables once all four are picked.
4. Click "Save to collection". On success the app navigates to `/model/testa` showing the saved reference sheet.
5. Go to `/` (Roster) → "Testa" now appears as a card with a real thumbnail.
6. Confirm the write on disk: `models/testa/card.json` exists and `git log --oneline -1` shows the auto-commit `feat: add model testa`.

If any step fails, capture the browser console + network tab and the backend log; fix before committing.

- [ ] **Step 5: Clean up the test model (optional)**

If "Testa" was a throwaway, remove it so it isn't committed as real content:

```bash
git rm -r models/testa && git commit -m "chore: remove console smoke-test model"
```

(Or keep it if the model is wanted. Note the create flow already made its own commit in Step 4.)

- [ ] **Step 6: Commit the console**

```bash
git add studio/frontend/src/routes/Console.jsx studio/frontend/src/components/CandidateGrid.jsx studio/frontend/src/components/SavePanel.jsx
git commit -m "feat(frontend): casting console — describe generate, pick per angle, save"
```

---

## Notes for the implementer

- The `/generate` route runs synchronously (~60s for four angles); the UI shows a "Generating…" state across that single request, then `pollUntilDone` returns the already-finished job on its first poll. Keep the poll — it also covers the `error` status.
- `count: 2` is deliberate (2 frames per angle × 4 angles = 8 candidates) to match the mockup's "Generate 8". Do not raise it without reason — each extra frame is more GPU time.
- Reference-mode, the likeness slider, the dedup banner, and LoRA promotion are intentionally inert in v1. Render them per the mockup but do not wire them.
- If a candidate image 404s, it means the ComfyUI output URL expired or the server restarted; regenerate.
