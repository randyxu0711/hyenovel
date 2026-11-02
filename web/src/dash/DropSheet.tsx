import { useEffect, useRef, useState } from "react";

const hasFiles = (e: DragEvent) => !!e.dataTransfer && [...(e.dataTransfer.types ?? [])].includes("Files");

/** 整個畫面收檔:拖檔案進來時蓋一層桌色、疊上一張寫著下一版號的紙;放開交第一個檔。拖文字/連結不理。 */
export default function DropSheet({ next, onFile }: { next: number; onFile: (f: File) => void }) {
  const [on, setOn] = useState(false);
  const depth = useRef(0);
  const cb = useRef(onFile);
  cb.current = onFile;
  useEffect(() => {
    const enter = (e: DragEvent) => { if (!hasFiles(e)) return; e.preventDefault(); depth.current++; setOn(true); };
    const over = (e: DragEvent) => { if (hasFiles(e)) e.preventDefault(); };   // 不擋,瀏覽器會直接開檔
    const leave = (e: DragEvent) => { if (!hasFiles(e)) return; if (--depth.current <= 0) { depth.current = 0; setOn(false); } };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0; setOn(false);
      const f = e.dataTransfer?.files[0];
      if (f) cb.current(f);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, []);
  if (!on) return null;
  return (
    <div className="drop-sheet" aria-hidden="true">
      <div className="drop-paper dash-paper"><span>v{next}</span></div>
    </div>
  );
}
