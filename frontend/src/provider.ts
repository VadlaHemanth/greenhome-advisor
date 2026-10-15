import type { Health } from "./types";

export function activeProvider(health: Health | null) {
  const provider = health?.llm_provider || "gemini";
  const label =
    provider === "xkiro" ? "Qwen via Xkiro" : health?.llm_label || "Gemini";
  const notice =
    provider === "xkiro"
      ? "Sends your question and de-identified calculation evidence to Xkiro, a third-party gateway for Qwen. Its retention and hosting are unverified. Do not include real personal or confidential information. Off by default."
      : "Sends the question and de-identified calculation evidence to Google. No real personal or confidential information. Off by default.";
  return {
    provider,
    label,
    configured: health?.llm_configured ?? health?.gemini_configured ?? false,
    notice,
    serverNotice: health?.llm_data_notice,
    model: health?.llm_model,
  };
}
