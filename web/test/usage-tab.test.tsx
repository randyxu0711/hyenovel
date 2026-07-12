import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

const AGG = {
  slug: "s02", empty: false,
  phases: { analyst: { input:100,output:50,cache_creation:200,cache_read:900,cost_usd:0.42,turns:1 } },
  total: { input:100,output:50,cache_creation:200,cache_read:900,cost_usd:0.42 },
  cache_read_ratio: 0.75, retry_cost_usd: 0, retry_count: 0,
};

vi.mock("../src/data/client", () => ({
  getStory: vi.fn(async () => ({ viz, source: "　　原文。" })),
  getUsage: vi.fn(async () => AGG),
}));
import Single from "../src/journey/Single";

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true }));
});

describe("Single 用量 tab", () => {
  it("點『用量』開出用量面板", async () => {
    render(<MemoryRouter initialEntries={["/story/s02"]}>
      <Routes><Route path="/story/:slug" element={<Single />} /></Routes></MemoryRouter>);
    await waitFor(() => expect(document.querySelector(".sb-bar")).toBeTruthy());
    fireEvent.click(document.querySelector(".sb-textabs")!.querySelectorAll("button")[2]);   // 第三顆 = 用量
    await waitFor(() => expect(document.querySelector(".u")).toBeTruthy());
  });
});
