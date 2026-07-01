import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import viz from "./fixtures/viz.json";

vi.mock("../src/data/client", () => ({
  getStory: vi.fn(async () => ({ viz, source: "　　原文第一行。" })),
}));
import Single from "../src/journey/Single";

beforeEach(() => vi.clearAllMocks());

function mount() {
  return render(<MemoryRouter initialEntries={["/story/s02"]}>
    <Routes><Route path="/story/:slug" element={<Single />} /></Routes></MemoryRouter>);
}

describe("Single", () => {
  it("進單篇顯示骨舞台,三段切換在,可開原文覆蓋層", async () => {
    mount();
    await waitFor(() => expect(document.querySelector("svg.bonestage")).toBeTruthy());
    expect(screen.getByRole("button", { name: "因果鏈" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "原文" }));
    await waitFor(() => expect(screen.getByText(/原文第一行/)).toBeTruthy());
  });
});
