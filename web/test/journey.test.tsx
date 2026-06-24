import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Journey from "../src/journey/Journey";
import index from "./fixtures/index.json";
import viz from "./fixtures/viz.json";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const body = url.includes("index.json") ? index
      : url.includes("viz.json") ? viz : null;
    if (body) return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    return Promise.resolve({ ok: true, text: () => Promise.resolve("　　原文一段。") } as Response);
  }));
});

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<Journey />} />
        <Route path="/story/:slug" element={<Journey />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Journey", () => {
  it("/ 顯示總覽(overview),不顯示麵包屑", async () => {
    const { container, getByTestId } = at("/");
    await waitFor(() => expect(getByTestId("overview")).toBeTruthy());
    expect(container.querySelector(".crumb")).toBeNull();
  });
  it("/story/:slug 進單篇:顯示麵包屑且有 single 面板", async () => {
    const slug = (index as { stories: { slug: string }[] }).stories[0].slug;
    const { container } = at(`/story/${slug}`);
    await waitFor(() => expect(container.querySelector(".single")).toBeTruthy());
    expect(container.querySelector(".crumb")).toBeTruthy();
  });
});
