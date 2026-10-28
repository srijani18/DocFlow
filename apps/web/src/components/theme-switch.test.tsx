import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { THEME_KEY } from "@/lib/theme";

import { ThemeSwitch } from "./theme-switch";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "";
  const media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  window.matchMedia = (() => media) as unknown as typeof window.matchMedia;
});

describe("ThemeSwitch", () => {
  it("AC2: switches theme, shows the choice and remembers it", async () => {
    render(<ThemeSwitch />);

    const group = screen.getByRole("group", { name: "Theme" });
    expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: "Dark" }));

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(group).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Light" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
