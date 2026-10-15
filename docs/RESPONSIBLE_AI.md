# Responsible AI and limitations

The public NEED data are anonymised. The demonstration homes and synthetic valuation
targets are fictional. Do not upload real customer personal data or use the application
as a formal EPC assessment, installer survey, mortgage decision or financial valuation.

The score uses explicit fixed weights and monotonic prototype mappings. Measured energy
can reflect occupancy, affordability and unmet comfort needs; low consumption is not proof
of a well-insulated home. The recorded EPC date may differ from the consumption period.

Energy calculations are simplified screening scenarios, not a dynamic thermal model.
Inputs and assumptions, including heating-use allocation, are visible. Consent and
installer readiness are user confirmations, not verified approvals. Missing data do not
become zero and unavailable evidence must be acknowledged.

Property-value outputs from the synthetic-reference model are demonstrations of a
disclosed generator, not observed UK premiums or causal resale gains. Errors and interval
coverage against those targets do not establish real-market accuracy.

Gemini is restricted to explaining approved evidence and identifying supported scenarios.
Its output must pass validation. A failed or unavailable API uses an explicitly labelled
fallback; this must not be presented as a successful live LLM test.

Model performance may vary by region, property type and data completeness. Validate on
property-held-out records, compare simple baselines and disclose slices/limitations.
Never copy target data into predictors or tune on the final test.

Carbon uses a stated operational boundary and consistent documented factors. It excludes
upstream fuel and electricity, T&D, construction, refrigerants and lifecycle effects.

Users retain control of scenario selections. The app does not order installations, submit
applications, promise subsidies, or take financial actions.

## Confirmed fictional memory

### Multiple properties and customer-wide scope

Schema 2 explicitly stores each fictional customer's property records. Each
property has independent bills, permissions, plans, local budget and completion
history. Global customer exclusions are combined with local deferrals only in
the effective calculation input. Shared budget checks run transactionally across
all sibling properties. Completed upper-cost planning reservations are retained;
they are not reported as actual spending or cumulative measured savings.

Migration preserves existing records and does not guess ownership, spending or
new preferences. Old unpriced completions leave the legacy reserve unknown until
explicitly confirmed before a finite shared cap. Correcting or removing completed
work and ownership transfer are not supported in this release; no silent
history rewrite is performed. A selected completed measure or regressed installed
feature is rejected to avoid counting an improvement twice.

New ownership-case generation assigns customer IDs and groups before generating
properties/histories; siblings remain in one split and recorded-time chronology
controls available information. Earlier model/memory reports remain unchanged
and are not relabelled as multi-property or customer-level forecast validation.
The new experiment is fictional integration evidence, not a human-user outcome
study or a learned ownership model. NEED owner identities are neither present
nor inferred.

### Active third-party model gateway

The integrated user-selected provider is Xkiro with the requested
`qwen/qwen3.8-max:free` identifier. The OpenAI SDK is a compatible client, not
the model provider. We verified the gateway catalogue and bounded fictional
responses, not underlying model identity, hosting or policy compliance.
The provider notice and separate per-question opt-in state the data transfer.
There is no silent cross-provider fallback or arbitrary LLM prose on screen.
Keys remain server-side. See `docs/ACTIVE_LLM.md` for policy/source details.

Monthly CSV import processes only month and two kWh columns in memory. It
rejects duplicates, invalid/future periods, formula cells and invalid numbers.
Incomplete coverage remains unknown rather than scaled from a short season.
The user previews and applies totals; imported rows are not retained by the API.

Persistence is optional and limited to fictional workspace records. Its random
HttpOnly cookie identifies one private browser workspace; only a hash is stored.
Reads, writes, exports and deletion are scoped to that workspace. Customer and
adviser views are not separate authenticated bank roles. Real customer sharing
would require a different identity, permissions and lawful-processing design.

Memory stores confirmed budget, deferrals, selected work and completion history,
not arbitrary chats, LLM prose or secret values. Users can inspect, export and
delete it. The fixed 30-day expiry is enforced on access; physical expired-row
cleanup occurs during creation/maintenance rather than a continuously running
retention scheduler. Deleting live rows is not forensic erasure from backups.

Completed work clears old energy baselines and does not invent a new EPC,
valuation or observed saving. Later readings require explicit confirmation.
Evaluation separates customers and respects when an event became known, not only
its occurrence date. The eight-customer experiment demonstrates state retention,
not real-user benefit or a superior recommendation algorithm.

## Evidence and human oversight

Independent rational references test our documented arithmetic, not real homes.
The inspected reference test diagnostics were used to correct rank roundoff;
post-fix reruns are regression evidence, not fresh untouched holdouts.
Operational LLM checks verify returned claims against engine evidence; that does
not validate the engine's empirical assumptions. Earlier failures remain recorded.
No probability of winning the competition or claim of unlimited scaling is made.
