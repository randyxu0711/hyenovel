import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Single from "../src/journey/Single";
import viz from "./fixtures/viz.json";

vi.mock("../src/journey/Scene3D", () => ({ default: () => null })); // jsdom 無 WebGL

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

describe("feedback 手風琴", () => {
  it("關鍵點預設只見標題,點開後見內文", async () => {
    const v = viz as { slug: string; feedback: { key_points: { title: string; body: string }[] } };
    const slug = v.slug;
    const kp = v.feedback.key_points[0];
    const { container, getByText, queryByText } = renderSingle(slug);
    await waitFor(() => expect(container.querySelector(".tabs")).toBeTruthy());
    fireEvent.click(getByText("回饋"));
    expect(getByText(kp.title)).toBeTruthy();
    expect(queryByText(kp.body)).toBeNull();
    fireEvent.click(getByText(kp.title));
    await waitFor(() => expect(getByText(kp.body)).toBeTruthy());
  });
});
