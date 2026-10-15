import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReleaseIdentity } from "../ReleaseIdentity";

describe("release identity", () => {
  it("shows only the reported revision and environment", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          name: "GreenHome Advisor",
          version: "2026.10",
          revision: "a".repeat(40),
          environment: "hosted",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<ReleaseIdentity />);
    expect(await screen.findByText(/Revision aaaaaaaa/)).toBeTruthy();
    expect(screen.getByText(/Hosted runtime/)).toBeTruthy();
  });
  it("does not imply a version was verified when unavailable", async () => {
    render(<ReleaseIdentity />);
    expect(
      await screen.findByText(/Release metadata unavailable/),
    ).toBeTruthy();
    expect(screen.queryByText(/Hosted runtime/)).toBeNull();
  });
});
