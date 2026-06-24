import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import Camera from "../src/journey/Camera";

describe("Camera", () => {
  it("render stage + cam,並包住 children", () => {
    const { container, getByTestId } = render(
      <Camera stage="catalog"><div data-testid="kid" /></Camera>,
    );
    expect(container.querySelector(".stage")).toBeTruthy();
    expect(container.querySelector(".cam")).toBeTruthy();
    expect(getByTestId("kid")).toBeTruthy();
  });
});
