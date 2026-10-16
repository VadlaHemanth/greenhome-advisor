import type { Home, RetrofitId } from "../types";
import type { Face, Vec3 } from "./math";
import type { Features, FeatureStatus } from "./state";

export type Scene = {
  family: string;
  roofKind: "gable" | "hipped" | "shared-flat" | "unknown";
  contextHomes: number;
  faces: Face[];
};
const p = (x: number, y: number, z: number): Vec3 => ({ x, y, z });
const palette = {
  wall: "#f2eee3",
  side: "#ddd9cc",
  roof: "#647c70",
  roofDark: "#456357",
  trim: "#faf8ef",
  stone: "#b4b9a8",
  door: "#355c4d",
  glass: "#b6d0cd",
  unknownGlass: "#d9ded7",
  context: "#e0e4dc",
  contextRoof: "#b3c0b3",
  proposal: "#ad741f",
  installed: "#527b61",
  dark: "#284b40",
};
const active = (status: FeatureStatus) =>
  status === "installed" || status === "proposed";
type MapPlane = (u: number, v: number) => Vec3;

function rect(
  id: string,
  map: MapPlane,
  u: number,
  v: number,
  w: number,
  h: number,
  fill: string,
  extra: Partial<Face> = {},
): Face {
  return {
    id,
    vertices: [map(u, v), map(u + w, v), map(u + w, v + h), map(u, v + h)],
    fill,
    ...extra,
  };
}
function box(
  id: string,
  x: number,
  y: number,
  z: number,
  w: number,
  h: number,
  d: number,
  fill: string,
  extra: Partial<Face> = {},
): Face[] {
  return [
    {
      id: `${id}-front`,
      vertices: [
        p(x, y, z + d),
        p(x + w, y, z + d),
        p(x + w, y + h, z + d),
        p(x, y + h, z + d),
      ],
      fill,
      ...extra,
    },
    {
      id: `${id}-right`,
      vertices: [
        p(x + w, y, z + d),
        p(x + w, y, z),
        p(x + w, y + h, z),
        p(x + w, y + h, z + d),
      ],
      fill,
      ...extra,
    },
    {
      id: `${id}-back`,
      vertices: [
        p(x + w, y, z),
        p(x, y, z),
        p(x, y + h, z),
        p(x + w, y + h, z),
      ],
      fill,
      ...extra,
    },
    {
      id: `${id}-left`,
      vertices: [
        p(x, y, z),
        p(x, y, z + d),
        p(x, y + h, z + d),
        p(x, y + h, z),
      ],
      fill,
      ...extra,
    },
    {
      id: `${id}-top`,
      vertices: [
        p(x, y + h, z + d),
        p(x + w, y + h, z + d),
        p(x + w, y + h, z),
        p(x, y + h, z),
      ],
      fill,
      ...extra,
    },
  ];
}

/** Dimensionless, authored archetypes. Never uses floor area, address or energy figures. */
export function buildScene(
  home: Home,
  features: Features,
  thumbnail = false,
): Scene {
  const family = home.property_type ?? "unknown";
  const scene: Scene = {
    family,
    roofKind: "gable",
    contextHomes: 0,
    faces: [],
  };
  const faces = scene.faces;
  if (family === "unknown") {
    scene.roofKind = "unknown";
    faces.push(
      ...box("unconfirmed-plinth", -1.55, 0, -1.1, 3.1, 0.1, 2.2, "#e1e6dc"),
    );
    return scene;
  }
  const flat = family === "Flat";
  const bungalow = family === "Bungalow";
  const semi = family === "Semi detached";
  const terrace = family === "Mid terrace" || family === "End terrace";
  const width = flat
    ? 3.3
    : bungalow
      ? 4.1
      : semi
        ? 2.35
        : terrace
          ? 1.95
          : 3.25;
  const height = flat ? 4.05 : bungalow ? 1.55 : 2.8;
  const depth = flat ? 2.65 : bungalow ? 2.7 : 2.6;
  const ridge = bungalow ? 0.95 : 1.05;
  const centers = semi
    ? [-width / 2, width / 2]
    : terrace
      ? [-width, 0, width]
      : [0];
  const target = family === "Mid terrace" ? 1 : 0;
  scene.contextHomes = centers.length - 1;
  scene.roofKind = flat ? "shared-flat" : bungalow ? "hipped" : "gable";
  const extent = (width * centers.length) / 2;
  faces.push(
    ...box(
      "garden-plinth",
      -extent - 0.3,
      -0.16,
      -depth / 2 - 0.32,
      extent * 2 + 0.6,
      0.14,
      depth + 1.25,
      "#dce4d4",
    ),
  );
  const pathMap: MapPlane = (u, v) => p(u, -0.015, v);
  faces.push(
    rect(
      "entry-path",
      pathMap,
      centers[target] - 0.23,
      depth / 2,
      0.48,
      0.88,
      "#cecbbd",
      { doubleSided: true },
    ),
  );

  function windowDetails(
    id: string,
    map: MapPlane,
    u: number,
    v: number,
    w: number,
    h: number,
    context: boolean,
  ): Face[] {
    const feature = context ? undefined : ("double_glazing" as const);
    const status = context ? undefined : features.double_glazing.status;
    const panes = context ? 1 : (features.double_glazing.panes ?? 0);
    const details = [
      rect(
        `${id}-frame`,
        map,
        u - 0.055,
        v - 0.055,
        w + 0.11,
        h + 0.11,
        context ? "#cad2c7" : palette.trim,
      ),
      rect(
        `${id}-glass`,
        map,
        u,
        v,
        w,
        h,
        context
          ? "#bdccc2"
          : status === "unknown"
            ? palette.unknownGlass
            : palette.glass,
        { feature, status },
      ),
    ];
    if (!thumbnail) {
      details.push({
        id: `${id}-reflection`,
        vertices: [
          map(u + 0.06, v + h - 0.05),
          map(u + w * 0.45, v + h - 0.05),
          map(u + 0.06, v + h * 0.35),
        ],
        fill: context ? "#d2dcd2" : "#e6efdf",
      });
    }
    details.push(
      rect(
        `${id}-mullion`,
        map,
        u + w * 0.48,
        v,
        0.035,
        h,
        context ? "#dce2d7" : palette.trim,
      ),
      rect(
        `${id}-transom`,
        map,
        u,
        v + h * 0.5,
        w,
        0.035,
        context ? "#dce2d7" : palette.trim,
      ),
      rect(
        `${id}-sill`,
        map,
        u - 0.09,
        v - 0.09,
        w + 0.18,
        0.06,
        palette.stone,
      ),
    );
    for (let pane = 1; pane < panes; pane++) {
      details.push(
        rect(
          `${id}-pane-${pane + 1}`,
          map,
          u + 0.05 * pane,
          v + 0.05 * pane,
          w - 0.1 * pane,
          h - 0.1 * pane,
          "none",
          {
            feature,
            status,
            stroke: status === "proposed" ? palette.proposal : "#527e72",
          },
        ),
      );
    }
    return details;
  }

  function facade(
    id: string,
    map: MapPlane,
    span: number,
    context: boolean,
    entrance: boolean,
    side: boolean,
  ) {
    const floors = flat ? 3 : bungalow ? 1 : 2;
    // Store facade in storey-sized surfaces. Coplanar windows, trim and masonry
    // render atomically with each surface, not as depth-competing floating decals.
    for (let floor = 0; floor < floors; floor++) {
      const floorHeight = height / floors;
      const base = floor * floorHeight;
      const details: Face[] = [];
      const body = rect(
        `${id}-wall-windows-${floor}`,
        map,
        -span / 2,
        base,
        span,
        floorHeight,
        context || (flat && floor !== 1)
          ? palette.context
          : side
            ? palette.side
            : palette.wall,
        { details },
      );
      faces.push(body);
      details.push(
        rect(
          `${id}-course-${floor}`,
          map,
          -span / 2,
          base + 0.045,
          span,
          0.07,
          context ? "#c8d0c3" : "#c4c6b7",
        ),
      );
      if (!thumbnail) {
        for (let row = 0.28; row < floorHeight; row += 0.25) {
          details.push(
            rect(
              `${id}-masonry-${floor}-${row}`,
              map,
              -span / 2,
              base + row,
              span,
              0.009,
              context ? "#d6dccf" : "#deded0",
            ),
          );
        }
      }
      const windowWidth = side ? 0.52 : span > 3 ? 0.66 : 0.57;
      const windowHeight = flat ? 0.71 : bungalow ? 0.76 : 0.7;
      const windowBase = base + (bungalow ? 0.46 : 0.47);
      const offset = span > 3 ? 0.97 : span * 0.28;
      const windowPositions = side
        ? [0]
        : entrance && floor === 0
          ? [-offset]
          : [-offset, offset];
      for (const [index, u] of windowPositions.entries()) {
        details.push(
          ...windowDetails(
            `${id}-window-${floor}-${index}`,
            map,
            u - windowWidth / 2,
            windowBase,
            windowWidth,
            windowHeight,
            context || (flat && floor !== 1),
          ),
        );
      }
      if (entrance && floor === 0) {
        const doorX = span > 3 ? 0.36 : 0.2;
        details.push(
          rect(
            `${id}-door-trim`,
            map,
            doorX - 0.065,
            0.02,
            0.64,
            1.11,
            palette.trim,
          ),
          rect(
            `${id}-door`,
            map,
            doorX,
            0.03,
            0.51,
            1.04,
            context ? "#91a797" : palette.door,
          ),
          rect(
            `${id}-door-glass`,
            map,
            doorX + 0.08,
            0.68,
            0.35,
            0.28,
            "#c2d5c7",
          ),
          rect(
            `${id}-door-panel`,
            map,
            doorX + 0.08,
            0.18,
            0.35,
            0.34,
            context ? "#a4b4a3" : "#527362",
          ),
          rect(
            `${id}-door-handle`,
            map,
            doorX + 0.4,
            0.49,
            0.035,
            0.085,
            "#dec48f",
          ),
        );
      }
      // Flat highlight denotes the selected archetype, never an inferred unit number.
      if (flat && floor === 1 && !context) {
        details.push(
          rect(
            `${id}-flat-band`,
            map,
            -span / 2,
            base + 0.12,
            span,
            0.065,
            palette.installed,
          ),
        );
      }
      if (floor === floors - 1) {
        details.push(
          rect(
            `${id}-eaves`,
            map,
            -span / 2,
            height - 0.09,
            span,
            0.09,
            palette.trim,
          ),
        );
        if (!context && active(features.loft_insulation.status)) {
          const status = features.loft_insulation.status;
          const insulation = rect(
            `${id}-insulation`,
            map,
            -span / 2,
            height - 0.22,
            span,
            0.105,
            status === "proposed" ? "#d6b16f" : "#92ab7e",
            { feature: "loft_insulation", status },
          );
          details.push(insulation);
        }
      }
    }
  }

  function roof(id: string, cx: number, context: boolean) {
    const x0 = cx - width / 2 - 0.1,
      x1 = cx + width / 2 + 0.1;
    const z0 = -depth / 2 - 0.14,
      z1 = depth / 2 + 0.14;
    const y = height + 0.03,
      top = y + ridge;
    if (flat) {
      faces.push(
        ...box(`${id}-parapet`, x0, y, z0, x1 - x0, 0.13, z1 - z0, "#c3caba"),
      );
      faces.push({
        id: `${id}-shared-roof`,
        vertices: [
          p(x0 + 0.1, y + 0.135, z1 - 0.1),
          p(x1 - 0.1, y + 0.135, z1 - 0.1),
          p(x1 - 0.1, y + 0.135, z0 + 0.1),
          p(x0 + 0.1, y + 0.135, z0 + 0.1),
        ],
        fill: "#8e9f92",
      });
      return;
    }
    const alongX = semi || terrace || bungalow;
    const colour = context ? palette.contextRoof : palette.roof;
    let slopes: Face[];
    if (alongX) {
      const inset = bungalow ? 0.75 : 0;
      slopes = [
        {
          id: `${id}-roof-front`,
          vertices: [
            p(x0, y, z1),
            p(x1, y, z1),
            p(x1 - inset, top, 0),
            p(x0 + inset, top, 0),
          ],
          fill: colour,
        },
        {
          id: `${id}-roof-back`,
          vertices: [
            p(x1, y, z0),
            p(x0, y, z0),
            p(x0 + inset, top, 0),
            p(x1 - inset, top, 0),
          ],
          fill: context ? colour : palette.roofDark,
        },
        {
          id: `${id}-roof-left`,
          vertices: [p(x0, y, z0), p(x0, y, z1), p(x0 + inset, top, 0)],
          fill: bungalow ? palette.roofDark : palette.side,
        },
        {
          id: `${id}-roof-right`,
          vertices: [p(x1, y, z1), p(x1, y, z0), p(x1 - inset, top, 0)],
          fill: bungalow ? colour : palette.wall,
        },
      ];
    } else {
      slopes = [
        {
          id: `${id}-roof-left`,
          vertices: [
            p(x0, y, z0),
            p(x0, y, z1),
            p(cx, top, z1),
            p(cx, top, z0),
          ],
          fill: palette.roofDark,
        },
        {
          id: `${id}-roof-right`,
          vertices: [
            p(x1, y, z1),
            p(x1, y, z0),
            p(cx, top, z0),
            p(cx, top, z1),
          ],
          fill: colour,
        },
        {
          id: `${id}-gable-front`,
          vertices: [
            p(x0 + 0.08, y, z1 - 0.03),
            p(x1 - 0.08, y, z1 - 0.03),
            p(cx, top - 0.03, z1 - 0.03),
          ],
          fill: palette.wall,
        },
        {
          id: `${id}-gable-back`,
          vertices: [
            p(x1 - 0.08, y, z0 + 0.03),
            p(x0 + 0.08, y, z0 + 0.03),
            p(cx, top - 0.03, z0 + 0.03),
          ],
          fill: palette.side,
        },
      ];
    }
    for (const slope of slopes.slice(0, 2)) {
      const [a, b, , d] = slope.vertices;
      const onSlope: MapPlane = (u, v) =>
        p(
          a.x + (b.x - a.x) * u + (d.x - a.x) * v,
          a.y + (b.y - a.y) * u + (d.y - a.y) * v,
          a.z + (b.z - a.z) * u + (d.z - a.z) * v,
        );
      slope.details = [];
      // A hipped front is trapezoidal: keep details inside its central rectangle.
      if (!thumbnail && !bungalow) {
        for (let v = 0.16; v < 0.98; v += 0.16) {
          slope.details.push(
            rect(
              `${slope.id}-tile-${v}`,
              onSlope,
              0,
              v,
              1,
              0.008,
              context ? "#a3b4a5" : "#84998b",
            ),
          );
        }
      }
      if (
        !context &&
        active(features.solar_pv.status) &&
        slope === slopes[alongX ? 0 : 1]
      ) {
        const status = features.solar_pv.status;
        const columns = bungalow ? 2 : 3;
        for (let col = 0; col < columns; col++) {
          for (let row = 0; row < 2; row++) {
            const u = 0.19 + col * 0.205,
              v = 0.22 + row * 0.29;
            slope.details.push(
              rect(
                `${id}-solar-${col}-${row}`,
                onSlope,
                u,
                v,
                0.19,
                0.25,
                "#294f59",
                {
                  feature: "solar_pv",
                  status,
                  stroke: status === "proposed" ? "#dfb56f" : "#b7d7cb",
                },
              ),
            );
            if (!thumbnail) {
              slope.details.push(
                rect(
                  `${id}-solar-grid-${col}-${row}`,
                  onSlope,
                  u + 0.09,
                  v,
                  0.005,
                  0.25,
                  "#89b3b0",
                ),
              );
            }
          }
        }
      }
    }
    faces.push(...slopes);
    // Small ridge chimney and cap; a recognisable archetype, not recorded equipment.
    if (!bungalow) {
      const shaft = box(
        `${id}-chimney`,
        cx - width * 0.27,
        y,
        -0.26,
        0.29,
        top + 0.36 - y,
        0.32,
        context ? "#b4bfb0" : "#a9aa97",
      );
      for (const face of shaft) {
        face.vertices = face.vertices.map((v) =>
          v.y === y
            ? {
                ...v,
                y: alongX
                  ? y + ridge * (1 - Math.abs(v.z) / Math.abs(z0))
                  : y + ridge * (1 - Math.abs(v.x - cx) / (width / 2 + 0.1)),
              }
            : v,
        );
      }
      faces.push(
        ...shaft,
        ...box(
          `${id}-chimney-cap`,
          cx - width * 0.27 - 0.04,
          top + 0.36,
          -0.3,
          0.37,
          0.07,
          0.4,
          "#687d6a",
        ),
      );
    }
  }

  for (const [index, cx] of centers.entries()) {
    const context = index !== target;
    const id = context ? `neighbour-${index}` : "home";
    facade(
      `${id}-front`,
      (u, v) => p(cx + u, v, depth / 2),
      width,
      context,
      true,
      false,
    );
    facade(
      `${id}-back`,
      (u, v) => p(cx - u, v, -depth / 2),
      width,
      context,
      false,
      false,
    );
    if (index === centers.length - 1)
      facade(
        `${id}-right`,
        (u, v) => p(cx + width / 2, v, -u),
        depth,
        context,
        false,
        true,
      );
    if (index === 0)
      facade(
        `${id}-left`,
        (u, v) => p(cx - width / 2, v, u),
        depth,
        context,
        false,
        true,
      );
    roof(id, cx, context);
    faces.push(
      ...box(
        `${id}-door-step`,
        cx + (width > 3 ? 0.29 : 0.13),
        0,
        depth / 2,
        0.68,
        0.1,
        0.24,
        "#b6b9a8",
      ),
    );
  }
  // Roof equipment on a flat never implies an automatically owned private roof.
  if (flat && active(features.solar_pv.status)) {
    const status = features.solar_pv.status;
    faces.push(
      ...box(
        "shared-roof-solar",
        -0.9,
        height + 0.2,
        -0.7,
        1.8,
        0.06,
        0.95,
        "#294f59",
        { feature: "solar_pv", status },
      ),
    );
  }
  if (active(features.heat_pump.status)) {
    const status = features.heat_pump.status;
    const cx = centers[target];
    const x = cx - width / 2 + 0.04,
      z = depth / 2 + 0.13;
    const pump = box("heat-pump", x, 0.1, z, 0.64, 0.53, 0.3, "#e8eee1", {
      feature: "heat_pump",
      status,
    });
    const map: MapPlane = (u, v) => p(x + u, v, z + 0.3);
    const fan = rect("heat-pump-fan", map, 0.08, 0.19, 0.33, 0.33, "#527363", {
      feature: "heat_pump",
      status,
    });
    // Fan rotor is projected as actual coplanar 3D polygons. Only its small
    // screen-space rotor wrapper animates; there is no scene RAF loop.
    fan.details = [
      rect("heat-pump-fan-hub", map, 0.217, 0.327, 0.056, 0.056, "#d2dfcd"),
    ];
    for (let i = 0; i < 4; i++) {
      const angle = (i * Math.PI) / 2;
      const point = (radius: number, theta: number) =>
        map(0.245 + radius * Math.cos(theta), 0.355 + radius * Math.sin(theta));
      fan.details.push({
        id: `heat-pump-fan-blade-${i}`,
        fill: "#c5d5c1",
        vertices: [
          point(0.03, angle),
          point(0.135, angle + 0.2),
          point(0.14, angle + 0.75),
          point(0.05, angle + 0.9),
        ],
      });
    }
    pump[0].details = [fan];
    for (let i = 0; i < 4; i++)
      pump[0].details.push(
        rect(
          `heat-pump-grille-${i}`,
          map,
          0.47,
          0.22 + i * 0.07,
          0.1,
          0.023,
          "#728876",
        ),
      );
    faces.push(...pump);
  }
  return scene;
}
