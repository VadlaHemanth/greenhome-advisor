import type { RetrofitId } from "../types";
import type { FeatureStatus } from "./state";

export type Vec3 = { x: number; y: number; z: number };
export type Camera = { yaw: number; zoom: number };
export const DEFAULT_CAMERA: Readonly<Camera> = Object.freeze({
  yaw: 0.62,
  zoom: 1,
});
export const MIN_ZOOM = 0.8;
export const MAX_ZOOM = 1.35;
const ELEVATION = 0.42;
const TAU = Math.PI * 2;
export type Face = {
  id: string;
  vertices: Vec3[];
  fill: string;
  feature?: RetrofitId;
  status?: FeatureStatus;
  /** Coplanar facade details travel with their supporting face to avoid z fighting. */
  details?: Face[];
  doubleSided?: boolean;
  stroke?: string;
};
export type ProjectedFace = Omit<Face, "details"> & {
  points: string;
  depth: number;
  details: ProjectedFace[];
};

export function adjustCamera(camera: Camera, delta: Partial<Camera>): Camera {
  const yaw = camera.yaw + (Number.isFinite(delta.yaw) ? delta.yaw! : 0);
  const zoom = camera.zoom + (Number.isFinite(delta.zoom) ? delta.zoom! : 0);
  return {
    yaw: ((yaw % TAU) + TAU) % TAU,
    zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom)),
  };
}
export function projectPoint(point: Vec3, camera: Camera) {
  const x = point.x * Math.cos(camera.yaw) - point.z * Math.sin(camera.yaw);
  const z = point.x * Math.sin(camera.yaw) + point.z * Math.cos(camera.yaw);
  const y = point.y - 1.65;
  const scale = 54 * camera.zoom;
  return {
    x: 280 + x * scale,
    y: 184 - (y * Math.cos(ELEVATION) - z * Math.sin(ELEVATION)) * scale,
    depth: y * Math.sin(ELEVATION) + z * Math.cos(ELEVATION),
  };
}
function normal(vertices: Vec3[]) {
  const [a, b, c] = vertices;
  const u = { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z };
  const v = { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z };
  return {
    x: u.y * v.z - u.z * v.y,
    y: u.z * v.x - u.x * v.z,
    z: u.x * v.y - u.y * v.x,
  };
}
function facing(n: Vec3, camera: Camera) {
  return (
    n.x * Math.sin(camera.yaw) * Math.cos(ELEVATION) +
    n.y * Math.sin(ELEVATION) +
    n.z * Math.cos(camera.yaw) * Math.cos(ELEVATION)
  );
}
function visible(face: Face, camera: Camera) {
  return face.doubleSided || facing(normal(face.vertices), camera) > 0.00001;
}
function projectFace(face: Face, camera: Camera): ProjectedFace {
  const projected = face.vertices.map((v) => projectPoint(v, camera));
  return {
    ...face,
    points: projected
      .map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`)
      .join(" "),
    depth: projected.reduce((sum, p) => sum + p.depth, 0) / projected.length,
    details: (face.details ?? []).map((detail) => projectFace(detail, camera)),
  };
}
type ScreenPoint = { x: number; y: number };
function overlaps(a: ScreenPoint[], b: ScreenPoint[]) {
  // Separating-axis test for convex polygons, not just bounding boxes: disjoint
  // roofs can share a bounding box without imposing a painter-order constraint.
  for (const polygon of [a, b]) {
    for (let i = 0; i < polygon.length; i++) {
      const start = polygon[i],
        end = polygon[(i + 1) % polygon.length];
      const axis = { x: start.y - end.y, y: end.x - start.x };
      const ap = a.map((v) => v.x * axis.x + v.y * axis.y);
      const bp = b.map((v) => v.x * axis.x + v.y * axis.y);
      if (
        Math.max(...ap) <= Math.min(...bp) + 0.00001 ||
        Math.max(...bp) <= Math.min(...ap) + 0.00001
      )
        return false;
    }
  }
  return true;
}
function sideOfPlane(vertices: Vec3[], plane: Face, n: Vec3) {
  const origin = plane.vertices[0];
  const distances = vertices.map(
    (v) =>
      (v.x - origin.x) * n.x + (v.y - origin.y) * n.y + (v.z - origin.z) * n.z,
  );
  const min = Math.min(...distances),
    max = Math.max(...distances);
  if (min >= -1e-8 && max > 1e-8) return 1;
  if (max <= 1e-8 && min < -1e-8) return -1;
  return 0;
}
/**
 * Cull backfaces, start with camera depth, then enforce overlapping surface
 * plane order. Centroid-only sorting incorrectly hides small foreground units
 * behind broad walls, or distant houses behind their own ground plane.
 * Authored exterior polygons are convex and do not interpenetrate; coplanar
 * details belong to their supporting surface. No general mesh/CSG claim.
 */
export function projectFaces(
  faces: readonly Face[],
  camera: Camera,
): ProjectedFace[] {
  const projected = faces
    .filter((face) => visible(face, camera))
    .map((face) => projectFace(face, camera))
    .sort((a, b) => a.depth - b.depth || a.id.localeCompare(b.id));
  const outlines = projected.map((f) =>
    f.vertices.map((v) => projectPoint(v, camera)),
  );
  const normals = projected.map((f) => {
    const n = normal(f.vertices);
    return facing(n, camera) < 0 ? { x: -n.x, y: -n.y, z: -n.z } : n;
  });
  const edges: number[][] = projected.map(() => []);
  const incoming = projected.map(() => 0);
  for (let i = 0; i < projected.length; i++) {
    for (let j = i + 1; j < projected.length; j++) {
      if (!overlaps(outlines[i], outlines[j])) continue;
      const side =
        sideOfPlane(projected[j].vertices, projected[i], normals[i]) ||
        -sideOfPlane(projected[i].vertices, projected[j], normals[j]);
      if (!side) continue;
      const [far, near] = side > 0 ? [i, j] : [j, i];
      edges[far].push(near);
      incoming[near]++;
    }
  }
  const ordered: ProjectedFace[] = [];
  const emitted = new Set<number>();
  while (ordered.length < projected.length) {
    let next = projected.findIndex(
      (_, i) => !emitted.has(i) && incoming[i] === 0,
    );
    // Stable, bounded fallback for tangencies/numerical cycles; never loop.
    if (next < 0) next = projected.findIndex((_, i) => !emitted.has(i));
    ordered.push(projected[next]);
    emitted.add(next);
    for (const near of edges[next]) incoming[near]--;
  }
  return ordered;
}
