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
