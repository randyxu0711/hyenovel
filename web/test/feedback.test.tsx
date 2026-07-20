import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Single from "../src/journey/Single";
import viz from "./fixtures/viz.json";


beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) =>
    url.includes("viz.json")
      ? Promise.resolve({ ok: true, json: () => Promise.resolve(viz) } as Response)
      : Promise.resolve({ ok: true, text: () => Promise.resolve("　　原文。") } as Response),
  ));
});

function renderSingle(slug: string) {
  return render(
    <MemoryRouter initialEntries={[`/story/${slug}`]}>
      <Routes><Route path="/story/:slug" element={<Single />} /></Routes>
    </MemoryRouter>,
  );
}

// 回饋頁是「讀」的層:判斷內文、原文證據、枝節都直接在場,不必逐張點進討論才看得到
// (舊契約「點開才見內文」其實是點進 NodeTalk——回饋頁自己淪為目錄,已翻案)。
// 點標題仍是討論啟動器:開啟該節點的沉浸討論。
describe("回饋頁", () => {
  it("判斷內文/證據/枝節直接可讀", async () => {
    const v = viz as unknown as {
      slug: string;
      feedback: { key_points: { title: string; body: string; quotes: { quote: string }[] }[]; minor: string[] };
    };
    const kp = v.feedback.key_points[0];
    const { container, getByText } = renderSingle(v.slug);
    await waitFor(() => expect(container.querySelector(".sb-bar")).toBeTruthy());
    fireEvent.click(getByText("回饋"));
    expect(getByText(kp.title)).toBeTruthy();
    expect(getByText(kp.body)).toBeTruthy();
    expect(getByText(`「${kp.quotes[0].quote}」`)).toBeTruthy();
    expect(getByText(v.feedback.minor[0])).toBeTruthy();
  });

  it("點標題開啟該節點的沉浸討論", async () => {
    const v = viz as unknown as { slug: string; feedback: { key_points: { title: string }[] } };
    const kp = v.feedback.key_points[0];
    const { container, getByText } = renderSingle(v.slug);
    await waitFor(() => expect(container.querySelector(".sb-bar")).toBeTruthy());
    fireEvent.click(getByText("回饋"));
    fireEvent.click(getByText(kp.title));
    await waitFor(() => expect(container.querySelector(".talk")).toBeTruthy());
  });
});
