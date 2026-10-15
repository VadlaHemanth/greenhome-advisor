import type { ReactNode } from "react";
import type { RetrofitId } from "./types";
import "./retrofitIcons.css";

export type RetrofitIconProps = {
  id: RetrofitId;
  className?: string;
  size?: "sm" | "md" | "lg";
};

const dimensions = { sm: 32, md: 48, lg: 72 } as const;

const geometry = {
  loft_insulation: (
    <>
      <path data-part="roof" d="M7 29 32 10 57 29M13 25v13M51 25v13" />
      <g data-part="insulation-layers">
        <path className="retrofit-icon__sage" d="m10 39 22-8 22 8-22 8Z" />
        <path className="retrofit-icon__gold" d="m10 46 22 8 22-8" />
        <path d="m10 53 22 8 22-8" />
        <path d="m22 35 22 8M17 42l9-3M30 47l9-3" />
      </g>
    </>
  ),
  double_glazing: (
    <>
      <rect
        className="retrofit-icon__sage"
        x="16"
        y="8"
        width="38"
        height="44"
        rx="3"
      />
      <path className="retrofit-icon__gold" d="m10 56 6-6h38l4 6Z" />
      <rect
        className="retrofit-icon__ivory"
        x="10"
        y="13"
        width="38"
        height="43"
        rx="3"
      />
      <g data-part="window-panes" className="retrofit-icon__sage">
        <rect x="15" y="18" width="11" height="32" rx="1" />
        <rect x="32" y="18" width="11" height="32" rx="1" />
      </g>
      <path d="m18 29 5-6M35 29l5-6M29 32v6" />
    </>
  ),
  smart_controls: (
    <>
      <rect
        className="retrofit-icon__ivory"
        x="11"
        y="7"
        width="42"
        height="50"
        rx="9"
      />
      <g data-part="control-dial">
        <circle className="retrofit-icon__sage" cx="32" cy="29" r="13" />
        <path d="M23 29a9 9 0 0 1 18 0" />
        <path d="m32 29 5-5" />
        <circle className="retrofit-icon__gold" cx="32" cy="29" r="2" />
      </g>
      <path d="M20 47h6M23 44v6M38 47h6" />
    </>
  ),
  heat_pump: (
    <>
      <path className="retrofit-icon__gold" d="M12 49h8v7h-8ZM44 49h8v7h-8Z" />
      <rect
        className="retrofit-icon__ivory"
        x="6"
        y="13"
        width="52"
        height="36"
        rx="4"
      />
      <g data-part="fan">
        <circle cx="26" cy="31" r="13" />
        <g className="retrofit-icon__sage">
          <path d="M26 29c-6-5-4-11 1-9 4 2 4 6 1 10Z" />
          <path d="M28 31c7-3 11 2 7 6-4 2-7 0-8-4Z" />
          <path d="M25 33c-1 8-7 9-9 4 0-4 4-6 8-6Z" />
        </g>
        <circle className="retrofit-icon__gold" cx="26" cy="31" r="3" />
      </g>
      <path d="M46 23h6M46 29h6M46 35h6M46 41h6" />
    </>
  ),
  solar_pv: (
    <>
      <path d="m25 44-4 12M42 44l5 12M16 56h36" />
      <path className="retrofit-icon__sage" d="M17 20h34l7 26H8Z" />
      <path
        data-part="solar-grid"
        d="m28 20-1 26M40 20l3 26M14 29h39M11 37h45"
      />
      <g className="retrofit-icon__sun">
        <circle className="retrofit-icon__gold" cx="49" cy="9" r="3" />
        <path d="M49 2V1M42 9h-2M56 9h2M44 4l-1-1M54 4l1-1" />
      </g>
    </>
  ),
} satisfies Record<RetrofitId, ReactNode>;

/** Decorative artwork: keep the retrofit's visible name beside this icon. */
export function RetrofitIcon({
  id,
  className = "",
  size = "md",
}: RetrofitIconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={dimensions[size]}
      height={dimensions[size]}
      className={`retrofit-icon retrofit-icon--${size}${className ? ` ${className}` : ""}`}
      data-retrofit={id}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {geometry[id]}
    </svg>
  );
}
