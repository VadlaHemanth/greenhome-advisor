# Data source and reuse record

Team 225 · verified 10 October 2026 · England/Wales pilot.

This records notices actually inspected, not a legal opinion or government
endorsement. The project's software MIT licence is not evidence of the licence
for government datasets. Machine-readable records and actual hashes are in
`data/source_register.json` and `data/reference_cases_source_evidence.json`.

## NEED 2026: dataset-specific evidence

The [official dataset catalogue](https://www.data.gov.uk/dataset/7390402c-e7ce-4e2f-bb08-d8d65f852f47/nationalenergyefficiencydataframeworkanonymiseddata)
explicitly identifies **UK Open Government Licence (OGL)**, with its licence link
pointing to [version 3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
The [2026 metadata resource record](https://ckan.publishing.service.gov.uk/dataset/nationalenergyefficiencydataframeworkanonymiseddata/resource/d6b40609-730f-4172-9c9d-a1f01b03f173?inner_span=True)
also explicitly labels its licence OGL and its creation/update as 11 June 2026.
This is dataset/resource-specific evidence, stronger than merely citing the
generic GOV.UK footer.

The [DESNZ publication](https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026)
identifies the 50,000-row CSV, 4-million-row sample and metadata workbook,
published 11 June 2026. Only the existing 50,000-row sample supports this project's
observed-energy benchmark; the larger release was not downloaded.

**Attribution retained for reuse:**

Source: Department for Energy Security and Net Zero, National Energy Efficiency
Data-Framework (NEED), anonymised data 2026, 50,000-property sample and metadata.

> Contains public sector information licensed under the Open Government Licence v3.0.

Link the provider and OGL where possible. Do not imply endorsement. OGL excludes
personal data and third-party rights the provider cannot license, and does not
warrant suitability. No separate dataset-specific attribution statement was
found in the inspected catalogue/resource/publication or cached ODS; the default
OGL attribution above is retained. Check notices again for any future component
or redistribution; this record does not license unrelated sources.

### Verification and original acquisition distinction

- Direct official HTTPS fetches confirmed the notices and attachment links.
  Exa was used for targeted discovery and cross-checking, not as the publisher.
- Existing local CSV and ODS hashes matched `data/data_manifest.json`.
- A fresh official ODS download matched the cached ODS SHA-256.
- The CSV was **not re-downloaded in this task**. Its recorded cached check time
  does not prove its original acquisition date, which remains unknown.
- The ODS `Cover_sheet`, `Metadata` and `Production_steps` were inspected;
  no embedded alternative licence statement was found.

Hash-pinned source order supports local row IDs only. Do not re-identify rows,
join them to addresses or infer customer ownership. The source represents
anonymised current domestic properties in England/Wales after publisher
filtering, not all UK households. Meter-derived annual consumption is not a
measured retrofit-effect target. Preserve separate fuel quality flags and
missingness, time-window and stale/latest-EPC limitations.

## Carbon conversion factors

The [DESNZ 2026 publication](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026)
was published 11 June 2026 and updated 31 July 2026. It says the July correction
affected missing/zero values in the automatic-processing **flat file**, not the
June full-set workbook. The workbook actually fetched and inspected was the
[2026 full set](https://assets.publishing.service.gov.uk/media/6a29392bade52dc0882218a8/ghg-conversion-factors-2026-full-set.xlsx).
Its bytes and SHA-256 are recorded, together with direct ZIP/XML cell evidence.

| Quantity | Sheet / cell | Factor | Unit / basis |
|---|---|---:|---|
| UK electricity generated | `UK electricity!E25` | 0.13096 | kgCO₂e/kWh |
| Natural gas | `Fuels!D42` | 0.18231 | kgCO₂e/kWh, gross calorific value |

The XML float for electricity is stored as `0.13095999999999999`; the published
five-decimal factor used in the reference is 0.13096. Gas net-CV is a different
row and must not be substituted for gross-CV gas/boiler assumptions.

This is operational electricity generation plus gas combustion. It excludes
well-to-tank, transmission/distribution losses, embodied carbon and refrigerants;
it is not a whole-life retrofit footprint. Signed fuel changes matter. A sourced
carbon factor does not validate a hypothetical energy saving.

The official publication footer links OGL v3 except where otherwise stated.
No workbook-specific alternative notice was found in the inspected Introduction
sheet. Attribute DESNZ, *Greenhouse gas reporting: conversion factors 2026*,
full set, and retain the OGL statement above. The official methodology PDF link
was verified on the publication, **but that PDF was not read in this task**.
No claim of a full methodology or legal audit is made.

## New fictional references

`data/reference_cases.json` is newly generated project-authored fictional data.
It is not a repackaged NEED property sample and has no empirical savings labels.
Its 15%/7% loft, 10% glazing, 7% controls, default SPF/heat-share/PV assumptions
and cost ranges are disclosed prototype assumptions, not quantities established
by the government sources. Carbon factors retain their official attribution.
The independent rational simulator checks implementation under these assumptions,
not physical accuracy, adoption, comfort, real valuations or memory benefit.

The source search was narrowly scoped to English-language official NEED,
carbon-factor and OGL records on 10 October 2026; no systematic retrofit-effects
literature review was performed. Evidence is strong for the inspected metadata
and workbook cells, but absent here for real-home retrofit outcomes.
