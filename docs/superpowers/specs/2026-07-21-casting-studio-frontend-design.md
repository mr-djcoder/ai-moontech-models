# Casting Studio Frontend — Design

Date: 2026-07-21
Status: approved for planning

## Goal

Build the Studio frontend (`studio/frontend/`), currently unbuilt. It wraps the
existing FastAPI backend (`studio/backend/`, port 8800) so a user can browse the
model roster and create a new synthetic model end-to-end through a visual UI,
matching the supplied "MoonTech Casting" mockup. The models are used to produce
ads, so the create flow prioritizes judging realism when picking frames.

## Locked decisions

- **Stack:** React + Vite. Matches the README's stated plan. The Casting Console
  is a small state machine (generate → poll → pick → save) that React manages
  cleanly.
- **Design:** Port the mockup's visual language (the MoonTech dark theme CSS)
  verbatim. Replace the mock JS placeholder data and SVG portraits with real API
  data and real generated images.
- **Scope:** Describe-mode create flow wired end-to-end. Reference-image upload,
  the dedup banner, and the "Promote to LoRA" button are rendered per the mockup
  but inert (the backend has no upload endpoint; `/dedup-check` is a stub that
  returns `[]`; LoRA is phase 2).
- **No turntable / 360 view.** Rejected during design: a text-prompt yaw spin
  drifts identity frame-to-frame and works against the realism goal. Realism is
  served instead by a locked canonical face, the four clean reference angles, and
  (future) reference-mode re-seeding. A true multi-view/3D turntable, if ever
  needed, is a separate project.

## Architecture

Three views. Frontend dev server runs on Vite (:5173) and calls the backend
(:8800).

| View | Route | Purpose |
|---|---|---|
| Roster | `/` | Grid of models from `GET /models`, real reference thumbnails. |
| Casting Console | `/new` | Describe → generate → pick → save. |
| Model detail | `/model/:slug` | Card metadata + the four reference angles as a gallery (click to enlarge). |

Routing via React Router (three routes above). The mockup's `#roster` /
`#console` tab anchors become nav links to `/` and `/new`.

## Backend changes

Additive only — the existing four-angle path and all 59 passing tests stay
unchanged.

1. **CORS.** Add `CORSMiddleware` allowing `http://localhost:5173` (dev). This is
   the only cross-origin surface; the app is localhost-only with no auth.
2. **Serve saved model images.** Roster thumbnails and the detail gallery read
   images from `models/<slug>/reference/*.png` on disk, which the backend does
   not currently serve. Add a static route, e.g. `GET /models/{slug}/reference/{file}`,
   reading from `MODELS_ROOT / slug / "reference" / file` (reject path traversal;
   404 on miss). Candidate images during generation are already absolute ComfyUI
   URLs (`http://127.0.0.1:8188/view?...`) and need no backend change.

No new generation endpoints. The create flow uses `POST /generate`,
`GET /jobs/{id}`, and `POST /models` exactly as they exist today.

## Create flow — data contracts

This is the load-bearing part; the mockup is looser than the real contract.

1. **Brief → generate.** The Console form collects `name`, `gender`,
   `identity_string` (assembled from the attribute fields), `seed`, and `count`.
   Submit `POST /generate {mode:"describe", identity_string, seed, count}`.
   Returns `{job_id}`. Note: `/generate` currently runs the job synchronously and
   returns only after all angles finish; the UI shows a spinner across that call,
   then reads the finished job.
2. **Poll.** `GET /jobs/{job_id}` until `status` is `done` or `error`. On `done`
   it returns `candidates: Candidate[]`, where each `Candidate` carries
   `{url, filename, subfolder, angle, index}`.
3. **Pick — one frame per angle.** Generation produces `count` frames for **each**
   of the four angles (`front`, `34`, `profile`, `body`). The save contract
   (`SaveRequest.picked`) requires exactly one `PickedFrame{filename, subfolder}`
   **per angle** — `copy_reference_frames` iterates all four and `KeyError`s if any
   is missing. Therefore the UI groups candidates by `angle` (four groups) and the
   user selects one frame in each group. Save is disabled until all four angles
   have a pick. (This corrects the mockup's "pick one strongest frame" — there is
   no separate canonical-face field; the four picks *are* the reference sheet.)
4. **Save.** `POST /models` with `{slug, name, gender, identity_string, seed,
   attributes, provenance, picked}`. Response is `{ok, commit}` on success or
   `{ok:false, reason}` on a safety rejection or write failure. On success the
   backend has written `models/<slug>/` and git-committed; the UI routes to
   `/model/:slug`.

`slug` is derived from `name` (lowercased, spaces→hyphens); shown in the Save
panel's key/value readout and editable.

## Inert (rendered, not wired) in v1

- **Reference mode** segment: visible, disabled, tooltip "needs image upload —
  phase 2". No backend upload endpoint exists.
- **Dedup banner:** the mockup's "87% similar" warning. `POST /dedup-check`
  returns `[]` today, so the banner never shows. Wire the call so it lights up
  automatically when the real mechanism (#16) lands, but expect no matches now.
- **Likeness slider:** only meaningful for reference mode; hidden/disabled in
  describe-only v1.
- **Promote to LoRA** button: disabled, "phase 2" per the mockup.

## Frontend structure

```
studio/frontend/
  index.html
  package.json            vite + react + react-router-dom
  vite.config.js
  src/
    main.jsx              router mount
    styles.css            the mockup's MoonTech theme, ported verbatim
    api.js                fetch wrappers: listModels, getModel, generate,
                          pollJob, saveModel, dedupCheck, imageUrl(slug,file)
    routes/
      Roster.jsx          grid + toolbar (search/filter chips are client-side)
      Console.jsx         brief form + generate + candidate picker + save panel
      ModelDetail.jsx     metadata + four-angle gallery with enlarge
    components/
      ModelCard.jsx
      CandidateGrid.jsx   grouped by angle, one-pick-per-angle selection
      SavePanel.jsx       provenance, key/value readout, save button
```

Keep each component focused; `api.js` is the single seam to the backend so views
don't embed URLs.

## Error handling

- Generate/poll failure (`job.status === "error"` or network) → inline error in
  the Base-sheet panel with a retry; no crash.
- Save `ok:false` → surface `reason` in the Save panel (covers safety rejections
  and write failures).
- Missing/broken reference image → placeholder tile, no layout break.

## Testing

- **Backend:** add pytest cases for the static image route (serves an existing
  file; 404 on miss; rejects `..` traversal) and confirm CORS headers are present.
  Existing 59 tests must stay green.
- **Frontend:** no JS test harness exists yet; verify by driving the running
  stack manually — create a model through the Console against live ComfyUI, pick
  four frames, save, and confirm the new card appears on the roster and its detail
  gallery renders the saved reference images.

## Out of scope (explicit)

Turntable/360, reference-image upload, real dedup, LoRA promotion, auth, and any
non-localhost deployment. Each is a later, separately-scoped piece.
