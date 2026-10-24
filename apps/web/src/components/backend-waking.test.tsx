import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BackendUnavailable, BackendWaking } from "./backend-waking";

describe("BackendWaking", () => {
  it("AC20: announces that the server is starting up", () => {
    render(<BackendWaking />);

    expect(screen.getByRole("status")).toHaveTextContent("Starting up the server");
  });
});

describe("BackendUnavailable", () => {
  it("AC20: offers Try again", async () => {
    const onRetry = vi.fn();
    render(<BackendUnavailable reason="unreachable" onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't reach the DocFlow server");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("explains an unexpected error differently from an unreachable server", () => {
    render(<BackendUnavailable reason="error" onRetry={() => undefined} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });
});
