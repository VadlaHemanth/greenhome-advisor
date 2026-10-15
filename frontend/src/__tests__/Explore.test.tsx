import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Explore } from "../Explore";
import { api, ApiError } from "../api";
import type { Decision, RetrofitId } from "../types";
import {
  assessment,
  catalogue,
  decision,
  deferred,
  health,
  home,
  reply,
} from "./fixtures";

function props() {
  return {
    home,
    selected: ["heat_pump"] as RetrofitId[],
    assessment,
    health,
    catalogue,
    onApply: vi.fn(),
    reply: null,
    onReply: vi.fn(),
    edit: vi.fn(),
  };
}
function ask() {
  fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
    target: { value: "Explain my score" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Send question/ }));
}

describe("bounded questions and decision check", () => {
  it("uses the active Qwen provider and notice, not the legacy Gemini alias", async () => {
    const question = vi.spyOn(api, "whatIf").mockResolvedValue(reply);
    render(
      <Explore
        {...props()}
        health={{
          ...health,
          gemini_configured: false,
          llm_configured: true,
          llm_provider: "xkiro",
          llm_label: "Qwen via Xkiro",
          llm_model: "fixture",
          llm_data_notice: "Test server disclosure",
        }}
      />,
    );
    const consent = screen.getByRole("checkbox", {
      name: /Use Qwen via Xkiro/,
    });
    expect(consent).toHaveProperty("disabled", false);
    expect(consent).toHaveProperty("checked", false);
    expect(
      screen.getByText(/Its retention and hosting are unverified/),
    ).toBeTruthy();
    expect(screen.getByText("Test server disclosure")).toBeTruthy();
    expect(screen.queryByText(/Use Gemini/)).toBeNull();
    fireEvent.click(consent);
    ask();
    await waitFor(() => expect(question).toHaveBeenCalled());
    expect(question.mock.calls[0][3]).toBe(true);
  });

  it("labels live_llm as Qwen and local fallback as local", () => {
    const input = {
      ...props(),
      health: {
        ...health,
        llm_configured: true,
        llm_provider: "xkiro" as const,
      },
    };
    const { rerender } = render(
      <Explore
        {...input}
        reply={{ ...reply, explanation_mode: "live_llm", provider: "xkiro" }}
      />,
    );
    expect(
      screen.getByText("Live Qwen via Xkiro · validated claims"),
    ).toBeTruthy();
    rerender(
      <Explore
        {...input}
        reply={{ ...reply, explanation_mode: "fallback", provider: "xkiro" }}
      />,
    );
    expect(screen.getByText("Local calculation explanation")).toBeTruthy();
    expect(
      screen.queryByText("Live Qwen via Xkiro · validated claims"),
    ).toBeNull();
  });

  it("revokes consent and cancels pending questions when provider changes", async () => {
    const pending = deferred<typeof reply>();
    const question = vi.spyOn(api, "whatIf").mockReturnValue(pending.promise);
    const input = props();
    const { rerender } = render(
      <Explore {...input} health={{ ...health, gemini_configured: true }} />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Use Gemini/ }));
    ask();
    rerender(
      <Explore
        {...input}
        health={{ ...health, llm_configured: true, llm_provider: "xkiro" }}
      />,
    );
    expect(question.mock.calls[0][4]?.aborted).toBe(true);
    expect(
      screen.getByRole("checkbox", { name: /Use Qwen via Xkiro/ }),
    ).toHaveProperty("checked", false);
    await act(async () => pending.resolve(reply));
    expect(input.onReply).not.toHaveBeenCalled();
  });

  it("does not allow a true legacy alias to override active-provider unavailability", () => {
    render(
      <Explore
        {...props()}
        health={{
          ...health,
          gemini_configured: true,
          llm_configured: false,
          llm_provider: "xkiro",
        }}
      />,
    );
    expect(
      screen.getByRole("checkbox", { name: /Use Qwen via Xkiro/ }),
    ).toHaveProperty("disabled", true);
  });
  it("makes no request on mount or by merely choosing an example", () => {
    const question = vi.spyOn(api, "whatIf");
    const check = vi.spyOn(api, "decision");
    render(<Explore {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Explain my score" }));
    expect(
      screen.getByRole("textbox", { name: "Your question" }),
    ).toHaveProperty("value", "Explain my score");
    expect(question).not.toHaveBeenCalled();
    expect(check).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps remote use off by default even when health says configured", async () => {
    const question = vi.spyOn(api, "whatIf").mockResolvedValue(reply);
    const input = {
      ...props(),
      health: { ...health, gemini_configured: true },
    };
    render(<Explore {...input} />);
    expect(screen.getByText("Gemini configured · opt-in")).toBeTruthy();
    expect(screen.queryByText("Gemini available · opt-in")).toBeNull();
    ask();
    await waitFor(() => expect(input.onReply).toHaveBeenCalledWith(reply));
    expect(question.mock.calls[0][3]).toBe(false);
  });

  it("sends true only after the explicit consent checkbox is checked", async () => {
    const question = vi.spyOn(api, "whatIf").mockResolvedValue(reply);
    render(
      <Explore {...props()} health={{ ...health, gemini_configured: true }} />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Use Gemini/ }));
    ask();
    await waitFor(() => expect(question).toHaveBeenCalled());
    expect(question.mock.calls[0][3]).toBe(true);
  });

  it("disables remote consent when Gemini is unavailable", () => {
    render(<Explore {...props()} />);
    expect(screen.getByRole("checkbox", { name: /Use Gemini/ })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByText("Local explanation mode")).toBeTruthy();
    expect(
      screen.getByText(
        "Live Gemini is not enabled by the server. Local explanations use the same calculated evidence.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/Configure credentials/)).toBeNull();
  });

  it("resets consent when changing homes", () => {
    const input = {
      ...props(),
      health: { ...health, gemini_configured: true },
    };
    const { rerender } = render(<Explore {...input} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Use Gemini/ }));
    expect(screen.getByRole("checkbox", { name: /Use Gemini/ })).toHaveProperty(
      "checked",
      true,
    );
    rerender(
      <Explore {...input} home={{ ...home, property_id: "OTHER-HOME" }} />,
    );
    expect(screen.getByRole("checkbox", { name: /Use Gemini/ })).toHaveProperty(
      "checked",
      false,
    );
  });

  it("does not submit questions without a valid current assessment", () => {
    const question = vi.spyOn(api, "whatIf");
    render(<Explore {...props()} assessment={null} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
      target: { value: "Add loft insulation" },
    });
    expect(
      screen.getByRole("button", { name: /Send question/ }),
    ).toHaveProperty("disabled", true);
    expect(question).not.toHaveBeenCalled();
  });

  it("aborts on selection change and ignores a late what-if response", async () => {
    const pending = deferred<typeof reply>();
    const question = vi.spyOn(api, "whatIf").mockReturnValue(pending.promise);
    const input = props();
    const { rerender } = render(<Explore {...input} />);
    ask();
    const signal = question.mock.calls[0][4];
    rerender(<Explore {...input} selected={["loft_insulation"]} />);
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve({ ...reply, applied: true });
    });
    expect(input.onReply).not.toHaveBeenCalled();
  });

  it("cancels requests when the user presses Cancel", async () => {
    const pending = deferred<typeof reply>();
    const question = vi.spyOn(api, "whatIf").mockReturnValue(pending.promise);
    const input = props();
    render(<Explore {...input} />);
    ask();
    fireEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    expect(question.mock.calls[0][4]?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(reply);
    });
    expect(input.onReply).not.toHaveBeenCalled();
  });

  it("removes a previous explanation when a replacement request fails", async () => {
    vi.spyOn(api, "whatIf").mockRejectedValue(
      new ApiError("Service unavailable", 500, "failure"),
    );
    render(<Explore {...props()} reply={reply} />);
    expect(screen.getByText(reply.lines[0])).toBeTruthy();
    ask();
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Service unavailable",
    );
    expect(screen.queryByText(reply.lines[0])).toBeNull();
  });

  it("shows the exact backend quota fallback as local, not live Gemini", () => {
    const quotaReply = {
      ...reply,
      status: "fallback_quota",
      message:
        "Gemini credits are depleted; using local engine-grounded evidence.",
    };
    render(<Explore {...props()} reply={quotaReply} />);
    expect(screen.getByText(quotaReply.message)).toBeTruthy();
    expect(screen.getByText("Local calculation explanation")).toBeTruthy();
    expect(screen.queryByText("Live Gemini · validated claims")).toBeNull();
  });

  it("handles unavailable decision arrays as null without offering Apply", async () => {
    vi.spyOn(api, "decision").mockResolvedValue({
      ...decision,
      status: "unavailable",
      recommended_package: null,
      packages: null,
      scenarios: null,
      assumptions: null,
      warnings: null,
    });
    render(<Explore {...props()} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Check the plan’s sensitivity/ }),
    );
    await screen.findByText(/does not have enough suitable data/);
    expect(
      screen.queryByRole("button", { name: /Use this package/ }),
    ).toBeNull();
  });

  it("handles absent optional fields in an unavailable decision response", async () => {
    vi.spyOn(api, "decision").mockResolvedValue({
      status: "unavailable",
    } as Decision);
    render(<Explore {...props()} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Check the plan’s sensitivity/ }),
    );
    await screen.findByText(/does not have enough suitable data/);
  });

  it("describes stability only across tested scenarios and applies the returned package", async () => {
    vi.spyOn(api, "decision").mockResolvedValue(decision);
    const input = props();
    render(<Explore {...input} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Check the plan’s sensitivity/ }),
    );
    await screen.findByText("Stable across tested scenarios");
    expect(screen.getByText("Largest gap in tested scenarios")).toBeTruthy();
    expect(screen.queryByText(/Worst-case gap/)).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: /Use this package & reassess/ }),
    );
    expect(input.onApply).toHaveBeenCalledWith(["loft_insulation"]);
    expect(
      screen.queryByText(/uniquely optimal|outperforms|guaranteed best/i),
    ).toBeNull();
  });

  it("does not apply a returned catalogue ID that is currently infeasible", async () => {
    vi.spyOn(api, "decision").mockResolvedValue(decision);
    const input = props();
    render(
      <Explore
        {...input}
        assessment={{
          ...assessment,
          recommendations: assessment.recommendations.map((r) => ({
            ...r,
            feasible: false,
          })),
        }}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Check the plan’s sensitivity/ }),
    );
    const apply = await screen.findByRole("button", {
      name: /Use this package & reassess/,
    });
    expect(apply).toHaveProperty("disabled", true);
    fireEvent.click(apply);
    expect(input.onApply).not.toHaveBeenCalled();
  });

  it("retains the normal form when the decision endpoint is not available", async () => {
    vi.spyOn(api, "decision").mockRejectedValue(
      new ApiError("Decision endpoint not ready", 404, "unavailable"),
    );
    render(<Explore {...props()} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Check the plan’s sensitivity/ }),
    );
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Decision endpoint not ready",
    );
    expect(screen.getByRole("textbox", { name: "Your question" })).toBeTruthy();
  });

  it("never claims a standard assessment is available when both services are unavailable", async () => {
    vi.spyOn(api, "decision").mockRejectedValue(
      new ApiError(
        "Cannot connect to the calculation service",
        0,
        "connection",
      ),
    );
    render(<Explore {...props()} assessment={null} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Check the plan’s sensitivity/ }),
    );
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Cannot connect to the calculation service",
    );
    expect(
      screen.queryByText(/standard assessment is still available/),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: /Send question/ }),
    ).toHaveProperty("disabled", true);
  });
});
