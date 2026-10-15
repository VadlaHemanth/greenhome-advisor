import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  CheckCheck,
  MessageCircle,
  ShieldCheck,
} from "lucide-react";
import { api, errorMessage } from "./api";
import { useResource } from "./useResource";
import type {
  Assessment,
  CatalogueItem,
  Health,
  Home,
  Reply,
  RetrofitId,
} from "./types";
import { RETROFIT_IDS } from "./types";
import { number } from "./format";
import {
  Button,
  Loading,
  Notice,
  PageHeading,
  packageNames,
} from "./components";
import { DecisionEvidence } from "./DecisionEvidence";
import { activeProvider } from "./provider";

export function Explore({
  home,
  selected,
  assessment,
  health,
  catalogue,
  onApply,
  reply,
  onReply,
  edit,
}: {
  home: Home;
  selected: RetrofitId[];
  assessment: Assessment | null;
  health: Health | null;
  catalogue: CatalogueItem[];
  onApply: (ids: RetrofitId[]) => void;
  reply: Reply | null;
  onReply: (reply: Reply) => void;
  edit: () => void;
}) {
  const provider = activeProvider(health);
  const providerContext = JSON.stringify(provider);
  const [question, setQuestion] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hideReply, setHideReply] = useState(false);
  const [decisionRun, setDecisionRun] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const context = JSON.stringify([home, selected, providerContext]);
  const homeContext = JSON.stringify(home);
  const latest = useRef(context);
  latest.current = context;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    controller.current?.abort();
    setBusy(false);
    setError(null);
  }, [context]);
  useEffect(() => {
    setConsent(false);
  }, [homeContext, providerContext]);
  const decision = useResource(
    decisionRun ? JSON.stringify([home, decisionRun]) : null,
    (signal) => api.decision(home, signal),
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !question.trim() || !assessment) return;
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    const requestedContext = context;
    setBusy(true);
    setError(null);
    setHideReply(true);
    try {
      const result = await api.whatIf(
        home,
        selected,
        question.trim(),
        consent && provider.configured,
        current.signal,
      );
      if (!current.signal.aborted && latest.current === requestedContext) {
        onReply(result);
        setHideReply(false);
      }
    } catch (cause) {
      if (!current.signal.aborted && latest.current === requestedContext)
        setError(errorMessage(cause));
    } finally {
      if (!current.signal.aborted && latest.current === requestedContext)
        setBusy(false);
    }
  }
  const recommended = decision.data?.recommended_package;
  const canApply =
    Array.isArray(recommended) &&
    recommended.every(
      (id) =>
        RETROFIT_IDS.includes(id) &&
        assessment?.recommendations.some(
          (item) => item.id === id && item.feasible,
        ),
    ) &&
    decision.data?.status === "available";
  return (
    <>
      <PageHeading title="Explore before you decide">
        Ask about the current home, or check how your plan holds up when
        screening assumptions change.
      </PageHeading>
      <section className="question-card card">
        <div className="section-heading">
          <h2>
            <MessageCircle size={19} aria-hidden="true" />
            Ask a what-if
          </h2>
          <span className={`tag ${provider.configured ? "sage" : ""}`}>
            {provider.configured
              ? `${provider.label} configured · opt-in`
              : "Local explanation mode"}
          </span>
        </div>
        <p>
          Ask where to start, why a measure suits this home, or what your plan
          means. Questions that name improvements can also add or remove them.
          Change budgets, deferred options and home details in their forms—not
          by asking here.
        </p>
        <form onSubmit={submit}>
          <label className="form-field">
            <span>Your question</span>
            <textarea
              name="what_if_question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              maxLength={600}
              required
              placeholder="What if I add loft insulation and a heat pump?"
            />
          </label>
          <div className="question-examples" aria-label="Example questions">
            {[
              "What should I do first?",
              "Which improvements suit my home?",
              "Explain this plan",
              "Explain my score",
              "Add loft insulation",
            ].map((text) => (
              <button
                type="button"
                key={text}
                onClick={() => setQuestion(text)}
              >
                {text}
              </button>
            ))}
          </div>
          <label className="check-row consent-check">
            <input
              type="checkbox"
              name="use_gemini"
              checked={consent}
              disabled={!provider.configured || busy}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>
              <strong>Use {provider.label} for this submitted question</strong>
              <small>{provider.notice}</small>
              {provider.serverNotice ? (
                <small>{provider.serverNotice}</small>
              ) : null}
            </span>
          </label>
          <div className="form-actions">
            <Button
              type="submit"
              variant="primary"
              disabled={busy || !assessment || !question.trim()}
            >
              {busy ? (
                "Validating & recomputing…"
              ) : (
                <>
                  Send question <ArrowRight size={16} aria-hidden="true" />
                </>
              )}
            </Button>
            {busy ? (
              <Button
                onClick={() => {
                  controller.current?.abort();
                  setBusy(false);
                }}
              >
                Cancel request
              </Button>
            ) : null}
          </div>
        </form>
        {!provider.configured ? (
          <p className="fine-print">
            Live {provider.label} is not enabled by the server. Local
            explanations use the same calculated evidence.
          </p>
        ) : null}
        {!assessment ? (
          <Notice>
            Wait for a valid current plan, or fix its feasibility/budget, before
            submitting a question.
          </Notice>
        ) : null}
        {error ? <Notice kind="error">{error}</Notice> : null}
        {reply && !hideReply && !busy && !error ? (
          <div className="explanation" aria-live="polite">
            <span
              className={`tag ${["live_gemini", "live_llm"].includes(reply.explanation_mode) ? "sage" : "gold"}`}
            >
              {reply.needs_clarification
                ? "Clarification needed"
                : reply.explanation_mode === "live_gemini"
                  ? "Live Gemini · validated claims"
                  : reply.explanation_mode === "live_llm"
                    ? `Live ${reply.provider === "xkiro" ? "Qwen via Xkiro" : reply.provider === "gemini" ? "Gemini" : provider.label} · validated claims`
                    : "Local calculation explanation"}
            </span>
            <p>{reply.message}</p>
            {reply.applied ? (
              <div className="applied-note">
                <CheckCheck size={16} aria-hidden="true" />
                Applied to your plan:{" "}
                {packageNames(reply.selected_retrofits, catalogue)}
              </div>
            ) : null}
            <ul>
              {reply.lines.map((line, index) => (
                <li key={`${index}-${line}`}>{line}</li>
              ))}
            </ul>
            <details>
              <summary>How this answer was produced</summary>
              <p>
                Parser: {reply.parser_mode}. Explanation:{" "}
                {reply.explanation_mode}. Status: {reply.status}.
              </p>
              <p>
                Every numerical statement is rendered from engine outputs. The
                selected AI provider can choose only approved, evidence-backed
                claims; it cannot supply estimates.
              </p>
            </details>
          </div>
        ) : null}
        <p className="fine-print">
          No bills, grants, alternative technologies or unsupported claims.
          Conflicting requests ask for clarification. No model-generated
          estimates.
        </p>
      </section>
      <section className="decision-card card">
        <p className="sr-only" role="status" aria-live="polite">
          {decision.loading
            ? "Checking your plan."
            : decision.data
              ? "Decision check finished. Results are available below."
              : ""}
        </p>
        <div className="section-heading">
          <div>
            <span className="tag gold">Decision check</span>
            <h2 className="display">
              A useful question: would the plan change?
            </h2>
          </div>
          <ShieldCheck size={30} strokeWidth={1.2} aria-hidden="true" />
        </div>
        <p>
          Stress-test feasible packages against analyst-selected heating and
          solar assumptions. This check prioritises purchased-energy savings—not
          property-value illustrations.
        </p>
        <Button
          onClick={() => setDecisionRun((n) => n + 1)}
          variant="primary"
          disabled={decision.loading}
        >
          {decision.loading
            ? "Checking scenarios…"
            : decision.data
              ? "Run decision check again"
              : "Check the plan’s sensitivity"}
        </Button>
        {decision.loading ? (
          <Loading label="Testing feasible packages across assumption scenarios…" />
        ) : null}
        {decision.error ? <Notice kind="error">{decision.error}</Notice> : null}
        {decision.data ? (
          decision.data.status === "available" ? (
            <div
              className="decision-result"
              aria-label="Decision check results"
            >
              <h3>
                {decision.data.stable === true
                  ? "Stable across tested scenarios"
                  : decision.data.stable === false
                    ? "The preferred package changes across scenarios"
                    : "Stability is unavailable"}
              </h3>
              <p>
                {number(decision.data.scenario_count)} scenarios tested ·{" "}
                {number(decision.data.feasible_package_count)} feasible
                packages.
              </p>
              <p>
                <strong>Suggested robust package</strong>
                <br />
                {packageNames(recommended, catalogue)}
              </p>
              <dl className="summary-list">
                <div>
                  <dt>Largest gap in tested scenarios</dt>
                  <dd>
                    {number(decision.data.regret_kwh, 1)}
                    <small>
                      kWh/year compared with the best tested package
                    </small>
                  </dd>
                </div>
              </dl>
              <DecisionEvidence
                decision={decision.data}
                catalogue={catalogue}
              />
              {decision.data.next_check ? (
                <Notice>
                  <strong>{decision.data.next_check.question}</strong>
                  <p>{decision.data.next_check.reason}</p>
                  {decision.data.next_check.field ? (
                    <Button onClick={edit}>Review this home assumption</Button>
                  ) : null}
                </Notice>
              ) : null}
              <Button
                disabled={!canApply}
                onClick={() => canApply && onApply(recommended!)}
              >
                Use this package & reassess{" "}
                <ArrowRight size={16} aria-hidden="true" />
              </Button>
              <details>
                <summary>Stress-test assumptions and limitations</summary>
                <ul>
                  {[
                    ...(decision.data.assumptions || []),
                    ...(decision.data.warnings || []),
                  ].map((text, i) => (
                    <li key={i}>{text}</li>
                  ))}
                </ul>
              </details>
            </div>
          ) : (
            <Notice>
              {decision.data.warnings?.join(" ") ||
                "This home does not have enough suitable data for a decision check. Review its details and permissions."}
            </Notice>
          )
        ) : null}
        <p className="fine-print">
          Stress cases are not probabilities or guarantees. “Stable” means only
          stable across the scenarios actually tested.
        </p>
      </section>
    </>
  );
}
