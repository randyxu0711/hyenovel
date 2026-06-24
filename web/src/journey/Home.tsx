import { useEffect, useState } from "react";
import Overview from "./Overview";
import Catalog from "./Catalog";
import { getIndex } from "../data/client";
import type { IndexEntry } from "../types";

export default function Home() {
  const [stage, setStage] = useState<"overview" | "catalog">("overview");
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getIndex().then(i => setEntries(i.stories)).catch(e => setErr(String(e.message))); }, []);
  if (err) return <div className="loadmsg">讀不到故事列表:{err}<br />先在 repo 根跑 <code>python index.py</code>。</div>;
  return (
    <div className={`home stage-${stage}`} data-testid="home">
      <Catalog entries={entries} />
      {stage === "overview" && <Overview onEnter={() => setStage("catalog")} />}
    </div>
  );
}
