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

export const generateReference = ({ ref_image, likeness, seed, count }) =>
  jpost("/generate", { mode: "reference", ref_image, likeness, seed, count });

export async function uploadReference(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`upload -> ${r.status}`);
  return r.json(); // { ref_image }
}

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
