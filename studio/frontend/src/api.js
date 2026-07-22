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

export async function deleteModel(slug) {
  const r = await fetch(`${API}/models/${slug}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`DELETE /models/${slug} -> ${r.status}`);
  return r.json();
}

export const generateDescribe = ({ identity_string, seed, count }) =>
  jpost("/generate", { mode: "describe", identity_string, seed, count });

export const generateReference = ({ ref_image, identity_string, seed, count }) =>
  jpost("/generate", { mode: "reference", ref_image, identity_string, seed, count });

export async function uploadReference(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`upload -> ${r.status}`);
  return r.json(); // { ref_image }
}

export const saveModel = (payload) => jpost("/models", payload);
export const dedupCheck = (attributes) => jpost("/dedup-check", { attributes });

export const generateDataset = (slug, count = 40) =>
  jpost(`/models/${slug}/dataset`, { count });

export const imageUrl = (slug, refPath) => `${API}/models/${slug}/${refPath}`;

// Candidate previews come from ComfyUI, which 403s cross-origin browser loads.
// Route them through the backend proxy (same origin as the rest of the API).
export const candidateUrl = ({ filename, subfolder = "", type = "output" }) =>
  `${API}/comfy-image?filename=${encodeURIComponent(filename)}` +
  `&subfolder=${encodeURIComponent(subfolder || "")}&type=${encodeURIComponent(type)}`;

// Generation runs on a local GPU across four angles and can take many minutes.
// Budget ~40 min (1200 tries x 2s) so the UI keeps polling instead of giving up
// mid-render. The backend caps each angle's ComfyUI poll separately.
export async function pollUntilDone(jobId, { interval = 2000, tries = 1200 } = {}) {
  for (let i = 0; i < tries; i++) {
    const job = await jget(`/jobs/${jobId}`);
    if (job.status !== "running") return job;
    await new Promise((res) => setTimeout(res, interval));
  }
  throw new Error("job timed out");
}
