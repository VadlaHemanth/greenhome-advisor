import {
  ArrowUpRight,
  ChartNoAxesCombined,
  House,
  ShieldCheck,
} from "lucide-react";
import { HomeSchematic } from "./HomeSchematic";
import type { Home } from "./types";

const example: Home = {
  property_id: "WELCOME-EXAMPLE",
  property_type: "Semi detached",
  age_band: 2,
  region: "E12000007",
  floor_area_m2: 100,
  epc_rating: "E",
  electricity_kwh: 4800,
  gas_kwh: 12000,
  heating: "gas_boiler",
  insulation: "poor",
  glazing: "single",
  solar_kwp: 0,
  smart_controls: false,
  roof_access: true,
  listed_building: false,
  consent_confirmed: false,
  heat_pump_ready: true,
  current_value_gbp: null,
  budget_gbp: null,
  data_kind: "synthetic_demo",
};

export function Welcome({
  onExample,
  onOwnHome,
  onEvidence,
}: {
  onExample: () => void;
  onOwnHome: () => void;
  onEvidence: () => void;
}) {
  return (
    <div className="release-welcome">
      <section className="welcome-lead">
        <div className="welcome-copy">
          <p className="release-kicker">
            <House size={16} aria-hidden="true" /> A considered improvement
            starts here
          </p>
          <h1>
            Know your home.
            <br />
            Choose your next step.
          </h1>
          <p className="welcome-intro">
            What should you improve first? Compare suitable work, the energy it
            could save and what that means for your bills.
          </p>
          <div className="welcome-actions">
            <button className="button primary" onClick={onExample}>
              Explore an example home{" "}
              <ArrowUpRight size={17} aria-hidden="true" />
            </button>
            <button className="button secondary" onClick={onOwnHome}>
              Assess my own home
            </button>
          </div>
          <p className="welcome-scope">
            England and Wales pilot. Own-home assessments are temporary and
            unsaved.
          </p>
        </div>
        <div className="welcome-visual">
          <div className="visual-caption">
            <span>A fictional home, a possible plan</span>
            <span className="release-tag">Before you spend</span>
          </div>
          <HomeSchematic
            home={example}
            selected={["loft_insulation", "solar_pv"]}
          />
        </div>
      </section>
      <section
        className="welcome-steps"
        aria-label="Your home improvement journey"
      >
        <article>
          <span className="step-index">1</span>
          <h2>Understand today</h2>
          <p>
            A score with every contribution explained. Missing details remain
            visible.
          </p>
        </article>
        <article>
          <span className="step-index">2</span>
          <h2>Compare what fits</h2>
          <p>
            Suitable packages, clear costs and separate electricity and gas
            changes.
          </p>
        </article>
        <article>
          <span className="step-index">3</span>
          <h2>Decide with evidence</h2>
          <p>
            Use your tariffs, inspect assumptions and take a clear plan to an
            installer.
          </p>
        </article>
      </section>
      <section className="welcome-evidence">
        <div>
          <ShieldCheck size={24} aria-hidden="true" />
          <h2>Every estimate has a boundary.</h2>
          <p>
            Calculations own the figures. AI only explains approved facts.
            Savings are estimates; the property-value model is a labelled
            synthetic demonstration.
          </p>
        </div>
        <button className="button secondary" onClick={onEvidence}>
          Explore methods & evidence{" "}
          <ChartNoAxesCombined size={17} aria-hidden="true" />
        </button>
      </section>
    </div>
  );
}
