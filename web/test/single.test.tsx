import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

vi.mock("../src/data/client", () => ({
  getStory: vi.fn(async () => ({ viz, source: "　　原文第一行。" })),
}));
vi.mock("../src/journey/Scene3D", () => ({ default: () => null })); // jsdom 無 WebGL
import Single from "../src/journey/Single";

beforeEach(() => vi.clearAllMocks());

function mount() {
  return render(<MemoryRouter initialEntries={["/story/s02"]}>
    <Routes><Route path="/story/:slug" element={<Single />} /></Routes></MemoryRouter>);
}

describe("Single", () => {
  it("預設顯示原文,可切到意圖鏈", async () => {
    mount();
    await waitFor(() => expect(screen.getByText(/原文第一行/)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "意圖鏈" }));
    await waitFor(() => expect(document.querySelector("g.cnode")).toBeTruthy());
  });
});
