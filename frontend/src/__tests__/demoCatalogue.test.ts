import { describe, expect, it } from "vitest";
import { validDemoCatalogue, catalogueQuery } from "../demoCatalogue";
import { catalogueFixture } from "./demoCatalogueFixtures";

describe("fictional catalogue response boundary", () => {
  it("accepts valid pages without changing the server's global ranks", () => {
    const result = catalogueFixture(17);
    expect(validDemoCatalogue(result)).toBe(true);
    expect(result.entries[0].ranking.rank).toBe(193);
  });

  it.each([
    (v: ReturnType<typeof catalogueFixture>) => {
      v.total = 201;
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.filtered_total = 201;
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.page_count = 18;
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.page = 0;
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.entries.pop();
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.entries[0].home.data_kind = "user_entered";
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.entries[0].home.electricity_kwh = -1;
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.entries[1] = structuredClone(v.entries[0]);
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.entries[0].ranking.property_id = "WRONG";
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.entries[0].ranking.rank = 201;
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      Object.assign(v.provenance, { synthetic: false });
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      Object.assign(v.provenance, { training_use: true });
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.provenance.sha256 = "invalid";
    },
    (v: ReturnType<typeof catalogueFixture>) => {
      v.summary.evidence_needed = 201;
    },
  ])("rejects malformed, contradictory or non-fictional data", (mutate) => {
    const data = catalogueFixture();
    mutate(data);
    expect(validDemoCatalogue(data)).toBe(false);
  });

  it("accepts an explicit empty filtered view without inventing zero estimates", () => {
    const data = {
      ...catalogueFixture(),
      filtered_total: 0,
      entries: [],
      page_count: 0,
      summary: { assessed: 0, evidence_needed: 0, flagged: 0 },
    };
    expect(validDemoCatalogue(data)).toBe(true);
  });

  it("encodes filters and page boundaries without including home facts", () => {
    const query = new URLSearchParams(
      catalogueQuery({
        q: "CAT-010",
        property_type: "Semi detached",
        status: "",
        page: 2,
      }),
    );
    expect(query.get("q")).toBe("CAT-010");
    expect(query.get("property_type")).toBe("Semi detached");
    expect(query.get("page")).toBe("2");
    expect(query.get("page_size")).toBe("12");
    expect(query.has("status")).toBe(false);
  });
});
