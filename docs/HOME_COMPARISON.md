# Illustrative home comparison

## What it does

The dashboard displays linked **Current** and **Proposed** views of one home's
building family. Six original model families cover detached, semi-detached,
mid-terrace, end-terrace, bungalow and flat inputs. An unknown type remains
unknown. Adjoining buildings and the highlighted flat band provide context;
they do not establish actual ownership boundaries, room layouts or location.

Rotate with the buttons, horizontal pointer/touch drag or left/right keys.
Use plus/minus to zoom and Home or Reset to restore the camera. Both views
always use the same camera. On narrow screens, Current, Proposed and Compare
controls keep both states available without horizontal page scrolling.

The permanent feature list describes current facts and proposed changes.
Feature buttons highlight insulation, panes, solar, heat-pump equipment and
the abstract controls marker; highlighting never selects an improvement.

## Rendering boundary

This is original dimensionless low-poly geometry projected into SVG, not a
photo, survey, physical simulation or externally imported 3D asset. Polygon
backface culling and depth/overlapping-plane ordering keep authored convex
surfaces readable. It is not a general-purpose renderer for arbitrary meshes.
No dimensions or floor plan are inferred from the area, region or property ID.

The browser uses no new 3D dependency and no continuously scheduled animation
loop. Camera changes render on interaction. Feature/fan animation is bounded
to 1.2 seconds, respects reduced-motion preferences, and stops when hidden,
outside the observed viewport or unmounted. Catalogue thumbnails are static
and have no interactive camera or animation effects.

## Truthful current/proposed state

- Confirmed installed features appear in both views.
- Only feasible selected improvements appear as proposals.
- Proposed equipment is not labelled installed.
- Missing facts stay unknown; no default gas boiler, PV, controls or certified
  efficiency improvement is inferred.
- While the selected package is being assessed, proposals are not represented
  as confirmed.
- Clearing selection restores matching current/proposed geometry.
- Changing home facts resets scene/camera state and cannot reuse another home's
  geometry or previous calculation results.
- Flat illustrations do not assume private roof permission or exact equipment
  placement. Relevant permission must be explicitly confirmed.

The scene receives the existing backend's feasibility results; it does not
calculate energy, carbon, money, property value or a projected EPC.

## Bill comparison

The adjacent dashboard card displays server-calculated annual variable cost
before/after, signed annual saving, monthly average and indicative installation
cost. Dashboard and Costs & packages share one temporary tariff controller.

Rates start unknown. The 25p electricity / 7p gas preset is an explicit
illustration, not a current tariff claim. Blank and zero remain distinct.
Changing rates clears the previous result until Calculate is used. Changing
home or workspace resets rates; same-home changes recompute with confirmed
rates. A failed response cannot restore stale results.

Standing charges are explicitly excluded/assumed unchanged in the UI; a heat
pump does not imply removing the gas connection. Monthly saving is annual
saving divided by 12, not a seasonal monthly bill prediction. Non-positive
annual saving does not create positive payback.

See `docs/MONEY.md` for numerical assumptions, `docs/DEMO_CATALOGUE.md` for
the example dataset, and `docs/VALIDATION.md` for actual verification scope.
