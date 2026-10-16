import { ApiError, request } from "./api";
import type { Home, RankedHome, RankingStatus } from "./types";
import { validHome, validRanking } from "./workspaceValidation";

export const DEMO_PROPERTY_TYPES = [
  "Detached",
  "Semi detached",
  "Mid terrace",
  "End terrace",
  "Bungalow",
  "Flat",
] as const;
export type CatalogueFilters = {
  q: string;
  property_type: string;
  status: string;
  page: number;
};
export type DemoEntry = {
  home: Home;
  label: string;
  kind: string;
  notes: string[];
  ranking: RankedHome;
};
export type DemoCataloguePage = {
  version: string;
  total: number;
  filtered_total: number;
  page: number;
  page_size: number;
  page_count: number;
  entries: DemoEntry[];
  summary: { assessed: number; evidence_needed: number; flagged: number };
  provenance: {
    label: string;
    synthetic: true;
    training_use: false;
    generator_version: string;
    sha256: string;
  };
  policy: string;
};

const object = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const integer = (v: unknown, min: number, max: number): v is number =>
  typeof v === "number" && Number.isInteger(v) && v >= min && v <= max;
const text = (v: unknown): v is string =>
  typeof v === "string" && v.trim().length > 0;
const evidenceStatuses: RankingStatus[] = [
  "insufficient_evidence",
  "unsupported",
];

/** Validate each page independently; ranks refer to the full fixed catalogue. */
export function validDemoCatalogue(v: unknown): v is DemoCataloguePage {
  if (
    !object(v) ||
    !text(v.version) ||
    v.total !== 200 ||
    !integer(v.filtered_total, 0, v.total) ||
    !integer(v.page, 1, 200) ||
    !integer(v.page_size, 1, 24) ||
    v.page_count !== Math.ceil(v.filtered_total / v.page_size) ||
    !Array.isArray(v.entries) ||
    v.entries.length !==
      Math.max(
        0,
        Math.min(v.page_size, v.filtered_total - (v.page - 1) * v.page_size),
      ) ||
    !text(v.policy) ||
    !object(v.provenance) ||
    !object(v.summary)
  )
    return false;
  const p = v.provenance,
    s = v.summary;
  if (
    p.synthetic !== true ||
    p.training_use !== false ||
    !text(p.label) ||
    !text(p.generator_version) ||
    typeof p.sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(p.sha256) ||
    !integer(s.assessed, 0, v.filtered_total) ||
    !integer(s.evidence_needed, 0, v.filtered_total) ||
    !integer(s.flagged, 0, v.filtered_total) ||
    s.assessed + s.evidence_needed !== v.filtered_total
  )
    return false;
  const ids = new Set<string>();
  return v.entries.every((entry) => {
    if (
      !object(entry) ||
      !validHome(entry.home) ||
      !text(entry.home.property_id) ||
      entry.home.data_kind !== "synthetic_demo" ||
      !text(entry.label) ||
      !text(entry.kind) ||
      !Array.isArray(entry.notes) ||
      !entry.notes.every(text) ||
      !object(entry.ranking) ||
      entry.ranking.property_id !== entry.home.property_id ||
      ids.has(entry.home.property_id) ||
      !validRanking({ policy: v.policy, rows: [entry.ranking], warnings: [] })
    )
      return false;
    const row = entry.ranking as unknown as RankedHome;
    if (evidenceStatuses.includes(row.status)) {
      if (row.rank !== null || row.improvement_percent !== null) return false;
    } else if (!integer(row.rank, 1, 200)) return false;
    ids.add(entry.home.property_id);
    return true;
  });
}

export function catalogueQuery(filters: CatalogueFilters): string {
  const query = new URLSearchParams({
    page: String(filters.page),
    page_size: "12",
  });
  if (filters.q.trim()) query.set("q", filters.q.trim());
  if (filters.property_type) query.set("property_type", filters.property_type);
  if (filters.status) query.set("status", filters.status);
  return query.toString();
}

export async function loadDemoCatalogue(
  filters: CatalogueFilters,
  signal?: AbortSignal,
): Promise<DemoCataloguePage> {
  const result = await request<unknown>(
    `/demo-catalogue?${catalogueQuery(filters)}`,
    undefined,
    signal,
  );
  if (
    !validDemoCatalogue(result) ||
    result.page !== filters.page ||
    result.page_size !== 12
  )
    throw new ApiError(
      "The example catalogue response could not be verified. Please retry.",
      502,
      "invalid_response",
    );
  if (
    result.entries.some(
      (entry) =>
        (filters.property_type &&
          entry.home.property_type !== filters.property_type) ||
        (filters.status && entry.ranking.status !== filters.status),
    )
  )
    throw new ApiError(
      "The example catalogue returned a different filter. Please retry.",
      502,
      "invalid_response",
    );
  return result;
}
