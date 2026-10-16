import {
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import { ArrowLeft, ArrowRight, Minus, Plus, RotateCcw } from "lucide-react";
import type { Home, Recommendation, RetrofitId } from "./types";
import { RETROFIT_IDS } from "./types";
import { buildScene } from "./home3d/geometry";
import {
  adjustCamera,
  DEFAULT_CAMERA,
  MAX_ZOOM,
  MIN_ZOOM,
  type Camera,
} from "./home3d/math";
import { comparisonState, FEATURE_NAMES, FEATURE_NOTES } from "./home3d/state";
import { SceneSvg } from "./home3d/SceneSvg";
import { useSceneMotion } from "./home3d/useSceneMotion";
import "./homeComparison.css";

export type HomeComparisonProps = {
  home: Home;
  selected: RetrofitId[];
  recommendations: Recommendation[];
  loading: boolean;
};
type View = "current" | "proposed" | "compare";
type Drag = {
  id: number;
  x: number;
  y: number;
  yaw: number;
  intent: "pending" | "horizontal" | "vertical";
};

export function HomeComparison(props: HomeComparisonProps) {
  // Reset interaction/animation immediately for *any* changed home inputs,
  // including two anonymous homes. Never retain the previous home's scene.
  return <Comparison key={JSON.stringify(props.home)} {...props} />;
}

function Comparison({
  home,
  selected,
  recommendations,
  loading,
}: HomeComparisonProps) {
  const [camera, setCamera] = useState<Camera>({ ...DEFAULT_CAMERA });
  const [view, setView] = useState<View>("compare");
  const [focus, setFocus] = useState<RetrofitId | null>(null);
  const root = useRef<HTMLElement | null>(null);
  const drag = useRef<Drag | null>(null);
  const id = useId();
  const state = useMemo(
    () => comparisonState(home, selected, recommendations, loading),
    [home, selected, recommendations, loading],
  );
  const current = useMemo(
    () => buildScene(home, state.current),
    [home, state.current],
  );
  const proposed = useMemo(
    () => buildScene(home, state.proposed),
    [home, state.proposed],
  );
  const proposalIds = state.changes
    .filter((c) => c.status === "proposed")
    .map((c) => c.id);
  const motion = useSceneMotion(root, proposalIds.join(","));
  const rotate = (yaw: number) => setCamera((c) => adjustCamera(c, { yaw }));
  const zoom = (delta: number) =>
    setCamera((c) => adjustCamera(c, { zoom: delta }));
  const reset = () => {
    setCamera({ ...DEFAULT_CAMERA });
    setFocus(null);
    motion.stop();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === "ArrowLeft") rotate(-Math.PI / 10);
    else if (event.key === "ArrowRight") rotate(Math.PI / 10);
    else if (event.key === "+" || event.key === "=") zoom(0.1);
    else if (event.key === "-" || event.key === "_") zoom(-0.1);
    else if (event.key === "Home" || event.key.toLowerCase() === "r") reset();
    else return; // Up/down remain native page scrolling keys.
    event.preventDefault();
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || event.isPrimary === false) return;
    drag.current = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      yaw: camera.yaw,
      intent: "pending",
    };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!start || start.id !== event.pointerId || start.intent === "vertical")
      return;
    const dx = event.clientX - start.x,
      dy = event.clientY - start.y;
    if (start.intent === "pending") {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 7) return;
      if (Math.abs(dy) >= Math.abs(dx)) {
        start.intent = "vertical";
        return;
      }
      start.intent = "horizontal";
      event.currentTarget.setPointerCapture?.(event.pointerId);
    }
    // CSS pan-y pinch-zoom leaves vertical page scroll and browser zoom native.
    setCamera((c) =>
      adjustCamera({ ...c, yaw: start.yaw }, { yaw: dx * 0.009 }),
    );
  };
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.id !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drag.current = null;
  };
  const focusFeature = (feature: RetrofitId) => {
    setFocus(feature);
    // Bring useful surfaces back into sight after an orbit, but do not invent
    // different camera positions for before and after.
    setCamera((c) => ({ ...c, yaw: DEFAULT_CAMERA.yaw }));
    motion.play();
  };
  const context =
    home.property_type === "Flat"
      ? "Shared-building illustration. The highlighted band is symbolic, not a known flat position. Roof rights and equipment locations are not inferred."
      : current.contextHomes > 0
        ? "Muted adjoining homes show the building family only; their features are not assessed."
        : "A model of the recorded building family, not the actual property.";
  return (
    <section
      ref={root}
      className={`home-comparison${motion.animating ? " hc-animate" : ""}`}
      data-animating={motion.animating ? "true" : undefined}
      aria-labelledby={`${id}-heading`}
    >
      <header className="hc-heading">
        <div>
          <h2 id={`${id}-heading`}>Your home, before &amp; after</h2>
          <p>{home.property_type ?? "Property type unknown"}</p>
        </div>
        <span className="hc-model-label">Illustrative 3D</span>
      </header>
      <div className="hc-view-switch" role="group" aria-label="Comparison view">
        {(["current", "proposed", "compare"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={view === mode}
            aria-label={
              mode === "compare" ? "Compare both homes" : `Show ${mode} home`
            }
            onClick={() => setView(mode)}
          >
            {mode === "current"
              ? "Current"
              : mode === "proposed"
                ? "Proposed"
                : "Compare"}
          </button>
        ))}
      </div>
      <div className={`hc-scenes hc-view-${view}`}>
        {(["current", "proposed"] as const).map((mode) => {
          const isCurrent = mode === "current";
          const label = isCurrent ? "Current" : "Proposed";
          return (
            <figure
              key={mode}
              className={`hc-scene hc-${mode}`}
              hidden={view !== "compare" && view !== mode}
            >
              <figcaption className="hc-scene-heading">
                <h3>{label}</h3>
                <span>
                  {isCurrent
                    ? "Recorded features"
                    : loading
                      ? "Pending assessment"
                      : proposalIds.length
                        ? `${proposalIds.length} proposed ${proposalIds.length === 1 ? "change" : "changes"}`
                        : "Unchanged"}
                </span>
              </figcaption>
              <div
                className="hc-viewport"
                role="group"
                tabIndex={0}
                aria-label={`${label} home camera`}
                aria-describedby={`${id}-instructions`}
                onKeyDown={onKeyDown}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
                onLostPointerCapture={() => {
                  drag.current = null;
                }}
                onPointerLeave={(e) => {
                  if (drag.current?.intent !== "horizontal") endDrag(e);
                }}
              >
                <SceneSvg
                  scene={isCurrent ? current : proposed}
                  camera={camera}
                  features={isCurrent ? state.current : state.proposed}
                  focus={focus}
                  label={`${label} home — ${home.property_type ?? "property type unknown"}, illustrative model`}
                />
              </div>
            </figure>
          );
        })}
      </div>
      <div
        className="hc-camera-controls"
        role="group"
        aria-label="Linked camera controls"
      >
        <button
          type="button"
          aria-label="Rotate left"
          onClick={() => rotate(-Math.PI / 10)}
        >
          <ArrowLeft size={17} aria-hidden="true" />
          <span>Rotate left</span>
        </button>
        <button
          type="button"
          aria-label="Rotate right"
          onClick={() => rotate(Math.PI / 10)}
        >
          <ArrowRight size={17} aria-hidden="true" />
          <span>Rotate right</span>
        </button>
        <span className="hc-controls-divider" aria-hidden="true" />
        <button
          type="button"
          aria-label="Zoom out"
          disabled={camera.zoom <= MIN_ZOOM}
          onClick={() => zoom(-0.1)}
        >
          <Minus size={18} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Zoom in"
          disabled={camera.zoom >= MAX_ZOOM}
          onClick={() => zoom(0.1)}
        >
          <Plus size={18} aria-hidden="true" />
        </button>
        <button type="button" aria-label="Reset view" onClick={reset}>
          <RotateCcw size={16} aria-hidden="true" />
          <span>Reset</span>
        </button>
      </div>
      <p className="hc-instructions" id={`${id}-instructions`}>
        Views rotate together. Drag sideways, or use ← / →, + / − and Home to
        reset.
      </p>
      <div
        className="hc-legend"
        role="group"
        aria-label="Feature status legend"
      >
        <span>
          <i className="hc-key-installed" aria-hidden="true" />
          Recorded / installed
        </span>
        <span>
          <i className="hc-key-proposed" aria-hidden="true" />
          Proposed · not installed
        </span>
        <span>
          <i className="hc-key-unknown" aria-hidden="true" />
          Unknown stays unknown
        </span>
      </div>
      <section
        className="hc-features"
        aria-label="Recorded features and proposed changes"
      >
        <div className="hc-features-heading">
          <h3>Look closer</h3>
          <p>Choose a feature to highlight it.</p>
        </div>
        <div className="hc-feature-columns" aria-hidden="true">
          <span>Feature</span>
          <span>Current</span>
          <span>Proposed</span>
        </div>
        {RETROFIT_IDS.map((feature) => {
          const change = state.changes.find((c) => c.id === feature);
          const before = state.current[feature];
          const after = state.proposed[feature];
          return (
            <div
              className={`hc-feature-row${focus === feature ? " hc-feature-focused" : ""}`}
              key={feature}
            >
              <button
                type="button"
                aria-label={`Focus ${FEATURE_NAMES[feature].toLowerCase()}`}
                aria-pressed={focus === feature}
                onClick={() => focusFeature(feature)}
              >
                {FEATURE_NAMES[feature]}
              </button>
              <span className={`hc-feature-status hc-status-${before.status}`}>
                <span className="hc-mobile-label">Current: </span>
                {before.label}
              </span>
              <span className={`hc-feature-status hc-status-${after.status}`}>
                <span className="hc-mobile-label">Proposed: </span>
                {change?.status === "pending"
                  ? "Pending · not shown"
                  : change?.status === "unavailable"
                    ? "Unavailable · unchanged"
                    : after.status === "proposed"
                      ? after.label
                      : "Unchanged"}
              </span>
              {change &&
                change.status !== "proposed" &&
                change.status !== "installed" && (
                  <p className="hc-change-reason">{change.message}</p>
                )}
            </div>
          );
        })}
        <div
          className="hc-feature-detail"
          role="status"
          aria-label="Feature detail"
          aria-live="polite"
        >
          {focus ? (
            <>
              <strong>{FEATURE_NAMES[focus]}</strong>
              <p>{FEATURE_NOTES[focus]}</p>
            </>
          ) : (
            <p>
              Explore the roof, windows and equipment. Highlighting a feature
              does not select an improvement.
            </p>
          )}
        </div>
      </section>
      <p className="hc-change-summary" role="status">
        {loading && selected.length
          ? "Checking selected improvements. Current features remain visible; proposals are not yet confirmed."
          : proposalIds.length
            ? "Only selected, currently feasible improvements are shown as proposed."
            : "No proposed changes are shown. Both views keep the same recorded features."}
      </p>
      <footer className="hc-disclosure">
        <p>{context}</p>
        <p>
          Illustration, not a survey. Dimensions, room layouts and equipment
          positions are not known. No energy, cost or performance result is
          calculated by this scene.
        </p>
      </footer>
    </section>
  );
}

/** Static gallery path: no hooks, interaction listeners, timers or camera state. */
export function HomeThumbnail({ home }: { home: Home }) {
  const features = comparisonState(home, [], [], false).current;
  return (
    <SceneSvg
      scene={buildScene(home, features, true)}
      camera={DEFAULT_CAMERA}
      features={features}
      thumbnail
      label={`${home.property_type ?? "Property type unknown"} — illustrative home thumbnail, not a surveyed property`}
    />
  );
}
