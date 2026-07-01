import type { Stage } from "../lib/camera";

export default function Chrome(
  { stage, title, onBack }: { stage: Stage; title?: string; onBack: () => void },
) {
  if (stage === "overview") return null;
  return (
    <>
      <div className="crumb">
        {stage === "single"
          ? <button className="crumb-link" onClick={onBack}>目錄</button>
          : <b>目錄</b>}
        {stage === "single" && title && <><span>›</span><b>{title}</b></>}
      </div>
      {stage === "single" && (
        <button className="chrome-back" onClick={onBack}>← 退</button>
      )}
    </>
  );
}
