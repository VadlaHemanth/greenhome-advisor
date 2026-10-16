import { projectFaces, type Camera, type ProjectedFace } from "./math";
import type { Scene } from "./geometry";
import type { Features } from "./state";
import type { RetrofitId } from "../types";

function Surface({
  face,
  focus,
}: {
  face: ProjectedFace;
  focus: RetrofitId | null;
}) {
  const highlighted = Boolean(focus && face.feature === focus);
  const rotor = face.id === "heat-pump-fan";
  return (
    <g
      data-feature={face.feature}
      data-feature-status={face.status}
      data-highlighted={highlighted ? "true" : undefined}
    >
      <polygon
        data-face={face.id}
        points={face.points}
        fill={face.fill}
        stroke={
          face.stroke ?? (face.status === "proposed" ? "#a16a18" : "none")
        }
        strokeWidth={face.stroke ? 1 : 1.35}
        strokeLinejoin="round"
        strokeDasharray={face.status === "unknown" ? "3 3" : undefined}
        className={highlighted ? "hc-highlight" : undefined}
      />
      {face.details.length > 0 && (
        <g className={rotor ? "hc-fan-rotor" : undefined}>
          {face.details.map((detail) => (
            <Surface key={detail.id} face={detail} focus={focus} />
          ))}
        </g>
      )}
    </g>
  );
}

/** Pure SVG render: no hooks, effects, controls, IDs or external assets. */
export function SceneSvg({
  scene,
  camera,
  features,
  label,
  focus = null,
  thumbnail = false,
}: {
  scene: Scene;
  camera: Camera;
  features: Features;
  label: string;
  focus?: RetrofitId | null;
  thumbnail?: boolean;
}) {
  const faces = projectFaces(scene.faces, camera);
  const controls = features.smart_controls;
  const hasControls =
    controls.status === "installed" || controls.status === "proposed";
  return (
    <svg
      className={thumbnail ? "hc-thumbnail" : "hc-model"}
      viewBox="0 0 560 360"
      role="img"
      aria-label={label}
      data-family={scene.family}
      data-camera={`${camera.yaw.toFixed(5)}:${camera.zoom.toFixed(2)}`}
    >
      <title>{label}</title>
      <ellipse
        cx="280"
        cy="301"
        rx="186"
        ry="24"
        fill="#c4d1be"
        opacity=".25"
      />
      {faces.map((face) => (
        <Surface key={face.id} face={face} focus={focus} />
      ))}
      {scene.family === "unknown" && (
        <g fill="#566d5a" textAnchor="middle">
          <text x="280" y="180" fontSize="52" fontFamily="Georgia, serif">
            ?
          </text>
          {!thumbnail && (
            <text x="280" y="212" fontSize="13">
              No building type inferred
            </text>
          )}
        </g>
      )}
      {!thumbnail && hasControls && (
        <g
          data-feature="smart_controls"
          data-feature-status={controls.status}
          data-highlighted={focus === "smart_controls" ? "true" : undefined}
          className="hc-controls-marker"
        >
          <rect
            x="440"
            y="38"
            width="70"
            height="60"
            rx="12"
            fill="#f9faf3"
            stroke={controls.status === "proposed" ? "#a16a18" : "#527b61"}
            strokeWidth={focus === "smart_controls" ? 3 : 1.5}
            strokeDasharray={controls.status === "proposed" ? "5 3" : undefined}
          />
          <circle cx="475" cy="63" r="13" fill="#dbe6d2" stroke="#527b61" />
          <path
            d="M475 54V62M470 57a8 8 0 1 0 10 0"
            fill="none"
            stroke="#355c4d"
            strokeWidth="2"
          />
          <text x="475" y="88" fontSize="10" textAnchor="middle" fill="#355c4d">
            Controls
          </text>
        </g>
      )}
    </svg>
  );
}
