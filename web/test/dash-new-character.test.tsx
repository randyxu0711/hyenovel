import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Candidate } from "../src/dash/api";
import { setLang } from "../src/dash/i18n";
import NewCharacter from "../src/dash/NewCharacter";
import { DRAFT_KEY, drop, keep } from "../src/dash/newCharacterDraft";
import { WORDS } from "../src/dash/questionnaire";

const candidate = (n: number, warnings: string[] = []) => ({
  name: { "zh-Hant": `門縫${n}`, en: `Crack ${n}` }, form: { "zh-Hant": "門縫", en: "door crack" },
  line: { "zh-Hant": "先聽", en: "Listens" }, reading: `讀法${n}`, sample: `讀到「暗暗紅紅」我停住了(${n})。`,
  figure: { main: (["olive", "rust", "slate"] as const)[(n - 1) % 3], second: "bark",
    parts: [{ group: "body", d: "M20 90 C20 50 40 30 60 30 C80 30 100 50 100 90 Z", fill: "main" },
      { group: "ears", d: "M40 30 L46 18 L52 30 Z", fill: "second" }],
    eyes: [[50, 58], [70, 58]], mouth: [[54, 70], [60, 73], [66, 70]] },
  axes: [], card: {}, warnings,
  examples: [1, 2, 3].map(k => [{ who: "char", text: `菜脯${n}-${k}` }, { who: "author", text: `作者${n}-${k}` }]),
  plist: { traits: ["直率", "務實", "冷面幽默"], speech: ["簡短", "乾脆", "口語"] },
  depth: `[門縫${n}: 直率, 務實, 冷面幽默; 說話: 簡短, 乾脆, 口語]`,
});
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let bodies: { answers: Record<string, string>; lang: string }[];
let replies: Response[];
let urls: string[];
let onSaved: (id?: string) => Promise<void>;

const mount = () => render(<NewCharacter onClose={() => {}} onSaved={onSaved} />);
const go = () => screen.getByRole("button", { name: "生成候選" }) as HTMLButtonElement;
const formBox = () => screen.getByLabelText("陪你讀稿的,是什麼?") as HTMLInputElement;
const tab = (n: number | string) => screen.getByRole("tab", { name: new RegExp(`^門縫${n}`) });
const tabs = () => screen.getAllByRole("tab");
const panel = () => within(screen.getByRole("tabpanel"));
const pick = (n: number) => { fireEvent.click(tab(n)); return panel(); };
const box = (p: ReturnType<typeof panel>) => {
  if (!p.queryByLabelText("修改意見")) fireEvent.click(p.getByRole("button", { name: "修改" }));
  return p.getByLabelText("修改意見") as HTMLInputElement;
};
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;
const again = () => { fireEvent.click(button("重新生成")); fireEvent.click(button("重新生成")); };
const toResults = async (form = "門縫") => {
  const view = mount();
  fireEvent.change(formBox(), { target: { value: form } });
  fireEvent.click(go());
  await screen.findByRole("tab", { name: /^門縫1/ });
  return view;
};
const seeded = (extra: Record<string, unknown> = {}) => keep({
  form: "門縫", wish: "", batch: [candidate(1), candidate(2), candidate(3)] as unknown as Candidate[], batchNo: 1, revealed: 1,
  asked: { form: "門縫", wish: "" }, reaction: "", ...extra,
});

beforeEach(() => {
  sessionStorage.clear();
  drop();
  setLang("zh-Hant");
  bodies = [];
  urls = [];
  onSaved = vi.fn(async () => {});
  replies = [json({ seed: 1, story: "〈冰箱〉:清冰箱。", candidates: [candidate(1), candidate(2), candidate(3, ["looks-like-instructions"])] })];
  vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
    urls.push(_u);
    bodies.push(JSON.parse(String(init?.body)));
    const reply = replies.shift() ?? json({ seed: 2, candidates: [candidate(4), candidate(5), candidate(6)] });
    const signal = init?.signal;
    if (!signal) return reply;
    return Promise.race([reply, new Promise<Response>((_, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })]);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("問卷資料", () => {
  it("詞卡每類三張", () => {
    expect(WORDS.map(r => r.length)).toEqual([3, 3, 3, 3, 3, 3]);
  });
});

describe("作答", () => {
  it("兩題都空不能生成(會花額度);只寫第二題也能生成", async () => {
    mount();
    expect(go().disabled).toBe(true);
    expect(go().title).toBe("先寫一題,或按骰子");
    fireEvent.change(screen.getByLabelText("你想要它怎麼讀?"), { target: { value: "慢慢來" } });
    expect(go().disabled).toBe(false);
    fireEvent.click(go());
    await screen.findByRole("tab", { name: /^門縫1/ });
    expect(bodies[0]).toEqual({ answers: { form: "", wish: "慢慢來" }, lang: "zh-Hant" });
  });
  it("送出兩題的答案,去掉前後空白", async () => {
    mount();
    fireEvent.change(formBox(), { target: { value: " 退潮 " } });
    fireEvent.change(screen.getByLabelText("你想要它怎麼讀?"), { target: { value: " 慢慢來 " } });
    fireEvent.click(go());
    await screen.findByRole("tab", { name: /^門縫1/ });
    expect(bodies[0].answers).toEqual({ form: "退潮", wish: "慢慢來" });
  });
  it("開放題不放例子", () => {
    mount();
    expect(formBox().getAttribute("placeholder")).toBeNull();
    expect(screen.getByLabelText("你想要它怎麼讀?").getAttribute("placeholder")).toBeNull();
  });
  it("詞卡要按了才出現,換詞不打 API,選了填進形體", () => {
    mount();
    expect(screen.queryByRole("button", { name: "校對員" })).toBeNull();
    fireEvent.click(button("提供參考詞"));
    fireEvent.click(button("校對員"));
    expect(formBox().value).toBe("校對員");
    fireEvent.click(button("提供參考詞"));
    fireEvent.click(button("換一組詞"));
    expect(button("代書")).toBeTruthy();
    expect(bodies).toEqual([]);
  });
});

describe("陣容", () => {
  it("生成時答案條顯示狀態和已跑時間,不是假進度;問卷摺起來", async () => {
    mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    const status = screen.getByRole("status");
    expect(status.textContent).toContain("0:00");
    expect(status.closest(".nc-strip")?.textContent).toContain("門縫");
    expect(screen.queryByLabelText("陪你讀稿的,是什麼?")).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
    await screen.findByRole("tab", { name: /^門縫1/ });
  });
  it("三張排成分頁,剛揭曉一張都不選", async () => {
    await toResults();
    expect(screen.getByRole("tablist", { name: "候選" })).toBeTruthy();
    expect(tabs()).toHaveLength(3);
    expect(tabs().map(t => t.getAttribute("aria-selected"))).toEqual(["false", "false", "false"]);
    expect(screen.queryByRole("tabpanel")).toBeNull();
  });
  it("卡上只有角色、名字、介紹;形體只在答案條", async () => {
    await toResults();
    expect(tab(1).textContent).toBe("門縫1先聽");
    expect(tab(1).querySelector("svg.fig")?.getAttribute("width")).toBe("168");
    expect(tab(1).querySelector("small")).toBeNull();
    expect(document.querySelector(".nc-strip")?.textContent).toContain("門縫");
  });
  it("名字等於形體時,卡上用介紹當標題,不重複印名字", async () => {
    replies = [json({ seed: 1, candidates: [1, 2, 3].map(n => ({ ...candidate(n), name: { "zh-Hant": "門縫", en: "door crack" }, line: { "zh-Hant": `聽${n}`, en: `L${n}` } })) })];
    mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    await screen.findByRole("tab", { name: "聽1" });
    expect(tabs().map(t => t.textContent)).toEqual(["聽1", "聽2", "聽3"]);
    expect(tabs()[0].querySelector(".nc-name")?.hasAttribute("data-lined")).toBe(true);
  });
  it("候選卡畫出它自己的長相和主色", async () => {
    await toResults();
    const [first, second] = tabs().map(a => a.querySelector("svg.fig")!);
    expect(first.getAttribute("style")).toContain("--fig-main: #7f9466");
    expect(second.getAttribute("style")).toContain("--fig-main: #a8553a");
    expect(first.querySelectorAll("g.ears path").length).toBeGreaterThan(0);
  });
  it("揭曉時三張畫出來,每批只播一次", async () => {
    const view = await toResults();
    await waitFor(() => expect(tabs().every(t => t.hasAttribute("data-draw"))).toBe(true));
    expect(JSON.parse(sessionStorage.getItem(DRAFT_KEY)!).revealed).toBe(1);
    view.unmount();
    mount();
    expect(tabs().some(t => t.hasAttribute("data-draw"))).toBe(false);
  });
});

describe("面板", () => {
  it("點卡展開面板,接在那張下面", async () => {
    await toResults();
    const p = pick(2);
    expect(tab(2).getAttribute("aria-selected")).toBe("true");
    expect(tab(2).getAttribute("aria-controls")).toBe("nc-panel");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(tab(2).id);
    expect(p.getByText("菜脯2-1")).toBeTruthy();
  });
  it("範例對話照聊天樣式,沒有說話者標籤", async () => {
    await toResults();
    const turns = pick(1).getAllByRole("listitem").slice(0, 2);
    expect(turns.map(li => li.textContent)).toEqual(["菜脯1-1", "作者1-1"]);
    expect(turns.map(li => li.className)).toEqual(["", "chat-me"]);
    expect(screen.getByRole("tabpanel").textContent).not.toContain("作者1-1作者");
  });
  it("試讀收在怎麼讀裡,沒有試讀就不留空行", async () => {
    replies = [json({ seed: 1, candidates: [{ ...candidate(1), sample: "" }, candidate(2), candidate(3)] })];
    await toResults();
    pick(1);
    expect(document.querySelector(".nc-sample")).toBeNull();
    pick(2);
    expect(document.querySelector("details.nc-how .nc-sample")?.textContent).toContain("(2)");
    expect(document.querySelector("details.nc-how summary")?.textContent).toBe("讀法");
  });
  it("像指令的文字在那張的面板顯示警告", async () => {
    await toResults();
    pick(1);
    expect(screen.queryAllByRole("note")).toHaveLength(0);
    pick(3);
    expect(screen.getAllByRole("note")).toHaveLength(1);
  });
  it("三段範例往下疊、沒有分頁,最上面說聊的是哪篇", async () => {
    await toResults();
    const p = pick(1);
    expect(p.getByText("菜脯1-1")).toBeTruthy();
    expect(p.getByText("菜脯1-3")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "情境" })).toBeNull();
    expect(p.getByText("對話範例:〈冰箱〉")).toBeTruthy();
    expect(pick(2).getByText("菜脯2-3")).toBeTruthy();
  });
  it("改這張先摺著;展開後才有輸入和會花額度,選用收起;✕ 收回焦點回改這張", async () => {
    await toResults();
    const p = pick(1);
    expect(p.queryByLabelText("修改意見")).toBeNull();
    expect(p.queryByText("會使用額度")).toBeNull();
    box(p);
    expect(p.getByText("會使用額度")).toBeTruthy();
    expect(p.queryByRole("button", { name: "選用" })).toBeNull();
    fireEvent.click(p.getByRole("button", { name: "收起" }));
    expect(p.queryByLabelText("修改意見")).toBeNull();
    expect(document.activeElement).toBe(p.getByRole("button", { name: "修改" }));
    expect(p.getByRole("button", { name: "選用" })).toBeTruthy();
  });
  it("改這張展開時 Esc 只收回摺頁,不收面板", async () => {
    await toResults();
    const p = pick(1);
    fireEvent.keyDown(box(p), { key: "Escape" });
    expect(screen.getByRole("tabpanel")).toBeTruthy();
    expect(p.queryByLabelText("修改意見")).toBeNull();
  });
  it("沒有範例就不顯示範例", async () => {
    replies = [json({ seed: 1, candidates: [1, 2, 3].map(n => ({ ...candidate(n), examples: [] })) })];
    await toResults();
    pick(1);
    expect(screen.queryByRole("group", { name: "情境" })).toBeNull();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
  it("英文介面卡上用英文名", async () => {
    setLang("en");
    mount();
    fireEvent.change(document.getElementById("nc-form")!, { target: { value: "crack" } });
    fireEvent.click(button("Generate candidates"));
    await screen.findByRole("tab", { name: /^Crack 1/ });
    fireEvent.click(screen.getByRole("tab", { name: /^Crack 1/ }));
    expect(panel().getAllByRole("listitem").slice(0, 2).map(li => li.textContent)).toEqual(["菜脯1-1", "作者1-1"]);
  });
  it("左右鍵切卡並移焦點,Home/End 到兩端,只有一張在 Tab 順序裡", async () => {
    await toResults();
    expect(tabs().map(t => t.tabIndex)).toEqual([0, -1, -1]);
    tab(1).focus();
    fireEvent.keyDown(tab(1), { key: "ArrowRight" });
    expect(tab(2).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(tab(2));
    expect(tabs().map(t => t.tabIndex)).toEqual([-1, 0, -1]);
    fireEvent.keyDown(tab(2), { key: "End" });
    expect(document.activeElement).toBe(tab(3));
    fireEvent.keyDown(tab(3), { key: "ArrowRight" });
    expect(document.activeElement).toBe(tab(1));
    fireEvent.keyDown(tab(1), { key: "ArrowLeft" });
    expect(tab(3).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(tab(3), { key: "Home" });
    expect(tab(1).getAttribute("aria-selected")).toBe("true");
  });
  it("Esc 收起面板,焦點回那張;再點選中的那張也收起", async () => {
    await toResults();
    const p = pick(2);
    fireEvent.keyDown(p.getByRole("button", { name: "選用" }), { key: "Escape" });
    expect(screen.queryByRole("tabpanel")).toBeNull();
    expect(document.activeElement).toBe(tab(2));
    pick(2);
    fireEvent.click(tab(2));
    expect(screen.queryByRole("tabpanel")).toBeNull();
  });
});

describe("答案條", () => {
  const EXAMPLE = "第二張的讀法接近了,但說話再短一點、長相換成別的動物";
  const reaction = () => screen.getByLabelText("對這批的意見") as HTMLInputElement;

  it("換一批先攤開反應列,收起後字還在", async () => {
    await toResults();
    expect(screen.queryByLabelText("對這批的意見")).toBeNull();
    fireEvent.click(button("重新生成"));
    expect(document.activeElement).toBe(reaction());
    fireEvent.change(reaction(), { target: { value: "短一點" } });
    fireEvent.click(button("收起"));
    expect(screen.queryByLabelText("對這批的意見")).toBeNull();
    fireEvent.click(button("重新生成"));
    fireEvent.keyDown(reaction(), { key: "Escape" });
    expect(screen.queryByLabelText("對這批的意見")).toBeNull();
    fireEvent.click(button("重新生成"));
    expect(reaction().value).toBe("短一點");
  });
  it("換一批用同樣答案重打、不帶 seed", async () => {
    await toResults();
    again();
    await screen.findByRole("tab", { name: /^門縫4/ });
    expect(bodies[1].answers).toEqual(bodies[0].answers);
    expect(bodies[1]).not.toHaveProperty("seed");
  });
  it("第一次生成不帶反應和上一批", async () => {
    await toResults();
    expect(bodies[0]).not.toHaveProperty("reaction");
    expect(bodies[0]).not.toHaveProperty("previous");
  });
  it("換一批帶去頭尾空白的反應和這批三張的名字與介紹,成功後清空收起", async () => {
    await toResults();
    fireEvent.click(button("重新生成"));
    fireEvent.change(reaction(), { target: { value: "  再短一點  " } });
    fireEvent.click(button("重新生成"));
    await screen.findByRole("tab", { name: /^門縫4/ });
    expect(bodies[1]).toMatchObject({
      answers: bodies[0].answers, lang: "zh-Hant", reaction: "再短一點",
      previous: [1, 2, 3].map(n => ({ name: `門縫${n}`, line: "先聽" })),
    });
    expect(screen.queryByLabelText("對這批的意見")).toBeNull();
    fireEvent.click(button("重新生成"));
    expect(reaction().value).toBe("");
  });
  it("反應留白也照送空字串", async () => {
    await toResults();
    fireEvent.click(button("重新生成"));
    fireEvent.change(reaction(), { target: { value: "   " } });
    fireEvent.submit(reaction().form!);
    await screen.findByRole("tab", { name: /^門縫4/ });
    expect(bodies[1]).toMatchObject({ reaction: "", previous: expect.any(Array) });
  });
  it("英文介面上一批用英文名和介紹", async () => {
    setLang("en");
    mount();
    fireEvent.change(document.getElementById("nc-form")!, { target: { value: "crack" } });
    fireEvent.click(button("Generate candidates"));
    await screen.findByRole("tab", { name: /^Crack 1/ });
    fireEvent.click(button("Another batch"));
    fireEvent.click(button("Another batch"));
    await screen.findByRole("tab", { name: /^Crack 4/ });
    expect((bodies[1] as unknown as { previous: unknown }).previous).toEqual([1, 2, 3].map(n => ({ name: `Crack ${n}`, line: "Listens" })));
  });
  it("反應框的提示是完整範例句,空框按 Tab 填進去", async () => {
    await toResults();
    fireEvent.click(button("重新生成"));
    expect(reaction().placeholder).toBe(EXAMPLE);
    expect(fireEvent.keyDown(reaction(), { key: "Tab" })).toBe(false);
    expect(reaction().value).toBe(EXAMPLE);
  });
  it("有字時 Tab 不覆蓋,Shift+Tab 也不填", async () => {
    await toResults();
    fireEvent.click(button("重新生成"));
    expect(fireEvent.keyDown(reaction(), { key: "Tab", shiftKey: true })).toBe(true);
    expect(reaction().value).toBe("");
    fireEvent.change(reaction(), { target: { value: "短一點" } });
    expect(fireEvent.keyDown(reaction(), { key: "Tab" })).toBe(true);
    expect(reaction().value).toBe("短一點");
  });
  it("改答案在原地攤開問卷,陣容留在下面;收起或 Esc 摺回", async () => {
    await toResults();
    fireEvent.click(button("修改條件"));
    expect(formBox().value).toBe("門縫");
    expect(document.activeElement).toBe(formBox());
    expect(tabs()).toHaveLength(3);
    fireEvent.click(button("收起"));
    expect(screen.queryByLabelText("陪你讀稿的,是什麼?")).toBeNull();
    expect(document.activeElement).toBe(button("修改條件"));
    fireEvent.click(button("修改條件"));
    fireEvent.keyDown(formBox(), { key: "Escape" });
    expect(screen.queryByLabelText("陪你讀稿的,是什麼?")).toBeNull();
  });
  it("答案改到跟這批不同時陣容變淡,改回來就不淡", async () => {
    await toResults();
    const lineup = () => document.querySelector(".nc-lineup")!;
    fireEvent.click(button("修改條件"));
    expect(lineup().hasAttribute("data-stale")).toBe(false);
    fireEvent.change(formBox(), { target: { value: "退潮" } });
    expect(lineup().hasAttribute("data-stale")).toBe(true);
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    expect(lineup().hasAttribute("data-stale")).toBe(false);
  });
  it("改答案後生成:摺頁收回、陣容原地進生成中,好了換成新那批", async () => {
    await toResults();
    fireEvent.click(button("修改條件"));
    fireEvent.change(formBox(), { target: { value: "退潮" } });
    fireEvent.click(go());
    expect(screen.queryByLabelText("陪你讀稿的,是什麼?")).toBeNull();
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    await screen.findByRole("tab", { name: /^門縫4/ });
    expect(bodies[1].answers.form).toBe("退潮");
    expect(document.querySelector(".nc-lineup")!.hasAttribute("data-stale")).toBe(false);
  });
  it("第一批失敗回問卷顯示原因,答案還在", async () => {
    replies = [json({ code: "candidates-failed", params: { reason: "timeout" } }, 502)];
    mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("候選生成失敗,再試一次。"));
    expect(formBox().value).toBe("門縫");
    expect(screen.queryByRole("button", { name: "收起" })).toBeNull();
  });
  it("額度用完講額度,不講再試一次", async () => {
    replies = [json({ code: "candidates-failed", params: { reason: "usage-limit" } }, 502)];
    mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    await waitFor(() => expect(screen.getByRole("alert").textContent).not.toContain("再試一次"));
  });
  it("生成中按停下:連線斷掉、回問卷不報錯,答案還在", async () => {
    replies = [new Promise<Response>(() => {}) as unknown as Response];
    mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    fireEvent.click(within(screen.getByRole("status")).getByRole("button", { name: "停下" }));
    await waitFor(() => expect(formBox().value).toBe("門縫"));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(go().disabled).toBe(false);
    fireEvent.click(go());
    await screen.findByRole("tab", { name: /^門縫4/ });
  });
  it("換一批途中按停下,原本那批回來", async () => {
    await toResults();
    replies = [new Promise<Response>(() => {}) as unknown as Response];
    again();
    fireEvent.click(button("停下"));
    await screen.findByRole("tab", { name: /^門縫1/ });
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("換一批失敗時,原本的候選回來,錯誤在答案條", async () => {
    await toResults();
    replies = [json({ code: "candidates-busy" }, 409)];
    again();
    const alert = await screen.findByRole("alert");
    expect(alert.closest(".nc-strip")).toBeTruthy();
    expect(tab(1)).toBeTruthy();
  });
});

describe("改候選與存卡", () => {
  const revise = (n: number, text = "再冷一點") => {
    const p = pick(n);
    fireEvent.change(box(p), { target: { value: text } });
    fireEvent.click(p.getByRole("button", { name: "送出修改" }));
    return p;
  };
  const last = () => bodies[bodies.length - 1] as unknown as Record<string, any>;

  it("回饋空白不能送,有字才能", async () => {
    await toResults();
    const p = pick(1);
    box(p);
    const send = p.getByRole("button", { name: "送出修改" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(box(p), { target: { value: "   " } });
    expect(send.disabled).toBe(true);
    fireEvent.change(box(p), { target: { value: "冷一點" } });
    expect(send.disabled).toBe(false);
  });
  it("只送一張,只更新那一張,回饋清空", async () => {
    await toResults();
    replies = [json(candidate(9))];
    revise(2);
    await screen.findByRole("tab", { name: /^門縫9/ });
    expect(urls[urls.length - 1]).toBe("/api/characters/candidates/revise");
    expect(last().feedback).toBe("再冷一點");
    expect(last().candidate.name["zh-Hant"]).toBe("門縫2");
    expect(tab(1)).toBeTruthy();
    expect(tab(3)).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /^門縫2/ })).toBeNull();
    await waitFor(() => expect((box(panel())).value).toBe(""));
  });
  it("改的時候只有這張掃描,輸入鎖住保留那句;其他張可讀,花額度的都鎖住", async () => {
    let release = (_: Response) => {};
    await toResults();
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    fireEvent.change(box(pick(3)), { target: { value: "別的" } });
    const p = revise(1);
    await waitFor(() => expect(document.querySelectorAll('.fig[data-state="scanning"]')).toHaveLength(1));
    expect(tab(1).querySelector('.fig[data-state="scanning"]')).toBeTruthy();
    const input = box(p);
    expect(input.readOnly).toBe(true);
    expect(input.value).toBe("再冷一點");
    expect(p.getByText("0:00")).toBeTruthy();
    expect(p.queryByRole("button", { name: "選用" })).toBeNull();
    const other = pick(3);
    expect(other.getByText("菜脯3-1")).toBeTruthy();
    expect(other.queryByLabelText("修改意見")).toBeNull();
    expect((other.getByRole("button", { name: "修改" }) as HTMLButtonElement).disabled).toBe(true);
    expect((other.getByRole("button", { name: "選用" }) as HTMLButtonElement).disabled).toBe(true);
    expect(button("重新生成").disabled).toBe(true);
    fireEvent.click(button("修改條件"));
    expect(go().disabled).toBe(true);
    release(json(candidate(9)));
    await waitFor(() => expect(go().disabled).toBe(false));
  });
  it("改的時候送出鍵換停下;按了那張回原樣、回饋留著、不報錯", async () => {
    await toResults();
    replies = [new Promise<Response>(() => {}) as unknown as Response];
    const p = revise(1);
    expect(tab(1).querySelector(".nc-clock")!.textContent).toBe("0:00");
    fireEvent.click(p.getByRole("button", { name: "停下" }));
    await waitFor(() => expect(panel().getByRole("button", { name: "送出修改" })).toBeTruthy());
    expect(tab(1)).toBeTruthy();
    expect((box(panel())).value).toBe("再冷一點");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(button("重新生成").disabled).toBe(false);
  });
  it("連點改這張,第二下落在停下鍵上不會停掉", async () => {
    let release = (_: Response) => {};
    await toResults();
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const p = revise(1);
    fireEvent.click(p.getByRole("button", { name: "停下" }), { detail: 2 });
    release(json(candidate(9)));
    await screen.findByRole("tab", { name: /^門縫9/ });
  });
  it("讀回應途中停下(AbortError 不是 DashError)也不報錯", async () => {
    await toResults();
    replies = [{ ok: true, status: 200, json: () => Promise.reject(new DOMException("aborted", "AbortError")) } as unknown as Response];
    revise(1);
    await waitFor(() => expect(panel().getByRole("button", { name: "送出修改" })).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("失敗時原內容和回饋都留著,原因顯示在那張的面板", async () => {
    await toResults();
    replies = [json({ code: "candidates-failed", params: { reason: "usage-limit" } }, 502)];
    revise(1);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toContain("再試一次");
    expect(alert.closest(".nc-panel")).toBeTruthy();
    expect(tab(1)).toBeTruthy();
    expect((box(panel())).value).toBe("再冷一點");
  });
  it("改好後長相變了那格重畫,沒變就不重畫", async () => {
    seeded();
    mount();
    replies = [json({ ...candidate(1), name: { "zh-Hant": "門縫7", en: "Crack 7" } })];
    revise(1);
    await screen.findByRole("tab", { name: /^門縫7/ });
    expect(tab(7).hasAttribute("data-draw")).toBe(false);
    expect(screen.getByRole("tabpanel").querySelector(".nc-panel-body[data-fresh]")).toBeTruthy();
    replies = [json(candidate(9))];
    revise(2);
    await screen.findByRole("tab", { name: /^門縫9/ });
    await waitFor(() => expect(tab(9).hasAttribute("data-draw")).toBe(true));
    expect(tab(7).hasAttribute("data-draw")).toBe(false);
  });
  it("存之前可改名字,卡上即時跟著變;改過的會送出,存完回清單並帶新角色 id", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    expect(tabs()[0].hasAttribute("data-using")).toBe(true);
    fireEvent.change(screen.getByLabelText("名字"), { target: { value: "我取的" } });
    fireEvent.change(screen.getByLabelText("一句介紹"), { target: { value: "慢慢聽" } });
    expect(tabs()[0].querySelector(".nc-name")!.textContent).toBe("我取的");
    expect(tabs()[0].querySelector(".nc-line")!.textContent).toBe("慢慢聽");
    fireEvent.change(screen.getByLabelText("讀法"), { target: { value: "我改的讀法" } });
    replies = [json({ created: true, character: { id: "new1" } }, 201)];
    fireEvent.click(button("存"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("new1"));
    expect(urls[urls.length - 1]).toBe("/api/characters");
    expect(last().candidate.name).toEqual({ "zh-Hant": "我取的", en: "Crack 1" });
    expect(last().candidate.reading).toBe("我改的讀法");
    expect(last().confirm).toBe(false);
  });
  it("預覽不放每輪提醒,用這個之後才看得到", async () => {
    await toResults();
    fireEvent.click(pick(1).getByText("讀法"));
    expect(panel().queryByRole("group", { name: "每輪提醒" })).toBeNull();
    fireEvent.click(button("選用"));
    expect(within(panel().getByRole("group", { name: "每輪提醒" })).getByText("務實")).toBeTruthy();
  });
  it("改的時候別張候選卡和換一批都鎖住,取消後焦點回到用這個", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    expect((tabs()[1] as HTMLButtonElement).disabled).toBe(true);
    expect((tabs()[0] as HTMLButtonElement).disabled).toBe(false);
    expect(button("重新生成").disabled).toBe(true);
    fireEvent.click(button("取消"));
    expect((tabs()[1] as HTMLButtonElement).disabled).toBe(false);
    expect(document.activeElement).toBe(button("選用"));
  });
  it("編輯器預填每輪提醒,改了會送出", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    const words = within(screen.getByRole("group", { name: "每輪提醒" }));
    expect(words.getByText("務實")).toBeTruthy();
    fireEvent.click(words.getByRole("button", { name: "拿掉「務實」" }));
    replies = [json({ created: true, character: { id: "new1" } }, 201)];
    fireEvent.click(button("存"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(last().depth).toBe("[{{char}}: 直率, 冷面幽默; 說話: 簡短, 乾脆, 口語]");
  });
  it("只改名字不送每輪提醒,讓它跟著新名字", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    fireEvent.change(screen.getByLabelText("名字"), { target: { value: "我取的" } });
    replies = [json({ created: true, character: { id: "new1" } }, 201)];
    fireEvent.click(button("存"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect("depth" in last()).toBe(false);
  });
  it("名字空白不能存", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    fireEvent.change(screen.getByLabelText("名字"), { target: { value: "  " } });
    expect(button("存").disabled).toBe(true);
  });
  it("有警告時先列出,再按一次才帶 confirm", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    replies = [json({ created: false, warnings: ["looks-like-instructions"] })];
    fireEvent.click(button("存"));
    await screen.findByRole("button", { name: "仍要存" });
    expect(within(document.querySelector("form.char-edit") as HTMLElement).getByText(/像指令/)).toBeTruthy();
    expect(onSaved).not.toHaveBeenCalled();
    replies = [json({ created: true, character: {} }, 201)];
    fireEvent.click(button("仍要存"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(last().confirm).toBe(true);
  });
  it("編輯器在面板原地出現,取消回面板,卡上的名字回原樣", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    expect(screen.getByRole("tabpanel").querySelector("form.char-edit")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("名字"), { target: { value: "我取的" } });
    fireEvent.click(button("取消"));
    fireEvent.click(button("放棄"));
    expect(panel().getByRole("button", { name: "選用" })).toBeTruthy();
    expect(tabs()[0].textContent).toBe("門縫1先聽");
  });
  it("存失敗時留在編輯器,顯示 den 給的原因", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    replies = [json({ code: "bad-card", params: { errors: ["too-large"] } }, 422)];
    fireEvent.click(button("存"));
    expect(await screen.findByText("角色卡太大。")).toBeTruthy();
    expect(screen.getByLabelText("名字")).toBeTruthy();
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe("離開再回來", () => {
  it("候選、選中的那張、聊的是哪篇、反應都還在,不重打 API", async () => {
    const view = await toResults();
    pick(2);
    fireEvent.click(button("重新生成"));
    fireEvent.change(screen.getByLabelText("對這批的意見"), { target: { value: "短一點" } });
    view.unmount();
    mount();
    expect(tabs()).toHaveLength(3);
    expect(tab(2).getAttribute("aria-selected")).toBe("true");
    expect(panel().getByText("對話範例:〈冰箱〉")).toBeTruthy();
    expect((screen.getByLabelText("對這批的意見") as HTMLInputElement).value).toBe("短一點");
    expect(bodies).toHaveLength(1);
  });
  it("改答案後離開,回來仍是候選、摺頁收起,沒送出的修改還在", async () => {
    const view = await toResults();
    fireEvent.click(button("修改條件"));
    fireEvent.change(formBox(), { target: { value: "退潮" } });
    view.unmount();
    mount();
    expect(tabs()).toHaveLength(3);
    expect(screen.queryByLabelText("陪你讀稿的,是什麼?")).toBeNull();
    expect(document.querySelector(".nc-strip")?.textContent).toContain("退潮");
    expect(document.querySelector(".nc-lineup")!.hasAttribute("data-stale")).toBe(true);
    fireEvent.click(button("修改條件"));
    expect(formBox().value).toBe("退潮");
    expect(bodies).toHaveLength(1);
  });
  it("返回鍵永遠是回讀伴", async () => {
    const view = await toResults();
    expect(button("返回讀伴")).toBeTruthy();
    fireEvent.click(button("修改條件"));
    expect(button("返回讀伴")).toBeTruthy();
    view.unmount();
  });
  it("還沒有候選時是攤開的問卷,沒有陣容也沒有收起", () => {
    mount();
    expect(formBox()).toBeTruthy();
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByRole("button", { name: "收起" })).toBeNull();
  });
  it("v2 的舊草稿不讀,因為候選沒有每輪提醒", () => {
    sessionStorage.setItem("hyenovel.newCharacter.v2", JSON.stringify({
      form: "門縫", wish: "", batch: [candidate(1), candidate(2), candidate(3)], batchNo: 1, reaction: "",
    }));
    mount();
    expect(formBox().value).toBe("");
    expect(screen.queryByRole("tablist")).toBeNull();
  });
  it("舊存檔沒有新欄位也接得回來", () => {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({
      form: "門縫", wish: "", batch: [candidate(1), candidate(2), candidate(3)], batchNo: 1, reaction: "", view: "form",
    }));
    mount();
    expect(tabs()).toHaveLength(3);
    expect(tabs().some(t => t.hasAttribute("data-draw"))).toBe(false);
  });
  it("重新整理(只剩 sessionStorage)也接得回來", async () => {
    const view = await toResults();
    pick(3);
    view.unmount();
    const saved = sessionStorage.getItem(DRAFT_KEY)!;
    drop();
    sessionStorage.setItem(DRAFT_KEY, saved);
    mount();
    expect(tabs()).toHaveLength(3);
    expect(tab(3).getAttribute("aria-selected")).toBe("true");
  });
  it("壞掉的存檔當作沒有", () => {
    sessionStorage.setItem(DRAFT_KEY, "{not json");
    mount();
    expect(formBox().value).toBe("");
    cleanup();
    drop();
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ form: 3 }));
    mount();
    expect(formBox().value).toBe("");
    cleanup();
    drop();
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ form: "", wish: "", batch: null, batchNo: 0, reaction: "", picked: "x" }));
    mount();
    expect(formBox().value).toBe("");
  });
  it("生成中離開,回來接著等;好了就是那批", async () => {
    let release = (_: Response) => {};
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const view = mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    expect(screen.getByRole("status")).toBeTruthy();
    view.unmount();
    mount();
    expect(screen.getByRole("status")).toBeTruthy();
    release(json({ seed: 1, candidates: [candidate(1), candidate(2), candidate(3)] }));
    await screen.findByRole("tab", { name: /^門縫1/ });
    expect(bodies).toHaveLength(1);
  });
  it("生成中離開、不在頁上時生成好了,回來直接是那批,揭曉照播", async () => {
    let release = (_: Response) => {};
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const view = mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    view.unmount();
    release(json({ seed: 1, candidates: [candidate(1), candidate(2), candidate(3)] }));
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem(DRAFT_KEY)!).batch).toHaveLength(3));
    mount();
    expect(tabs()).toHaveLength(3);
    await waitFor(() => expect(tabs().every(t => t.hasAttribute("data-draw"))).toBe(true));
  });
  it("不在頁上時生成失敗,回來說原因", async () => {
    let release = (_: Response) => {};
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const view = mount();
    fireEvent.change(formBox(), { target: { value: "門縫" } });
    fireEvent.click(go());
    view.unmount();
    release(json({ code: "candidates-failed", params: { reason: "timeout" } }, 502));
    await new Promise(r => setTimeout(r, 0));
    mount();
    expect(screen.getByRole("alert").textContent).toBe("候選生成失敗,再試一次。");
    expect(formBox().value).toBe("門縫");
  });
  it("有那批時不在頁上換一批失敗,回來是舊那批,錯誤在答案條", async () => {
    seeded();
    let release = (_: Response) => {};
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const view = mount();
    again();
    view.unmount();
    release(json({ code: "candidates-busy" }, 409));
    await new Promise(r => setTimeout(r, 0));
    mount();
    expect(tabs()).toHaveLength(3);
    expect(screen.getByRole("alert").closest(".nc-strip")).toBeTruthy();
  });
  it("帶反應換一批途中離開,回來好了焦點在第一張,不跳到換一批", async () => {
    seeded();
    let release = (_: Response) => {};
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const view = mount();
    fireEvent.click(button("重新生成"));
    fireEvent.change(screen.getByLabelText("對這批的意見"), { target: { value: "短一點" } });
    fireEvent.click(button("重新生成"));
    view.unmount();
    mount();
    await act(async () => {
      release(json({ seed: 2, candidates: [candidate(4), candidate(5), candidate(6)] }));
      await new Promise(r => setTimeout(r, 0));
    });
    expect(document.activeElement).toBe(tab(4));
  });
  it("改單張途中離開,回來送出的那句還在", async () => {
    seeded();
    let release = (_: Response) => {};
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    const view = mount();
    const p = pick(2);
    fireEvent.change(box(p), { target: { value: "再冷一點" } });
    fireEvent.click(p.getByRole("button", { name: "送出修改" }));
    view.unmount();
    mount();
    expect(tab(2).getAttribute("aria-selected")).toBe("true");
    expect((box(panel())).value).toBe("再冷一點");
    release(json(candidate(7)));
    await screen.findByRole("tab", { name: /^門縫7/ });
  });
  it("存成角色後清掉,再進來是空白問卷", async () => {
    await toResults();
    fireEvent.click(pick(1).getByRole("button", { name: "選用" }));
    replies = [json({ created: true, character: {} }, 201)];
    fireEvent.click(button("存"));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(sessionStorage.getItem(DRAFT_KEY)).toBeNull();
    cleanup();
    mount();
    expect(formBox().value).toBe("");
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });
  it("改答案重生成後,舊那批換成新的", async () => {
    const view = await toResults();
    fireEvent.click(button("修改條件"));
    fireEvent.change(formBox(), { target: { value: "退潮" } });
    fireEvent.click(go());
    await screen.findByRole("tab", { name: /^門縫4/ });
    view.unmount();
    mount();
    expect(tab(4)).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /^門縫1/ })).toBeNull();
  });
  it("sessionStorage 丟例外時照常生成,離開再回來也還在", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    drop();
    const view = await toResults();
    view.unmount();
    mount();
    expect(tabs()).toHaveLength(3);
  });
});
