import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PrintHead from "../src/dash/PrintHead";
import Reader from "../src/dash/Reader";
import { api, type WorkDetail, type WorkMap } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import { LinksProvider } from "../src/dash/links";
import { CharactersProvider, makeCharacters } from "../src/dash/useCharacters";
import { hyena } from "./dash-fixtures";

const map = (n: number, o: Partial<WorkMap> = {}): WorkMap => ({
  version: 1, analysis_version: 1, notes_version: null, motifs: [], notes: null,
  beats: Array.from({ length: n }, (_, i) => ({ id: `b${i}`, label: `節拍${i}`, intensity: 0.3 + i / 10, span: { quote: "q", start: i, end: i + 1 } })),
  ...o,
});
const wrap = (el: JSX.Element) => (
  <MemoryRouter><CharactersProvider value={makeCharacters([hyena], "hyena")}><LinksProvider>{el}</LinksProvider></CharactersProvider></MemoryRouter>);
const cols = () => document.querySelectorAll(".dash-mcol");
const head = () => document.querySelector(".dash-printhead");
const reduce = (on: boolean) => {
  window.matchMedia = ((q: string) => ({ matches: on && q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
};

beforeEach(() => setLang("zh-Hant"));
afterEach(() => { delete (window as { matchMedia?: unknown }).matchMedia; vi.restoreAllMocks(); vi.useRealTimers(); });

describe("PrintHead(印字頭)", () => {
  it("running:只有印字頭,沒有任何點陣欄", () => {
    render(wrap(<PrintHead running printed={false} map={map(3)} />));
    expect(head()).toBeTruthy();
    expect(cols()).toHaveLength(0);
  });
  it("沒在跑也沒印:什麼都不畫", () => {
    const { container } = render(wrap(<PrintHead running={false} printed={false} map={null} />));
    expect(container.textContent).toBe("");
    expect(head()).toBeNull();
  });
  it("printed:印一次點陣張力(每個 beat 一欄),印完收起", () => {
    vi.useFakeTimers();
    render(wrap(<PrintHead running printed map={map(3)} />));
    expect(cols()).toHaveLength(3);
    expect(head()).toBeNull();
    act(() => { vi.advanceTimersByTime(3000); });
    expect(cols()).toHaveLength(0);
    expect(head()).toBeNull();   // 印完就收起,不回到來回移動
  });
  it("印的時候點一下 → 直接收起", () => {
    render(wrap(<PrintHead running printed map={map(3)} />));
    fireEvent.click(document.querySelector(".dash-print")!);
    expect(cols()).toHaveLength(0);
  });
  it("減動:不顯示印字頭,也不播印", () => {
    reduce(true);
    const { container, rerender } = render(wrap(<PrintHead running printed={false} map={map(3)} />));
    expect(container.textContent).toBe("");
    expect(head()).toBeNull();
    rerender(wrap(<PrintHead running printed map={map(3)} />));
    expect(cols()).toHaveLength(0);
  });
});

describe("Reader 接 job 事件:analyst ok 才印", () => {
  const work = { slug: "d1", title: "海", version: 1, versions: [1], text: "內文", state: "running", job_id: 5, notes_ready: false };
  const mountReader = (m: WorkMap | null, onAnalysed = vi.fn()) => {
    vi.spyOn(api, "work").mockResolvedValue(work as WorkDetail);
    render(wrap(<Reader slug="d1" works={[]} onOpen={vi.fn()} onSubmitNew={vi.fn()} onQuote={vi.fn()} map={m} onAnalysed={onAnalysed} />));
    return onAnalysed;
  };
  it("分析中:紙頂有印字頭、沒有點陣欄", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "analyst", status: "start" } };
      await new Promise(() => {});
    });
    mountReader(map(3));
    await screen.findByText("內文");
    await waitFor(() => expect(head()).toBeTruthy());
    expect(cols()).toHaveLength(0);
  });
  it("收到 analyst ok + map 有 3 個 beats → 印出 3 欄,並通知外面重抓 map", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "analyst", status: "start" } };
      yield { event: "phase", data: { name: "analyst", status: "ok" } };
      await new Promise(() => {});
    });
    const onAnalysed = mountReader(map(3));
    await waitFor(() => expect(cols()).toHaveLength(3));
    expect(onAnalysed).toHaveBeenCalled();
  });
  it("resume-skip 的 ok 不算:不印", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "analyst", status: "ok", detail: "resume-skip" } };
      yield { event: "phase", data: { name: "reviewer", status: "start" } };
      await new Promise(() => {});
    });
    const onAnalysed = mountReader(map(3));
    await screen.findByText(/寫備課筆記/);
    expect(cols()).toHaveLength(0);
    expect(head()).toBeTruthy();
    expect(onAnalysed).not.toHaveBeenCalled();
  });
  it("analyst ok 但 map 還沒有 beats(還沒重抓到)→ 先不印", async () => {
    vi.spyOn(api, "jobEvents").mockImplementation(async function* () {
      yield { event: "phase", data: { name: "analyst", status: "ok" } };
      await new Promise(() => {});
    });
    const onAnalysed = mountReader(map(0, { analysis_version: null }));
    await waitFor(() => expect(onAnalysed).toHaveBeenCalled());
    expect(cols()).toHaveLength(0);
  });
});
