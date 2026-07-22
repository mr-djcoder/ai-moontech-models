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
        {front && <img src={imageUrl(model.slug, front)} alt={model.name} onError={(e) => { e.currentTarget.style.display = "none"; }} />}
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
