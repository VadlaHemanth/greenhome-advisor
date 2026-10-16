import { describe, expect, it } from "vitest";
import { home } from "./fixtures";
import { RETROFIT_IDS, type Home, type Recommendation } from "../types";
import {
  DEFAULT_CAMERA,
  adjustCamera,
  projectPoint,
  projectFaces,
  type Face,
} from "../home3d/math";
import { buildScene } from "../home3d/geometry";
import { comparisonState } from "../home3d/state";

const recommendations: Recommendation[] = RETROFIT_IDS.map((id) => ({
  id,
  name: id,
  feasible: true,
  suitability: "Medium",
  reason: "Test only",
  cost_gbp: [0, 0],
  standalone: null,
}));
const baseline = (h: Home = home) => comparisonState(h, [], [], false).current;
const surfaces = (faces: readonly Face[]): Face[] =>
  faces.flatMap((face) => [face, ...surfaces(face.details ?? [])]);

describe("original home geometry and camera", () => {
  it("projects real depth: yaw changes x/depth and a full turn returns the same point", () => {
    const point = { x: 2, y: 1, z: 3 };
    const initial = projectPoint(point, DEFAULT_CAMERA);
    const rotated = projectPoint(
      point,
      adjustCamera(DEFAULT_CAMERA, { yaw: Math.PI / 2 }),
    );
    expect(rotated.x).not.toBeCloseTo(initial.x);
    expect(rotated.depth).not.toBeCloseTo(initial.depth);
    const full = projectPoint(
      point,
      adjustCamera(DEFAULT_CAMERA, { yaw: 2 * Math.PI }),
    );
    expect(full.x).toBeCloseTo(initial.x);
    expect(full.y).toBeCloseTo(initial.y);
  });
  it("bounds zoom, normalises yaw and recovers safely from non-finite camera input", () => {
    expect(adjustCamera(DEFAULT_CAMERA, { zoom: 100 }).zoom).toBe(1.35);
    expect(adjustCamera(DEFAULT_CAMERA, { zoom: -100 }).zoom).toBe(0.8);
    const bad = adjustCamera(DEFAULT_CAMERA, { yaw: NaN, zoom: Infinity });
    expect(Number.isFinite(bad.yaw) && Number.isFinite(bad.zoom)).toBe(true);
    expect(adjustCamera(DEFAULT_CAMERA, { yaw: 200 }).yaw).toBeLessThan(
      2 * Math.PI,
    );
  });
  it("projects visible faces with finite depths without mutating model geometry", () => {
    const scene = buildScene(home, baseline());
    const snapshot = JSON.stringify(scene);
    const projected = projectFaces(scene.faces, DEFAULT_CAMERA);
    expect(projected.length).toBeGreaterThan(20);
    expect(projected.every((face) => Number.isFinite(face.depth))).toBe(true);
    expect(JSON.stringify(scene)).toBe(snapshot);
    expect(projected.every((f) => !/NaN|Infinity/.test(f.points))).toBe(true);
  });
  it("keeps an offset foreground unit in front of its wall despite misleading centroid depth", () => {
    const wall: Face = {
      id: "wall",
      fill: "#fff",
      vertices: [
        { x: -2, y: 0, z: 1 },
        { x: 2, y: 0, z: 1 },
        { x: 2, y: 2, z: 1 },
        { x: -2, y: 2, z: 1 },
      ],
    };
    const unit: Face = {
      id: "unit",
      fill: "#000",
      vertices: [
        { x: -1.8, y: 0.1, z: 1.2 },
        { x: -1.1, y: 0.1, z: 1.2 },
        { x: -1.1, y: 0.7, z: 1.2 },
        { x: -1.8, y: 0.7, z: 1.2 },
      ],
    };
    expect(projectFaces([unit, wall], DEFAULT_CAMERA).map((f) => f.id)).toEqual(
      ["wall", "unit"],
    );
    expect(projectFaces([wall, unit], DEFAULT_CAMERA).map((f) => f.id)).toEqual(
      ["wall", "unit"],
    );
    expect(
      projectFaces(
        [
          {
            ...wall,
            vertices: [...wall.vertices].reverse(),
            doubleSided: true,
          },
          unit,
        ],
        DEFAULT_CAMERA,
      ).map((f) => f.id),
    ).toEqual(["wall", "unit"]);
    expect(
      projectFaces(
        [
          {
            ...wall,
            vertices: [...wall.vertices].reverse(),
            doubleSided: true,
          },
          {
            ...unit,
            vertices: unit.vertices.map((v) => ({ ...v, x: -v.x })).reverse(),
          },
        ],
        DEFAULT_CAMERA,
      ).map((f) => f.id),
    ).toEqual(["wall", "unit"]);
  });
  it("seats the detached chimney on its sloping roof rather than floating at ridge height", () => {
    const scene = buildScene(
      { ...home, property_type: "Detached" },
      baseline(),
    );
    const chimney = scene.faces.find((f) => f.id === "home-chimney-front")!;
    const roofY = (x: number) => 2.83 + 1.05 * (1 - Math.abs(x) / 1.725);
    for (const point of chimney.vertices.slice(0, 2))
      expect(point.y).toBeCloseTo(roofY(point.x), 5);
  });
  const types: NonNullable<Home["property_type"]>[] = [
    "Detached",
    "Semi detached",
    "Mid terrace",
    "End terrace",
    "Bungalow",
    "Flat",
  ];
  it("has six structurally distinct families, not six labels on the same cube", () => {
    const scenes = types.map((type) =>
      buildScene({ ...home, property_type: type }, baseline()),
    );
    expect(
      new Set(scenes.map((s) => JSON.stringify(s.faces.map((f) => f.vertices))))
        .size,
    ).toBe(6);
    expect(scenes.map((s) => s.contextHomes)).toEqual([0, 1, 2, 2, 0, 0]);
    expect(scenes[5].roofKind).toBe("shared-flat");
    expect(scenes[4].roofKind).toBe("hipped");
    expect(
      scenes.every((s) => s.faces.some((f) => f.id.includes("window"))),
    ).toBe(true);
  });
  it.each(types)(
    "keeps %s geometry finite through a complete orbit",
    (type) => {
      const scene = buildScene({ ...home, property_type: type }, baseline());
      for (let yaw = 0; yaw < Math.PI * 2; yaw += Math.PI / 8) {
        const projected = projectFaces(scene.faces, { ...DEFAULT_CAMERA, yaw });
        expect(surfaces(projected).length).toBeGreaterThan(20);
        expect(projected.every((f) => !/NaN|Infinity/.test(f.points))).toBe(
          true,
        );
      }
    },
  );
  it("does not infer a house or measurements from an unknown type or recorded floor area", () => {
    const unknown = buildScene({ ...home, property_type: null }, baseline());
    expect(unknown.family).toBe("unknown");
    expect(unknown.faces.some((f) => /roof|wall|window/.test(f.id))).toBe(
      false,
    );
    expect(
      buildScene({ ...home, floor_area_m2: 900 }, baseline()).faces,
    ).toEqual(buildScene({ ...home, floor_area_m2: null }, baseline()).faces);
  });
});

describe("recorded and proposed feature truth", () => {
  it("clearing selections is an exact geometric no-op", () => {
    const state = comparisonState(home, [], recommendations, false);
    expect(state.proposed).toEqual(state.current);
    expect(buildScene(home, state.proposed)).toEqual(
      buildScene(home, state.current),
    );
  });
  it("only renders selected currently feasible proposals, and identifies rejected/pending choices", () => {
    const state = comparisonState(
      home,
      ["heat_pump", "solar_pv", "smart_controls"],
      [
        recommendations.find((r) => r.id === "heat_pump")!,
        {
          ...recommendations.find((r) => r.id === "solar_pv")!,
          feasible: false,
        },
      ],
      false,
    );
    expect(state.proposed.heat_pump.status).toBe("proposed");
    expect(state.proposed.solar_pv.status).toBe("current");
    expect(state.proposed.smart_controls.status).toBe("current");
    expect(state.changes.find((c) => c.id === "solar_pv")?.status).toBe(
      "unavailable",
    );
    expect(state.changes.find((c) => c.id === "smart_controls")?.status).toBe(
      "pending",
    );
  });
  it("never turns loading into a confirmed proposal", () => {
    const state = comparisonState(
      home,
      [...RETROFIT_IDS],
      recommendations,
      true,
    );
    expect(state.proposed).toEqual(state.current);
    expect(state.changes.every((c) => c.status === "pending")).toBe(true);
  });
  it("keeps locally deferred upgrades unchanged even for contradictory recommendation input", () => {
    const state = comparisonState(
      { ...home, excluded_retrofits: ["solar_pv"] },
      ["solar_pv"],
      recommendations,
      false,
    );
    expect(state.current).toEqual(state.proposed);
    expect(state.changes[0].status).toBe("unavailable");
  });
  it("preserves all installed equipment in both views, including when selected or loading", () => {
    const improved: Home = {
      ...home,
      insulation: "good",
      glazing: "triple",
      heating: "heat_pump",
      solar_kwp: 3,
      smart_controls: true,
    };
    const state = comparisonState(
      improved,
      [...RETROFIT_IDS],
      recommendations,
      true,
    );
    expect(
      Object.values(state.current).every((s) => s.status === "installed"),
    ).toBe(true);
    expect(state.proposed).toEqual(state.current);
    expect(state.changes.every((c) => c.status === "installed")).toBe(true);
  });
  it("preserves null and explicit unknown features rather than assuming absence", () => {
    const missing: Home = {
      ...home,
      heating: null,
      insulation: "unknown",
      glazing: null,
      solar_kwp: null,
      smart_controls: null,
    };
    const state = comparisonState(missing, [], [], false);
    expect(
      Object.values(state.current).every((s) => s.status === "unknown"),
    ).toBe(true);
    expect(state.proposed).toEqual(state.current);
    const scene = buildScene(missing, state.current);
    expect(
      scene.faces.some(
        (f) => f.feature === "heat_pump" || f.feature === "solar_pv",
      ),
    ).toBe(false);
  });
  it("does not invent roof rights for flats or type-unknown homes", () => {
    for (const property_type of ["Flat", null] as const) {
      const h = { ...home, property_type, roof_access: null };
      const state = comparisonState(
        h,
        ["solar_pv", "loft_insulation"],
        recommendations,
        false,
      );
      expect(state.proposed).toEqual(state.current);
      expect(state.changes.every((c) => c.status === "unavailable")).toBe(true);
    }
  });
  it("adds pane geometry, insulation, panels and a heat-pump fan only to the proposed scene", () => {
    const state = comparisonState(
      home,
      [...RETROFIT_IDS],
      recommendations,
      false,
    );
    const current = buildScene(home, state.current);
    const proposed = buildScene(home, state.proposed);
    for (const id of [
      "loft_insulation",
      "double_glazing",
      "heat_pump",
      "solar_pv",
    ] as const) {
      expect(
        surfaces(proposed.faces).some(
          (f) => f.feature === id && f.status === "proposed",
        ),
      ).toBe(true);
    }
    expect(proposed.faces.length).toBeGreaterThan(current.faces.length);
    expect(surfaces(proposed.faces).some((f) => f.id.includes("fan"))).toBe(
      true,
    );
  });
});
