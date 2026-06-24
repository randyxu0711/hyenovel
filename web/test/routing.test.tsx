import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Single from "../src/journey/Single";

describe("routing", () => {
  it("Single 讀到 slug", () => {
    render(<MemoryRouter initialEntries={["/story/s02"]}>
      <Routes><Route path="/story/:slug" element={<Single />} /></Routes>
    </MemoryRouter>);
    expect(screen.getByTestId("single-slug").textContent).toBe("s02");
  });
});
