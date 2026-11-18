import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, DashError, type Compare } from "./api";

export function defaultOld(history: { n: number; noted: boolean }[], cur: number): number | null {
  const older = history.filter(h => h.n < cur).sort((a, b) => b.n - a.n);
  return older.length ? (older.find(h => h.noted) ?? older[0]).n : null;
}

export type CompareState = {
  on: boolean; clean: boolean; data: Compare | null; err: string | null;
  hunk: number | null; open: Set<string>; focus: { id: string; n: number } | null;
  picker: boolean; setPicker(b: boolean): void;
  toggle(): void; setClean(b: boolean): void; pickOld(n: number): void;
  step(d: 1 | -1): void; toggleRun(id: string): void;
};

const dels = (c: Compare, ids: string[]) => ids.filter(id => c.runs.some(r => r.id === id && r.op === "del"));

export function useCompare(slug: string, version: number | null, onCompare?: (c: Compare | null) => void): CompareState {
  const [search, setSearch] = useSearchParams();
  const cmp = search.get("cmp");
  const on = cmp !== null;
  const clean = on && search.has("clean");
  const [data, setData] = useState<Compare | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hunk, setHunk] = useState<number | null>(null);
  const [userOpen, setUserOpen] = useState<Set<string>>(new Set());
  const [tempOpen, setTempOpen] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const [picker, setPicker] = useState(false);
  const notify = useRef(onCompare);
  notify.current = onCompare;

  const edit = useCallback((f: (p: URLSearchParams) => void) => setSearch(prev => {
    const p = new URLSearchParams(prev);
    f(p);
    return p;
  }), [setSearch]);
  const leave = useCallback(() => edit(p => { p.delete("cmp"); p.delete("clean"); }), [edit]);
  const editRef = useRef(edit);
  editRef.current = edit;

  useEffect(() => {
    setData(null); setHunk(null); setUserOpen(new Set()); setTempOpen(new Set()); setFocus(null); setPicker(false);
    if (!on || version === null) { notify.current?.(null); return; }
    let live = true;
    const from = cmp ? Number(cmp) : undefined;
    api.compare(slug, version, from).then(c => { if (live) { setErr(null); setData(c); notify.current?.(c); } }, e => {
      if (!live) return;
      const code = e instanceof DashError ? e.code : "unknown";
      if (code === "unknown-version" && from !== undefined) { editRef.current(p => p.set("cmp", "")); return; }
      setErr(code);
      editRef.current(p => { p.delete("cmp"); p.delete("clean"); });
    });
    return () => { live = false; };
  }, [slug, version, cmp, on]);

  useEffect(() => {
    if (!on) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      if (picker) setPicker(false); else leave();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [on, picker, leave]);

  const go = useCallback((i: number) => {
    if (!data) return;
    const ids = data.hunks[i].ids;
    setHunk(i);
    setFocus(f => ({ id: ids[0], n: (f?.n ?? 0) + 1 }));
    if (clean) setTempOpen(new Set(dels(data, ids)));
    else setUserOpen(o => new Set([...o, ...dels(data, ids)]));
  }, [data, clean]);

  const open = useMemo(() => new Set([...userOpen, ...tempOpen]), [userOpen, tempOpen]);
  return {
    on, clean, data, err, hunk, open, focus, picker, setPicker,
    toggle: () => { setErr(null); if (on) leave(); else edit(p => p.set("cmp", "")); },
    setClean: b => edit(p => { if (b) p.set("clean", ""); else p.delete("clean"); }),
    pickOld: n => { setPicker(false); edit(p => p.set("cmp", String(n))); },
    step: d => {
      const n = data?.hunks.length ?? 0;
      if (!n) return;
      go(hunk === null ? (d > 0 ? 0 : n - 1) : (hunk + d + n) % n);
    },
    toggleRun: id => {
      setTempOpen(o => { const x = new Set(o); x.delete(id); return x; });
      setUserOpen(o => { const x = new Set(o); if (open.has(id)) x.delete(id); else x.add(id); return x; });
    },
  };
}
