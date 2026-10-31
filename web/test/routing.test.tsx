import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

vi.mock("../src/data/client", () => ({
  getTranscript: vi.fn(async () => ({ turns: [] })),
  getStory: vi.fn(async () => ({ viz, source: "" })),
  getConclusions: vi.fn(async () => ({ conclusions: [] })),
}));
vi.mock("../src/dash/api", async orig => {
  const m = await orig<typeof import("../src/dash/api")>();
  return { ...m, api: { ...m.api,
    themes: async () => ({ themes: [olive], default: "olive" }),
    characters: async () => ({ characters: [hyena], default: "hyena" }) } };
});
import Single from "../src/journey/Single";
import Dash from "../src/dash/Dash";
import { olive, hyena } from "./dash-fixtures";

describe("routing", () => {
  it("Single 掛載後顯示載入狀態或內容", () => {
    render(<MemoryRouter initialEntries={["/story/s02"]}>
      <Routes><Route path="/story/:slug" element={<Single />} /></Routes>
    </MemoryRouter>);
    // Loading state renders immediately before data arrives
    expect(screen.getByText(/載入中/)).toBeTruthy();
  });

  it("/ 與 /w/:slug 是 Dash(載入後有三欄與設定鍵)", async () => {
    for (const path of ["/", "/w/d01"]) {
      const { unmount } = render(<MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/" element={<Dash />} /><Route path="/w/:slug" element={<Dash />} /></Routes>
      </MemoryRouter>);
      expect(await screen.findByRole("navigation")).toBeTruthy();
      expect(screen.getByRole("main")).toBeTruthy();
      unmount();
    }
  });
});
