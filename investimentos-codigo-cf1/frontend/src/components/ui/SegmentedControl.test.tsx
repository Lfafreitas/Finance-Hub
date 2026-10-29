import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SegmentedControl } from "./SegmentedControl";

describe("SegmentedControl", () => {
  it("botões com aria-pressed e a pílula na opção escolhida", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { container } = render(
      <SegmentedControl
        label="Período"
        value="b"
        onChange={onChange}
        options={[
          { id: "a", label: "A" },
          { id: "b", label: "B" },
          { id: "c", label: "C" },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: "B" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "A" })).toHaveAttribute("aria-pressed", "false");
    const pill = container.querySelector("[aria-hidden=true]") as HTMLElement;
    expect(pill.style.transform).toBe("translateX(100%)");
    await user.click(screen.getByRole("button", { name: "C" }));
    expect(onChange).toHaveBeenCalledWith("c");
  });
});
