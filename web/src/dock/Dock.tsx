import { useState } from "react";
import type { VizData } from "../types";

const CN: Record<string, string> = { technique: "技法", effect: "效果", theme: "主題", motif: "意象", beat: "節拍", character: "角色" };

export default function Dock({ viz, selected }: { viz: VizData; selected: string | null }) {
  const [open, setOpen] = useState(true);
  if (!open) return <button className="dock-tab" onClick={() => setOpen(true)}>編輯 · 討論</button>;
  const node = selected ? viz.nodes.find(n => n.id === selected) : null;
  const kp = selected && viz.feedback
    ? viz.feedback.key_points.find(p => p.refs.includes(selected)) : null;
  return (
    <aside className="dock">
      <div className="dock-head"><span className="dock-t">編輯 · 討論</span>
        <span className="dock-x" onClick={() => setOpen(false)}>⟩</span></div>
      <div className="dock-body">
        {!node && viz.feedback && <>
          <div className="dock-type">編輯總覽</div>
          <div className="dock-label">整體閱讀</div>
          <p>{viz.feedback.read}</p>
          <div className="dock-lab">如果只能改一件事</div>
          <p>{viz.feedback.one_line}</p>
          <div className="dock-lab">就地討論</div>
          <div className="bubble ed">點左邊圖上任一節點,我們就從那裡聊起。</div>
        </>}
        {node && <>
          <div className="dock-type">{CN[node.type] || node.type}</div>
          <div className="dock-label">{node.label}</div>
          {kp ? <>
            <div className="dock-lab">編輯的判斷</div><p>{kp.body}</p>
            {kp.question && <div className="bubble ed">{kp.question}</div>}
          </> : <p>{node.note || "這個節點目前沒有編輯標記,從這裡開始討論也可以。"}</p>}
        </>}
      </div>
      <div className="dock-input">就這裡寫下你的想法…(下一階段接即時討論)</div>
    </aside>
  );
}
