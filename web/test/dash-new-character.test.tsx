import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLang } from "../src/dash/i18n";
import NewCharacter from "../src/dash/NewCharacter";
import { marked, PASSAGE, QUESTIONS, quotesIn, WORDS } from "../src/dash/questionnaire";

const candidate = (n: number, warnings: string[] = []) => ({
  name: { "zh-Hant": `門縫${n}`, en: `Crack ${n}` }, form: { "zh-Hant": "門縫", en: "door crack" },
  line: { "zh-Hant": "先聽", en: "Listens" }, reading: `讀法${n}`, sample: `讀到「暗暗紅紅」我停住了(${n})。`,
  axes: [], card: {}, warnings,
});
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let bodies: { answers: Record<string, string>; lang: string }[];
let replies: Response[];
let urls: string[];
let onSaved: () => Promise<void>;

const mount = () => render(<NewCharacter onClose={() => {}} onSaved={onSaved} />);
const go = () => screen.getByRole("button", { name: "生成候選" }) as HTMLButtonElement;
const option = (text: RegExp) => screen.getByRole("button", { name: text });

beforeEach(() => {
  setLang("zh-Hant");
  bodies = [];
  urls = [];
  onSaved = vi.fn(async () => {});
  replies = [json({ seed: 1, candidates: [candidate(1), candidate(2), candidate(3, ["looks-like-instructions"])] })];
  vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => {
    urls.push(_u);
    bodies.push(JSON.parse(String(init?.body)));
    return replies.shift() ?? json({ seed: 2, candidates: [candidate(4), candidate(5), candidate(6)] });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("問卷資料", () => {
  it("短文和 den 用的同一份", () => {
    expect(PASSAGE).toBe(readFileSync(join(__dirname, "../../marrow/prompts/sample_passage.md"), "utf8").trim());
  });
  it("注意力和回應形式的引文都逐字出自短文,中英同一組", () => {
    for (const q of QUESTIONS.filter(x => x.id !== "returns")) for (const set of q.sets) for (const o of set.options) {
      const zh = quotesIn(o["zh-Hant"]!), en = quotesIn(o.en!);
      expect(zh.length).toBeGreaterThan(0);
      expect(en.every(x => zh.includes(x))).toBe(true);
      for (const x of zh.filter(z => z !== "我")) expect(PASSAGE).toContain(x);
    }
  });
  it("每題每組選項數相同,換組不改變維度數", () => {
    for (const q of QUESTIONS) expect(new Set(q.sets.map(s => s.options.length)).size).toBe(1);
  });
  it("詞卡每類三張", () => {
    expect(WORDS.map(r => r.length)).toEqual([3, 3, 3, 3, 3, 3]);
  });
  it("marked 標出引文、合併重疊、略過找不到的", () => {
    const text = "甲乙丙丁戊";
    expect(marked(text, [])).toEqual([{ text, on: false }]);
    expect(marked(text, ["乙丙", "丙丁", "沒有"])).toEqual([
      { text: "甲", on: false }, { text: "乙丙丁", on: true }, { text: "戊", on: false },
    ]);
  });
});

describe("作答", () => {
  it("全部沒答不能生成;答了形體就能", () => {
    mount();
    expect(go().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "退潮" } });
    expect(go().disabled).toBe(false);
  });
  it("形體輸入框不放例子", () => {
    mount();
    expect(screen.getByLabelText("陪你讀稿的,是什麼?").getAttribute("placeholder")).toBeNull();
  });
  it("詞卡要按了才出現,換詞不打 API,選了填進形體", () => {
    mount();
    expect(screen.queryByRole("button", { name: "校對員" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "沒想法" }));
    fireEvent.click(screen.getByRole("button", { name: "校對員" }));
    expect((screen.getByLabelText("陪你讀稿的,是什麼?") as HTMLInputElement).value).toBe("校對員");
    fireEvent.click(screen.getByRole("button", { name: "沒想法" }));
    fireEvent.click(screen.getByRole("button", { name: "換一批詞" }));
    expect(screen.getByRole("button", { name: "代書" })).toBeTruthy();
    expect(bodies).toEqual([]);
  });
  it("按沒想法後可以全留白生成", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "沒想法" }));
    expect(go().disabled).toBe(false);
    fireEvent.click(go());
    await screen.findByText("門縫1");
    expect(Object.values(bodies[0].answers).every(v => v === "")).toBe(true);
  });
  it("選項可微調,送出改過的文字;只送有答的", async () => {
    mount();
    fireEvent.click(option(/暗暗紅紅/));
    const edit = screen.getByLabelText("微調這句") as HTMLTextAreaElement;
    expect(edit.value).toContain("暗暗紅紅");
    fireEvent.change(edit, { target: { value: "我改過的" } });
    fireEvent.click(go());
    await screen.findByText("門縫1");
    expect(bodies[0].answers).toEqual({ form: "", attention: "我改過的", returns: "", response: "", instance: "" });
    expect(bodies[0].lang).toBe("zh-Hant");
  });
  it("再按一次取消選擇,回到沒答", () => {
    mount();
    fireEvent.click(option(/暗暗紅紅/));
    expect(go().disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /取消選擇/ }));
    expect(go().disabled).toBe(true);
  });
  it("自己寫:空白算沒答,有字才算", () => {
    mount();
    fireEvent.click(screen.getAllByRole("button", { name: "自己寫" })[0]);
    expect(go().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("自己寫"), { target: { value: "  " } });
    expect(go().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("自己寫"), { target: { value: "我的話" } });
    expect(go().disabled).toBe(false);
  });
  it("換一組不打 API,換掉選項並清掉這題的答案", () => {
    mount();
    fireEvent.click(option(/暗暗紅紅/));
    fireEvent.click(screen.getAllByRole("button", { name: "換一組" })[0]);
    expect(screen.getByRole("button", { name: /灶腳/ })).toBeTruthy();
    expect(go().disabled).toBe(true);
    expect(bodies).toEqual([]);
  });
  it("滑到選項時,短文標出它提到的地方", () => {
    const { container } = mount();
    expect(container.querySelector(".nc-wave")).toBeNull();
    fireEvent.mouseEnter(option(/暗暗紅紅/).closest("li")!);
    expect(container.querySelector(".nc-wave")?.textContent).toBe("暗暗紅紅");
  });
});

describe("候選", () => {
  const toResults = async () => {
    mount();
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "門縫" } });
    fireEvent.click(go());
    await screen.findByText("門縫1");
  };
  const toResults2 = async () => {
    mount();
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "門縫" } });
    fireEvent.click(go());
    await screen.findByText("門縫2");
  };
  it("生成時顯示狀態和已跑時間,不是假進度", async () => {
    mount();
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "門縫" } });
    fireEvent.click(go());
    expect(screen.getByRole("status").textContent).toContain("0:00");
    expect(screen.queryByRole("progressbar")).toBeNull();
    await screen.findByText("門縫1");
  });
  it("列三個候選,像指令的文字要顯示警告", async () => {
    await toResults();
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getAllByRole("note")).toHaveLength(1);
  });
  it("形體和名字一樣時不重複顯示", async () => {
    replies = [json({ seed: 1, candidates: [{ ...candidate(1), name: { "zh-Hant": "門縫", en: "Crack" } }, candidate(2), candidate(3)] })];
    await toResults2();
    const [same, other] = screen.getAllByRole("article");
    expect(same.querySelector("small")).toBeNull();
    expect(other.querySelector("small")?.textContent).toBe("門縫");
  });
  it("換一批用同樣答案重打、不帶 seed", async () => {
    await toResults();
    fireEvent.click(screen.getByRole("button", { name: "換一批" }));
    await screen.findByText("門縫4");
    expect(bodies[1].answers).toEqual(bodies[0].answers);
    expect(bodies[1]).not.toHaveProperty("seed");
  });
  it("改答案回到問卷,答案還在", async () => {
    await toResults();
    fireEvent.click(screen.getByRole("button", { name: "改答案" }));
    expect((screen.getByLabelText("陪你讀稿的,是什麼?") as HTMLInputElement).value).toBe("門縫");
  });
  it("第一批失敗回問卷顯示原因,答案還在", async () => {
    replies = [json({ code: "candidates-failed", params: { reason: "timeout" } }, 502)];
    mount();
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "門縫" } });
    fireEvent.click(go());
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("候選生成失敗,再試一次。"));
    expect((screen.getByLabelText("陪你讀稿的,是什麼?") as HTMLInputElement).value).toBe("門縫");
  });
  it("額度用完講額度,不講再試一次", async () => {
    replies = [json({ code: "candidates-failed", params: { reason: "usage-limit" } }, 502)];
    mount();
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "門縫" } });
    fireEvent.click(go());
    await waitFor(() => expect(screen.getByRole("alert").textContent).not.toContain("再試一次"));
  });
  it("換一批失敗時,原本的候選留著", async () => {
    await toResults();
    replies = [json({ code: "candidates-busy" }, 409)];
    fireEvent.click(screen.getByRole("button", { name: "換一批" }));
    await screen.findByRole("alert");
    expect(screen.getByText("門縫1")).toBeTruthy();
  });
});

describe("改候選與存卡", () => {
  const toResults = async () => {
    mount();
    fireEvent.change(screen.getByLabelText("陪你讀稿的,是什麼?"), { target: { value: "門縫" } });
    fireEvent.click(go());
    await screen.findByText("門縫1");
    return screen.getAllByRole("article").map(a => within(a));
  };
  const revise = (card: ReturnType<typeof within>, text = "再冷一點") => {
    fireEvent.change(card.getByLabelText("一句回饋"), { target: { value: text } });
    fireEvent.click(card.getByRole("button", { name: "改這張" }));
  };
  const last = () => bodies[bodies.length - 1] as unknown as Record<string, any>;

  it("回饋空白不能送,有字才能", async () => {
    const [card] = await toResults();
    const send = card.getByRole("button", { name: "改這張" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(card.getByLabelText("一句回饋"), { target: { value: "   " } });
    expect(send.disabled).toBe(true);
    fireEvent.change(card.getByLabelText("一句回饋"), { target: { value: "冷一點" } });
    expect(send.disabled).toBe(false);
  });
  it("只送一張,只更新那一張,回饋清空", async () => {
    const [, second] = await toResults();
    replies = [json(candidate(9))];
    revise(second);
    await screen.findByText("門縫9");
    expect(urls[urls.length - 1]).toBe("/api/characters/candidates/revise");
    expect(last().feedback).toBe("再冷一點");
    expect(last().candidate.name["zh-Hant"]).toBe("門縫2");
    expect(screen.getByText("門縫1")).toBeTruthy();
    expect(screen.getByText("門縫3")).toBeTruthy();
    expect(screen.queryByText("門縫2")).toBeNull();
    expect((screen.getAllByLabelText("一句回饋")[1] as HTMLInputElement).value).toBe("");
  });
  it("改的時候只有這張掃描,其他花額度的按鈕都停用", async () => {
    let release = (_: Response) => {};
    const cards = await toResults();
    replies = [new Promise<Response>(r => { release = r; }) as unknown as Response];
    fireEvent.change(cards[2].getByLabelText("一句回饋"), { target: { value: "別的" } });
    revise(cards[0]);
    await waitFor(() => expect(document.querySelectorAll('.blob[data-state="scanning"]')).toHaveLength(1));
    expect(screen.getAllByRole("article")[0].querySelector('.blob[data-state="scanning"]')).toBeTruthy();
    expect((cards[2].getByRole("button", { name: "改這張" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "換一批" }) as HTMLButtonElement).disabled).toBe(true);
    expect(cards[0].getByText("0:00")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "改答案" }));
    expect(go().disabled).toBe(true);
    release(json(candidate(9)));
    await waitFor(() => expect(go().disabled).toBe(false));
  });
  it("失敗時原內容和回饋都留著,顯示原因", async () => {
    const [card] = await toResults();
    replies = [json({ code: "candidates-failed", params: { reason: "usage-limit" } }, 502)];
    revise(card);
    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).not.toContain("再試一次");
    expect(screen.getByText("門縫1")).toBeTruthy();
    expect((card.getByLabelText("一句回饋") as HTMLInputElement).value).toBe("再冷一點");
  });
  it("存之前可改名字,改過的會送出,存完回清單", async () => {
    const [card] = await toResults();
    fireEvent.click(card.getByRole("button", { name: "用這個" }));
    fireEvent.change(screen.getByLabelText("名字"), { target: { value: "我取的" } });
    fireEvent.change(screen.getByLabelText("讀法"), { target: { value: "我改的讀法" } });
    replies = [json({ created: true, character: {} }, 201)];
    fireEvent.click(screen.getByRole("button", { name: "存" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(urls[urls.length - 1]).toBe("/api/characters");
    expect(last().candidate.name).toEqual({ "zh-Hant": "我取的", en: "Crack 1" });
    expect(last().candidate.reading).toBe("我改的讀法");
    expect(last().confirm).toBe(false);
  });
  it("名字空白不能存", async () => {
    const [card] = await toResults();
    fireEvent.click(card.getByRole("button", { name: "用這個" }));
    fireEvent.change(screen.getByLabelText("名字"), { target: { value: "  " } });
    expect((screen.getByRole("button", { name: "存" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("有警告時先列出,再按一次才帶 confirm;取消回候選", async () => {
    const [card] = await toResults();
    fireEvent.click(card.getByRole("button", { name: "用這個" }));
    replies = [json({ created: false, warnings: ["looks-like-instructions"] })];
    fireEvent.click(screen.getByRole("button", { name: "存" }));
    await screen.findByRole("button", { name: "仍要存" });
    expect(within(document.querySelector("form.char-edit") as HTMLElement).getByText(/像是要改寫規則/)).toBeTruthy();
    expect(onSaved).not.toHaveBeenCalled();
    replies = [json({ created: true, character: {} }, 201)];
    fireEvent.click(screen.getByRole("button", { name: "仍要存" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(last().confirm).toBe(true);
  });
  it("編輯器可取消,候選回來", async () => {
    const [card] = await toResults();
    fireEvent.click(card.getByRole("button", { name: "用這個" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.getAllByRole("article")).toHaveLength(3);
  });
  it("存失敗時留在編輯器,顯示 den 給的原因", async () => {
    const [card] = await toResults();
    fireEvent.click(card.getByRole("button", { name: "用這個" }));
    replies = [json({ code: "bad-card", params: { errors: ["too-large"] } }, 422)];
    fireEvent.click(screen.getByRole("button", { name: "存" }));
    expect(await screen.findByText("角色卡太大。")).toBeTruthy();
    expect(screen.getByLabelText("名字")).toBeTruthy();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
