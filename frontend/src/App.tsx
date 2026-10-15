import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRight,
  CircleHelp,
  FileText,
  House,
  Leaf,
  ListChecks,
  Menu,
  PoundSterling,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "./api";
import { useResource } from "./useResource";
import type {
  Home,
  Page,
  Recommendation,
  Reply,
  RetrofitId,
  Preferences,
  ReviewStatus,
  Workspace,
  CompletionDraft,
  CustomerSettingsUpdate,
  DemoTemplateId,
} from "./types";
import {
  Button,
  Loading,
  Modal,
  Notice,
  PageHeading,
  RecommendationDetails,
  ScoreBreakdown,
} from "./components";
import { Dashboard } from "./Dashboard";
import { HomeForm } from "./HomeForm";
import { Improvements } from "./Improvements";
import { Explore } from "./Explore";
import { Reports } from "./Reports";
import { ScenarioRail } from "./ScenarioRail";
import { Homes } from "./Homes";
import { WorkspacePage } from "./WorkspacePage";
import { CustomerPlan } from "./CustomerPlan";
import { Welcome } from "./Welcome";
import { MoneyPlan } from "./MoneyPlan";
import { useWorkspace } from "./useWorkspace";
import {
  propertyHome,
  withPreferences,
  workspaceView,
  propertyContext,
  flattenProperties,
  latestCompletedOn,
} from "./workspaceModel";
const navigation: { id: Page; label: string; icon: typeof House }[] = [
  { id: "welcome", label: "Start", icon: House },
  { id: "dashboard", label: "Dashboard", icon: House },
  { id: "home", label: "My home", icon: House },
  { id: "improvements", label: "Improvements", icon: ListChecks },
  { id: "money", label: "Costs & packages", icon: PoundSterling },
  { id: "what-if", label: "What if", icon: Sparkles },
  { id: "plan", label: "My plan", icon: FileText },
  { id: "homes", label: "Homes", icon: House },
  { id: "workspace", label: "Saved workspace", icon: ListChecks },
  { id: "reports", label: "Reports", icon: FileText },
];
function initialPage(): Page {
  return (
    navigation.find((item) => item.id === window.location.hash.slice(1))?.id ||
    "welcome"
  );
}
function newHome(): Home {
  return {
    property_id: "MY-HOME",
    property_type: null,
    age_band: null,
    region: null,
    floor_area_m2: null,
    epc_rating: null,
    electricity_kwh: null,
    gas_kwh: null,
    heating: null,
    insulation: null,
    glazing: null,
    solar_kwp: null,
    smart_controls: null,
    roof_access: null,
    listed_building: null,
    consent_confirmed: null,
    heat_pump_ready: null,
    current_value_gbp: null,
    budget_gbp: null,
    data_kind: "user_entered",
  };
}
type Dialog =
  | { type: "score" | "edit" | "about" }
  | { type: "recommendation"; item: Recommendation };
export default function App() {
  const [page, setPage] = useState<Page>(initialPage);
  const [menu, setMenu] = useState(false);
  const [retry, setRetry] = useState(0);
  const [planRetry, setPlanRetry] = useState(0);
  const [editedHome, setEditedHome] = useState<Home | null>(null);
  const [selection, setSelected] = useState<RetrofitId[] | null>(null);
  const [comparison, setComparison] = useState<RetrofitId[]>([]);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [answer, setAnswer] = useState<{
    context: string;
    reply: Reply;
  } | null>(null);
  const main = useRef<HTMLElement>(null);
  const workspace = useWorkspace();
  const saved = useMemo(
    () => (workspace.data ? workspaceView(workspace.data) : null),
    [workspace.data],
  );
  // undefined selects the first restored household; null explicitly means temporary mode.
  const [customerId, setCustomerId] = useState<string | null | undefined>(
    undefined,
  );
  const customer =
    saved?.customers.find((c) =>
      customerId === undefined ? true : c.id === customerId,
    ) || null;
  const [propertyId, setPropertyId] = useState<string | undefined>(undefined);
  const property =
    customer?.properties.find(
      (p) => propertyId === undefined || p.id === propertyId,
    ) ?? null;
  const scope = propertyContext(saved, customer, property);
  const [settingsDraft, setSettingsDraft] = useState<Omit<
    CustomerSettingsUpdate,
    "version"
  > | null>(null);
  const settingsDirty = settingsDraft !== null;
  const [preferenceDraft, setPreferenceDraft] = useState<Preferences | null>(
    null,
  );
  const [reviewDraft, setReviewDraft] = useState<ReviewStatus | null>(null);
  const [formDirty, setFormDirty] = useState(false);
  const [baselineConfirmed, setBaselineConfirmed] = useState(false);
  const [undoPlan, setUndoPlan] = useState<RetrofitId[] | null>(null);
  const selected = selection ?? property?.selected_retrofits ?? [];
  const preferences = preferenceDraft ?? property?.preferences ?? null;
  const reviewStatus = reviewDraft ?? property?.review_status ?? "new";
  const bootstrap = useResource(`bootstrap-${retry}`, async (signal) => {
    const [homes, catalogue, health] = await Promise.all([
      api.homes(signal),
      api.catalogue(signal),
      api.health(signal),
    ]);
    return { homes, catalogue, health };
  });
  const sourceHome =
    editedHome || property?.home || bootstrap.data?.homes[0] || null;
  const home =
    sourceHome && customer && property && preferences
      ? withPreferences(sourceHome, preferences, customer.customer_preferences)
      : sourceHome;
  const householdDirty = Boolean(
    customer &&
      property &&
      home &&
      JSON.stringify([
        home,
        preferences,
        [...selected].sort(),
        reviewStatus,
      ]) !==
        JSON.stringify([
          propertyHome(customer, property),
          property.preferences,
          [...property.selected_retrofits].sort(),
          property.review_status,
        ]),
  );
  const temporaryDirty =
    !customer && (editedHome !== null || selected.length > 0);
  const dirtyRef = useRef({
    formDirty,
    householdDirty,
    temporaryDirty,
    settingsDirty,
  });
  dirtyRef.current = {
    formDirty,
    householdDirty,
    temporaryDirty,
    settingsDirty,
  };
  const pageRef = useRef(page);
  pageRef.current = page;
  const mutationBusy = Boolean(
    workspace.busy && workspace.busy !== "Restoring saved workspace…",
  );
  const busyRef = useRef(mutationBusy);
  busyRef.current = mutationBusy;
  const homeKey = home ? JSON.stringify([scope, home]) : null;
  const asyncContext = JSON.stringify([scope, home, selected]);
  const activeContext = useRef(asyncContext);
  activeContext.current = asyncContext;
  const baseline = useResource(
    homeKey ? `base-${homeKey}-${retry}` : null,
    (signal) => api.assess(home!, [], signal),
  );
  const packageResult = useResource(
    homeKey && selected.length
      ? JSON.stringify([scope, home, selected, planRetry])
      : null,
    (signal) => api.assess(home!, selected, signal),
  );
  const plan = selected.length ? packageResult : baseline;
  const reply = answer?.context === asyncContext ? answer.reply : null;
  useEffect(() => {
    const listener = () => {
      const next = navigation.find(
        (item) => item.id === window.location.hash.slice(1),
      )?.id;
      if (next && next !== pageRef.current) {
        if (busyRef.current) {
          window.history.replaceState(null, "", `#${pageRef.current}`);
          return;
        }
        if (
          dirtyRef.current.formDirty &&
          !window.confirm("Discard unsaved home edits and leave this page?")
        ) {
          window.history.pushState(null, "", `#${pageRef.current}`);
          return;
        }
        setFormDirty(false);
        setDialog(null);
        setPage(next);
        setMenu(false);
      }
    };
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (
        dirtyRef.current.formDirty ||
        dirtyRef.current.householdDirty ||
        dirtyRef.current.temporaryDirty ||
        dirtyRef.current.settingsDirty
      ) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("hashchange", listener);
    window.addEventListener("popstate", listener);
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      window.removeEventListener("hashchange", listener);
      window.removeEventListener("popstate", listener);
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, []);
  function navigate(next: Page) {
    if (mutationBusy) return;
    if (
      formDirty &&
      !window.confirm("Discard unsaved home edits and leave this page?")
    )
      return;
    setFormDirty(false);
    setDialog(null);
    setPage(next);
    setMenu(false);
    if (window.location.hash !== `#${next}`)
      window.history.pushState(null, "", `#${next}`);
    window.scrollTo({ top: 0, behavior: "instant" });
    requestAnimationFrame(() => main.current?.focus({ preventScroll: true }));
  }
  function updateHome(next: Home, confirmed = false) {
    if (!customer) setCustomerId(null);
    setEditedHome(next);
    if (customer && preferences)
      setPreferenceDraft({ ...preferences, budget_gbp: next.budget_gbp });
    setBaselineConfirmed(confirmed);
    setFormDirty(false);
    setSelected([]);
    setComparison([]);
    setAnswer(null);
    setDialog(null);
    setUndoPlan(null);
  }
  function updatePlan(next: RetrofitId[]) {
    if (mutationBusy) return;
    if (!customer) setCustomerId(null);
    setUndoPlan(next.length === 0 && selected.length ? selected : null);
    setSelected(next);
    setAnswer(null);
  }
  function receiveAnswer(next: Reply) {
    if (activeContext.current !== asyncContext) return;
    if (next.applied) setSelected(next.selected_retrofits);
    setAnswer({
      context: JSON.stringify([scope, home, next.selected_retrofits]),
      reply: next,
    });
  }
  function discardAllowed() {
    return (
      !mutationBusy &&
      (!(formDirty || householdDirty || temporaryDirty || settingsDirty) ||
        window.confirm(
          "Discard unsaved household changes? Saved versions will remain unchanged.",
        ))
    );
  }
  function resetDrafts(keepSettings = false) {
    workspace.clearIssue();
    if (!keepSettings) setSettingsDraft(null);
    setEditedHome(null);
    setSelected(null);
    setComparison([]);
    setAnswer(null);
    setPreferenceDraft(null);
    setReviewDraft(null);
    setFormDirty(false);
    setDialog(null);
    setBaselineConfirmed(false);
    setUndoPlan(null);
  }
  function applyWorkspace(next: Workspace | null, keepSettings = false) {
    resetDrafts(keepSettings);
    const nextView = next ? workspaceView(next) : null;
    const owner =
      nextView?.customers.find((c) => c.id === customer?.id) ??
      nextView?.customers[0];
    setCustomerId(owner?.id ?? null);
    setPropertyId(
      owner?.properties.find((p) => p.id === property?.id)?.id ??
        owner?.properties[0]?.id,
    );
  }
  function pickCustomer(id: string) {
    if (!discardAllowed()) return;
    resetDrafts();
    setPropertyId(undefined);
    setCustomerId(id && id !== "MY-HOME" ? id : null);
    if (id === "MY-HOME") {
      setEditedHome(newHome());
      setPage("home");
      window.history.pushState(null, "", "#home");
    }
  }
  function pickProperty(id: string) {
    if (!customer?.properties.some((p) => p.id === id) || !discardAllowed())
      return;
    resetDrafts();
    setPropertyId(id);
  }
  function pickHome(id: string) {
    if (!discardAllowed()) return;
    resetDrafts();
    setCustomerId(null);
    setPropertyId(undefined);
    if (id === "MY-HOME") {
      updateHome(newHome());
      setPage("home");
      window.history.pushState(null, "", "#home");
      return;
    }
    const found = bootstrap.data?.homes.find((item) => item.property_id === id);
    if (found) updateHome(structuredClone(found));
  }
  function changePreferences(next: Preferences) {
    setPreferenceDraft(next);
    setSelected(selected.filter((id) => !next.deferred_retrofits.includes(id)));
    setComparison(
      comparison.filter((id) => !next.deferred_retrofits.includes(id)),
    );
    setAnswer(null);
    setUndoPlan(null);
  }
  async function saveProperty() {
    if (!customer || !property || !home || !preferences || formDirty) return;
    const context = asyncContext;
    const update = {
      version: property.version,
      // Persist raw property preferences, not inherited customer exclusions.
      home: withPreferences(home, preferences),
      preferences,
      selected_retrofits: selected,
      review_status: reviewStatus,
      baseline_confirmed_after_completion: baselineConfirmed,
    };
    const next = await workspace.mutate(
      "Saving property changes…",
      (signal) =>
        saved?.schema_version === 2
          ? api.saveProperty(
              customer.id,
              property.id,
              { ...update, customer_version: customer.version },
              signal,
            )
          : api.saveCustomer(
              customer.id,
              { ...update, version: customer.version },
              signal,
            ),
      "Property changes saved.",
    );
    if (next !== undefined && activeContext.current === context)
      applyWorkspace(next, true);
  }
  async function complete(event: CompletionDraft) {
    if (!customer || !property || householdDirty || formDirty || settingsDirty)
      return;
    const context = asyncContext;
    const next = await workspace.mutate(
      "Recording completed work…",
      (signal) =>
        saved?.schema_version === 2
          ? api.completeProperty(
              customer.id,
              property.id,
              {
                ...event,
                version: property.version,
                customer_version: customer.version,
              },
              signal,
            )
          : api.completeRetrofit(
              customer.id,
              { ...event, version: customer.version },
              signal,
            ),
      "Completed work saved. Old fuel readings cleared; update the baseline before estimating further savings.",
    );
    if (next !== undefined && activeContext.current === context)
      applyWorkspace(next);
  }
  async function saveSettings() {
    if (!customer || !settingsDraft || saved?.schema_version !== 2) return;
    const context = asyncContext;
    const next = await workspace.mutate(
      "Saving customer settings…",
      (signal) =>
        api.saveCustomerSettings(
          customer.id,
          { ...settingsDraft, version: customer.version },
          signal,
        ),
      "Customer settings saved. Property budgets remain independent.",
    );
    if (next !== undefined && activeContext.current === context) {
      setSettingsDraft(null);
      setAnswer(null);
      setComparison([]);
    }
  }
  async function addProperty(template: DemoTemplateId) {
    if (
      !customer ||
      saved?.schema_version !== 2 ||
      customer.properties.length >= 8 ||
      !discardAllowed()
    )
      return;
    const context = asyncContext;
    const next = await workspace.mutate(
      "Adding fictional template property…",
      (signal) =>
        api.addProperty(
          customer.id,
          { customer_version: customer.version, template_id: template },
          signal,
        ),
      "Fictional property added. No other property's preferences, plans or history were copied.",
    );
    if (next && activeContext.current === context) {
      const added = workspaceView(next)
        .customers.find((c) => c.id === customer.id)
        ?.properties.find(
          (p) => !customer.properties.some((previous) => previous.id === p.id),
        );
      applyWorkspace(next);
      if (added) setPropertyId(added.id);
    }
  }
  function closeDialog() {
    if (dialog?.type === "edit") {
      if (formDirty && !window.confirm("Discard unsaved home edits?")) return;
      setFormDirty(false);
    }
    setDialog(null);
  }
  const nativeClick = (
    event: React.MouseEvent<HTMLAnchorElement>,
    next: Page,
  ) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.defaultPrevented
    )
      return;
    event.preventDefault();
    navigate(next);
  };
  const catalogue = bootstrap.data?.catalogue || [];
  const savedWorkspacePage = (
    <WorkspacePage
      key={scope}
      state={{ ...workspace, data: saved }}
      settingsDraft={settingsDraft}
      templates={bootstrap.data?.homes ?? []}
      draft={
        customer && property && preferences
          ? {
              customer,
              property,
              preferences,
              reviewStatus,
              dirty: householdDirty,
            }
          : null
      }
      actions={{
        create: async () => {
          if (!discardAllowed()) return;
          const next = await workspace.mutate(
            "Creating fictional workspace…",
            (signal) => api.createWorkspace(signal),
            "Fictional workspace created. No temporary own-home inputs were copied.",
          );
          if (next !== undefined) applyWorkspace(next);
        },
        restore: async () => {
          if (!discardAllowed()) return;
          const next = await workspace.restore();
          if (next !== undefined) applyWorkspace(next);
        },
        remove: async () => {
          if (!discardAllowed()) return;
          const next = await workspace.mutate(
            "Deleting workspace…",
            async (signal) => {
              await api.deleteWorkspace(signal);
              return null;
            },
            "Workspace deleted. No saved records remain; you are back in temporary mode.",
          );
          if (next !== undefined) applyWorkspace(next);
        },
        export: workspace.exportData,
        save: saveProperty,
        settings: setSettingsDraft,
        saveSettings,
        addProperty,
        preferences: changePreferences,
        review: setReviewDraft,
        complete,
        openFirst: () => {
          const first = saved?.customers[0];
          if (first) pickCustomer(first.id);
        },
        editHome: () => navigate("home"),
      }}
    />
  );
  const renderNav = (mobile = false) =>
    navigation.map((item) => (
      <a
        key={item.id}
        href={`#${item.id}`}
        aria-current={page === item.id ? "page" : undefined}
        onClick={(event) => {
          nativeClick(event, item.id);
        }}
      >
        {mobile ? (
          <item.icon size={18} strokeWidth={1.6} aria-hidden="true" />
        ) : null}
        {item.label}
      </a>
    ));
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="site-header">
        <a
          className="brand"
          href="#dashboard"
          onClick={(event) => {
            nativeClick(event, "dashboard");
          }}
        >
          <span className="brand-mark">
            <House size={29} strokeWidth={1.3} aria-hidden="true" />
            <Leaf size={15} aria-hidden="true" />
          </span>
          <span>
            GreenHome<small>Thoughtful improvements. Informed choices.</small>
          </span>
        </a>
        <nav className="desktop-nav" aria-label="Main navigation">
          {renderNav()}
        </nav>
        <div className="header-actions">
          <span className="pilot-badge">England & Wales pilot</span>
          <button
            className="icon-button"
            aria-label="About this assessment"
            onClick={() => setDialog({ type: "about" })}
          >
            <CircleHelp size={20} />
          </button>
          <button
            className="icon-button mobile-menu-button"
            aria-label={menu ? "Close navigation" : "Open navigation"}
            aria-expanded={menu}
            aria-controls="mobile-navigation"
            onClick={() => setMenu((value) => !value)}
          >
            {menu ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </header>
      {menu ? (
        <nav
          id="mobile-navigation"
          className="mobile-navigation"
          aria-label="Mobile navigation"
        >
          {renderNav(true)}
        </nav>
      ) : null}
      <div
        className={`workspace-bar ${page === "welcome" ? "welcome-hidden" : ""}`}
      >
        <div>
          <span className="status-dot" />
          <span>
            {bootstrap.error
              ? "Connection needs attention"
              : customer
                ? `${customer.label} / ${property?.label ?? "Choose a property"} · ${householdDirty || settingsDirty ? "Unsaved changes" : "Saved"}`
                : "Temporary screening · not saved"}
          </span>
        </div>
        <div className="scope-selectors">
          {saved ? (
            <>
              <label className="home-selector">
                <span>Customer</span>
                <select
                  name="selected_customer"
                  aria-label="Customer"
                  value={customer?.id ?? ""}
                  disabled={Boolean(workspace.busy)}
                  onChange={(e) => pickCustomer(e.target.value)}
                >
                  <option value="">Temporary screening</option>
                  {saved.customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                  <option value="MY-HOME">Enter your own home</option>
                </select>
              </label>
              <label className="home-selector">
                <span>Property</span>
                <select
                  name="selected_property"
                  aria-label="Property"
                  value={property?.id ?? ""}
                  disabled={!customer || Boolean(workspace.busy)}
                  onChange={(e) => pickProperty(e.target.value)}
                >
                  {!customer ? (
                    <option value="">No saved customer selected</option>
                  ) : null}
                  {customer?.properties.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label} · {p.home.property_id}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : null}
          {!customer ? (
            <label className="home-selector">
              <span>Temporary home</span>
              <select
                name="selected_home"
                aria-label="Choose a home"
                value={home?.property_id || ""}
                disabled={!bootstrap.data || Boolean(workspace.busy)}
                onChange={(event) => pickHome(event.target.value)}
              >
                {!bootstrap.data ? (
                  <option value="">Loading homes…</option>
                ) : null}
                {bootstrap.data?.homes.map((item) => (
                  <option key={item.property_id} value={item.property_id || ""}>
                    {item.property_id} · {item.property_type}
                  </option>
                ))}
                <option value="MY-HOME">Enter your own home</option>
              </select>
            </label>
          ) : null}
        </div>
      </div>
      <div
        className={`continuity-bar ${page === "welcome" ? "welcome-hidden" : ""}`}
      >
        <span>
          {customer
            ? "Private fictional workspace · customer view and Homes adviser view"
            : "Try a fictional home or screen your own. Temporary inputs are lost on reload."}
        </span>
        <Button onClick={() => navigate("workspace")}>
          {workspace.data ? "Manage saved workspace" : "Save a demo workspace"}
        </Button>
        <a href="#plan" onClick={(e) => nativeClick(e, "plan")}>
          Go to my plan
        </a>
      </div>
      <div
        className={`workspace-layout ${["welcome", "money", "reports", "homes", "workspace", "plan", "home"].includes(page) ? "reports-layout" : ""}`}
      >
        <main id="main" ref={main} tabIndex={-1} className="main-content">
          {page === "welcome" ? (
            <Welcome
              onExample={() => {
                if (!discardAllowed()) return;
                resetDrafts();
                setCustomerId(null);
                setPropertyId(undefined);
                setEditedHome(null);
                navigate("dashboard");
              }}
              onOwnHome={() => pickHome("MY-HOME")}
              onEvidence={() => navigate("reports")}
            />
          ) : null}
          <p className="sr-only" role="status" aria-live="polite">
            {!["welcome", "workspace", "homes", "reports"].includes(page)
              ? plan.loading
                ? "Updating the current home plan."
                : plan.data
                  ? selected.length
                    ? "Current home plan calculated. Results are ready."
                    : "Current home assessed. Choose improvements to calculate a plan."
                  : ""
              : ""}
          </p>
          {page === "workspace" ? savedWorkspacePage : null}
          {bootstrap.error && page !== "workspace" && page !== "welcome" ? (
            <section className="connection-state card">
              <h1>Let’s reconnect your home</h1>
              <Notice kind="error">{bootstrap.error}</Notice>
              <Button variant="primary" onClick={() => setRetry((n) => n + 1)}>
                <RefreshCw size={16} />
                Retry connection
              </Button>
            </section>
          ) : null}
          {(bootstrap.loading || !home) &&
          !bootstrap.error &&
          page !== "workspace" &&
          page !== "welcome" ? (
            <div className="dashboard-skeleton" aria-busy="true">
              <Loading label="Preparing your home workspace…" />
              <div className="skeleton-hero" />
              <div className="skeleton-cards">
                <div />
                <div />
                <div />
                <div />
              </div>
            </div>
          ) : null}
          {page !== "workspace" &&
          page !== "welcome" &&
          home &&
          !bootstrap.loading &&
          !bootstrap.error ? (
            <>
              {baseline.error && !["workspace", "homes"].includes(page) ? (
                <Notice kind="error">
                  <p>{baseline.error}</p>
                  <Button onClick={() => setRetry((n) => n + 1)}>
                    Retry assessment
                  </Button>
                  <Button onClick={() => navigate("home")}>
                    Review home details
                  </Button>
                </Notice>
              ) : null}
              {page === "homes" ? (
                <Homes
                  homes={bootstrap.data?.homes || []}
                  customers={saved?.customers || null}
                  workspaceId={saved?.id}
                  openHome={(id) => {
                    const target = flattenProperties(
                      saved?.customers ?? [],
                    ).find(({ property }) => property.home.property_id === id);
                    if (!discardAllowed()) return;
                    resetDrafts();
                    if (target) {
                      setCustomerId(target.customer.id);
                      setPropertyId(target.property.id);
                    } else {
                      setCustomerId(null);
                      setEditedHome(
                        bootstrap.data?.homes.find(
                          (h) => h.property_id === id,
                        ) || null,
                      );
                    }
                    setPage("dashboard");
                    window.history.pushState(null, "", "#dashboard");
                    requestAnimationFrame(() => main.current?.focus());
                  }}
                />
              ) : page === "plan" ? (
                <CustomerPlan
                  home={home}
                  assessment={plan.data}
                  selected={selected}
                  customer={customer}
                  property={property}
                  schemaVersion={saved?.schema_version}
                  unsaved={householdDirty || settingsDirty}
                />
              ) : page === "home" ? (
                <>
                  <PageHeading title="A little detail makes a better plan">
                    Start with what you know. Leave anything uncertain blank,
                    and we’ll explain what it affects.
                  </PageHeading>
                  {customer && property ? (
                    <p className="property-target">
                      Editing {customer.label} / {property.label} ·{" "}
                      {property.home.property_id}. Changes apply only to this
                      property.
                    </p>
                  ) : null}
                  <section className="card home-editor">
                    <HomeForm
                      key={homeKey}
                      home={home}
                      initialMode={
                        home.property_id === "MY-HOME" && !customer
                          ? "guided"
                          : "full"
                      }
                      workspaceBaseline={property?.baseline_status}
                      baselineAfterDate={latestCompletedOn(property)}
                      onDirtyChange={setFormDirty}
                      onSave={(next, confirmed) => {
                        updateHome(next, confirmed);
                        setPage("dashboard");
                        window.history.pushState(null, "", "#dashboard");
                      }}
                    />
                  </section>
                </>
              ) : page === "money" ? (
                <MoneyPlan
                  key={homeKey}
                  home={home}
                  selected={selected}
                  onChange={updatePlan}
                />
              ) : page === "reports" ? (
                <Reports home={home} assessment={plan.data} />
              ) : baseline.loading ? (
                <Loading label="Calculating the current home…" />
              ) : baseline.data ? (
                <>
                  {page === "dashboard" ? (
                    <Dashboard
                      home={home}
                      baseline={baseline.data}
                      plan={plan.data}
                      planLoading={plan.loading}
                      selected={selected}
                      onChange={updatePlan}
                      edit={() => setDialog({ type: "edit" })}
                      navigate={navigate}
                      showScore={() => setDialog({ type: "score" })}
                      showDetails={(item) =>
                        setDialog({ type: "recommendation", item })
                      }
                    />
                  ) : null}
                  {page === "improvements" ? (
                    <Improvements
                      key={homeKey}
                      home={home}
                      baseline={baseline.data}
                      selected={selected}
                      onChange={updatePlan}
                      compareSelected={comparison}
                      setCompareSelected={setComparison}
                      showDetails={(item) =>
                        setDialog({ type: "recommendation", item })
                      }
                    />
                  ) : null}
                  {page === "what-if" ? (
                    <Explore
                      key={homeKey}
                      home={home}
                      selected={selected}
                      assessment={plan.data}
                      health={bootstrap.data?.health || null}
                      catalogue={catalogue}
                      onApply={updatePlan}
                      reply={reply}
                      onReply={receiveAnswer}
                      edit={() => setDialog({ type: "edit" })}
                    />
                  ) : null}
                </>
              ) : null}
            </>
          ) : null}
        </main>
        {![
          "welcome",
          "money",
          "reports",
          "workspace",
          "homes",
          "plan",
          "home",
        ].includes(page) &&
        home &&
        !bootstrap.error ? (
          <ScenarioRail
            key={homeKey}
            baseline={baseline.data}
            assessment={plan.data}
            selected={selected}
            onChange={updatePlan}
            loading={plan.loading}
            error={plan.error}
            retry={() => {
              setPlanRetry((n) => n + 1);
              if (!selected.length) setRetry((n) => n + 1);
            }}
            catalogue={catalogue}
            openImprovements={() => navigate("improvements")}
            openQuestions={() => navigate("what-if")}
            openDetails={(item) => setDialog({ type: "recommendation", item })}
            undo={
              undoPlan
                ? () => {
                    setSelected(undoPlan);
                    setUndoPlan(null);
                    setAnswer(null);
                  }
                : undefined
            }
          />
        ) : null}
      </div>
      <footer className="site-footer">
        <span>
          <Leaf size={15} aria-hidden="true" />
          GreenHome <span className="footer-separator">/</span> Team 225
        </span>
        <p>
          Estimates to inform a conversation, not replace a qualified
          assessment.
        </p>
        <button
          className="text-link"
          onClick={() => setDialog({ type: "about" })}
        >
          Scope & limitations <ArrowUpRight size={14} />
        </button>
      </footer>
      {dialog ? (
        <Modal
          title={
            dialog.type === "edit"
              ? customer && property
                ? `${customer.label} / ${property.label}`
                : "Your home details"
              : dialog.type === "score"
                ? "Your score, explained"
                : dialog.type === "recommendation"
                  ? dialog.item.name
                  : "A clear starting point"
          }
          close={closeDialog}
        >
          {dialog.type === "edit" && home ? (
            <HomeForm
              key={homeKey}
              home={home}
              workspaceBaseline={property?.baseline_status}
              baselineAfterDate={latestCompletedOn(property)}
              onDirtyChange={setFormDirty}
              onSave={updateHome}
              onCancel={closeDialog}
            />
          ) : null}
          {dialog.type === "score" && baseline.data ? (
            <ScoreBreakdown assessment={baseline.data} />
          ) : null}
          {dialog.type === "recommendation" ? (
            <RecommendationDetails item={dialog.item} />
          ) : null}
          {dialog.type === "about" ? (
            <div className="about-copy">
              <p>
                This is an England and Wales retrofit-screening pilot.
                Demonstration homes are fictional. All money is shown in pounds
                sterling.
              </p>
              <p>
                The score and scenario estimates come from documented
                calculations. The energy benchmark is trained on anonymised NEED
                records. Property-value ranges are synthetic illustrations, not
                market valuations or proven resale gains.
              </p>
              <p>
                The selected AI provider can explain only approved evidence.
                When unavailable, the app identifies its local fallback. No live
                AI accuracy or guaranteed savings are claimed.
              </p>
              <p>
                Confirm permissions, building condition and installation
                requirements with a qualified professional before spending.
                Own-home inputs stay temporary. Only fictional household data is
                saved after explicit workspace consent; use no personal or
                confidential details.
              </p>
              <Button
                variant="primary"
                onClick={() => {
                  setDialog(null);
                  navigate("reports");
                }}
              >
                View evidence & model results
              </Button>
            </div>
          ) : null}
        </Modal>
      ) : null}
    </>
  );
}
