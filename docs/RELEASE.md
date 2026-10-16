# GreenHome Advisor release

## Scope

A separate personal portfolio continuation of Team 225's original GreenHome
prototype. The original competition repository and submitted artifacts are
not modified by this release.

New work: explicit tariff comparisons, named package alternatives, introductory
journey, feature-linked house schematic, and adviser summary. Existing
calculation, privacy, missing-data, ownership and synthetic-model limitations
remain in force.

The 16 October upgrade adds linked interactive current/proposed house
illustrations, a separate 200-home fictional catalogue, and dashboard bill
comparisons sharing temporary rates with Costs & packages. Catalogue data is
independently generated, not new model training, survey data or an organiser
dataset. Original four seed homes and private workspace limits remain unchanged.
See `docs/HOME_COMPARISON.md` and `docs/DEMO_CATALOGUE.md`.

Tariffs start unknown. The 25p/7p example is an explicit illustration, never
a claim about current rates. Score and required energy-percentage ranking do
not depend on tariffs. The house is a schematic, not a surveyed replica.

## Publication boundary

Source, tests, trained artifacts and documented data sources may be published.
Credentials, environment files, private databases, runtime/session logs,
historical chat exports, evaluator credentials, and competitor material must
not be committed. Historical reports are selected rather than copied wholesale.

## Validation status

Initial copied baseline: 330 required backend tests and 263 frontend tests.
These counts are dated baseline evidence, not the final release total. Final
test/build, deployed-API, persistence and desktop/mobile screenshot results
are recorded in `docs/VALIDATION.md`. The verified public application is at
`https://greenhome-advisor-xi.vercel.app`; its source revision is recorded there.
