import {
  RETROFIT_IDS,
  type Home,
  type Recommendation,
  type RetrofitId,
} from "../types";

export type FeatureStatus = "unknown" | "current" | "installed" | "proposed";
export type Feature = { status: FeatureStatus; label: string; panes?: number };
export type Features = Record<RetrofitId, Feature>;
export type Change = {
  id: RetrofitId;
  status: "proposed" | "installed" | "pending" | "unavailable";
  message: string;
};

export const FEATURE_NAMES: Record<RetrofitId, string> = {
  loft_insulation: "Roof insulation",
  double_glazing: "Window panes",
  heat_pump: "Heat pump fan",
  solar_pv: "Solar panels",
  smart_controls: "Smart controls",
};
export const FEATURE_NOTES: Record<RetrofitId, string> = {
  loft_insulation:
    "The roof-edge band represents insulation, not a measured thickness or surveyed loft.",
  double_glazing:
    "Inset pane outlines distinguish glazing. Window sizes and positions are illustrative.",
  heat_pump:
    "An illustrative outdoor unit. Fan motion is a short demonstration, not a running-system simulation.",
  solar_pv:
    "Panels illustrate recorded or proposed solar, not a design, output or confirmation of roof ownership.",
  smart_controls:
    "A controls annotation, not an internal location or a claim about the home’s wiring.",
};

function recorded(home: Home): Features {
  const unknown = (): Feature => ({ status: "unknown", label: "Unknown" });
  return {
    loft_insulation:
      home.insulation === null || home.insulation === "unknown"
        ? unknown()
        : {
            status: home.insulation === "good" ? "installed" : "current",
            label: `${home.insulation[0].toUpperCase()}${home.insulation.slice(1)} insulation`,
          },
    double_glazing:
      home.glazing === null || home.glazing === "unknown"
        ? unknown()
        : {
            status: home.glazing === "single" ? "current" : "installed",
            label: `${home.glazing[0].toUpperCase()}${home.glazing.slice(1)} glazing`,
            panes:
              home.glazing === "triple" ? 3 : home.glazing === "double" ? 2 : 1,
          },
    heat_pump:
      home.heating === null || home.heating === "unknown"
        ? unknown()
        : {
            status: home.heating === "heat_pump" ? "installed" : "current",
            label:
              home.heating === "heat_pump"
                ? "Heat pump installed"
                : home.heating === "gas_boiler"
                  ? "Gas boiler"
                  : "Electric resistance heating",
          },
    solar_pv:
      home.solar_kwp === null || !Number.isFinite(home.solar_kwp)
        ? unknown()
        : {
            status: home.solar_kwp > 0 ? "installed" : "current",
            label: home.solar_kwp > 0 ? "Solar installed" : "No solar recorded",
          },
    smart_controls:
      home.smart_controls === null
        ? unknown()
        : {
            status: home.smart_controls ? "installed" : "current",
            label: home.smart_controls
              ? "Smart controls installed"
              : "No smart controls recorded",
          },
  };
}

/** Visual truth only. Feasibility and all numerical results belong to the engine. */
export function comparisonState(
  home: Home,
  selected: readonly RetrofitId[],
  recommendations: readonly Recommendation[],
  loading: boolean,
) {
  const current = recorded(home);
  const proposed = { ...current };
  const changes: Change[] = [];
  for (const id of RETROFIT_IDS) {
    if (!selected.includes(id)) continue;
    if (current[id].status === "installed") {
      changes.push({
        id,
        status: "installed",
        message: "Already recorded as installed; unchanged.",
      });
      continue;
    }
    const recommendation = recommendations.find((r) => r.id === id);
    if (loading || !recommendation) {
      changes.push({
        id,
        status: "pending",
        message: loading
          ? "Assessment pending; not yet a confirmed proposal."
          : "Awaiting current recommendation; not shown as proposed.",
      });
      continue;
    }
    const roofFeature = id === "solar_pv" || id === "loft_insulation";
    const unconfirmedRoof =
      roofFeature &&
      (home.property_type === null ||
        (home.property_type === "Flat" && home.roof_access !== true));
    if (
      !recommendation.feasible ||
      unconfirmedRoof ||
      home.excluded_retrofits?.includes(id)
    ) {
      changes.push({
        id,
        status: "unavailable",
        message: unconfirmedRoof
          ? "Roof access or property type is not confirmed; no roof proposal shown."
          : home.excluded_retrofits?.includes(id)
            ? "Deferred for this home; no proposal shown."
            : recommendation.reason ||
              "Not currently feasible; no proposal shown.",
      });
      continue;
    }
    proposed[id] = {
      status: "proposed",
      label: "Proposed · not installed",
      ...(id === "double_glazing" ? { panes: 2 } : {}),
    };
    changes.push({
      id,
      status: "proposed",
      message: "Selected and currently feasible; not installed.",
    });
  }
  return { current, proposed, changes };
}
