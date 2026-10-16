import { home } from "./fixtures";
import { ranking } from "./workspaceFixtures";
import type { DemoCataloguePage } from "../demoCatalogue";

export function catalogueFixture(page = 1): DemoCataloguePage {
  const length = page === 17 ? 8 : 12;
  const start = (page - 1) * 12;
  return {
    version: "2026.10.1",
    total: 200,
    filtered_total: 200,
    page,
    page_size: 12,
    page_count: 17,
    entries: Array.from({ length }, (_, i) => {
      const id = `CAT-${String(start + i + 1).padStart(3, "0")}`;
      return {
        home: { ...home, property_id: id },
        label: `Fictional home ${start + i + 1}`,
        kind: "generated",
        notes: ["Synthetic demonstration; not measured household data."],
        ranking: {
          ...ranking.rows[0],
          property_id: id,
          rank: start + i + 1,
          flagged: true,
        },
      };
    }),
    summary: { assessed: 180, evidence_needed: 20, flagged: 70 },
    provenance: {
      label: "Independently generated fictional examples",
      synthetic: true,
      training_use: false,
      generator_version: "1",
      sha256: "a".repeat(64),
    },
    policy: "Global purchased-energy opportunity under each home's budget.",
  };
}
