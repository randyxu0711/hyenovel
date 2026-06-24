import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

vi.mock("../src/data/client", () => ({
  getStory: vi.fn(async () => ({ viz, source: "" })),
}));
import Single from "../src/journey/Single";

describe("routing", () => {
  it("Single 掛載後顯示載入狀態或內容", () => {
    render(<MemoryRouter initialEntries={["/story/s02"]}>
      <Routes><Route path="/story/:slug" element={<Single />} /></Routes>
    </MemoryRouter>);
    // Loading state renders immediately before data arrives
    expect(screen.getByText(/載入中/)).toBeTruthy();
  });
});
