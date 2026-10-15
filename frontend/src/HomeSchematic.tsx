import type { Home, RetrofitId } from "./types";

export function HomeSchematic({
  home,
  selected,
}: {
  home: Home;
  selected: RetrofitId[];
}) {
  const has = (id: RetrofitId) => selected.includes(id);
  const solar = (home.solar_kwp ?? 0) > 0;
  const pump = home.heating === "heat_pump";
  const loft = home.insulation === "good";
  const glazing = home.glazing === "double" || home.glazing === "triple";
  const controls = home.smart_controls === true;
  const status = (installed: boolean, id: RetrofitId) =>
    installed ? "installed" : has(id) ? "proposed" : "not selected";
  return (
    <figure className="home-schematic">
      <svg
        viewBox="0 0 580 380"
        role="img"
        aria-label="Home improvement schematic showing current and proposed features"
      >
        <defs>
          <pattern
            id="roof-lines"
            width="18"
            height="14"
            patternUnits="userSpaceOnUse"
          >
            <path d="M0 13H18" stroke="#53695f" strokeWidth="1" />
          </pattern>
        </defs>
        <ellipse cx="300" cy="344" rx="210" ry="14" fill="#d7e5df" />
        <path
          d="M101 191L277 65 451 191"
          fill="#dfe9e3"
          stroke="#315147"
          strokeWidth="4"
          strokeLinejoin="round"
        />
        <path d="M122 187L277 78 432 187Z" fill="#244b41" />
        <path d="M122 187L277 78 432 187Z" fill="url(#roof-lines)" />
        <path
          d="M351 116V69H378V137"
          fill="#b9b4a2"
          stroke="#315147"
          strokeWidth="3"
        />
        <path
          d="M131 191H423V338H131Z"
          fill="#f3f0e6"
          stroke="#315147"
          strokeWidth="3"
        />
        <path
          d="M137 198H417"
          stroke={loft || has("loft_insulation") ? "#cf8a27" : "#d7d4c7"}
          strokeWidth="12"
        />
        <path
          d="M145 223H407M145 249H407M145 275H407M145 301H407"
          stroke="#dcd7c8"
          strokeWidth="1"
        />
        {[167, 321].map((x) => (
          <g key={x}>
            <rect
              x={x}
              y="226"
              width="65"
              height="69"
              rx="3"
              fill={glazing || has("double_glazing") ? "#add7d7" : "#d7e3df"}
              stroke="#315147"
              strokeWidth="3"
            />
            <path
              d={`M${x + 32} 226V295M${x} 260H${x + 65}`}
              stroke="#315147"
              strokeWidth="3"
            />
            {(glazing || has("double_glazing")) && (
              <rect
                x={x + 5}
                y="231"
                width="55"
                height="59"
                rx="1"
                fill="none"
                stroke="#62999c"
              />
            )}
          </g>
        ))}
        <rect
          x="256"
          y="248"
          width="48"
          height="90"
          rx="3"
          fill="#6c8978"
          stroke="#315147"
          strokeWidth="3"
        />
        <circle cx="294" cy="292" r="3" fill="#f3d17e" />
        {(solar || has("solar_pv")) && (
          <g transform="translate(281 118) skewX(31)">
            <rect
              width="96"
              height="49"
              rx="3"
              fill="#1e5964"
              stroke={solar ? "#b3d8cc" : "#e5ac4e"}
              strokeWidth="3"
            />
            <path
              d="M32 0V49M64 0V49M0 24H96"
              stroke="#b3d8cc"
              strokeWidth="1.5"
            />
          </g>
        )}
        {(pump || has("heat_pump")) && (
          <g>
            <rect
              x="432"
              y="275"
              width="70"
              height="59"
              rx="6"
              fill="#e5ece8"
              stroke={pump ? "#315147" : "#cc8c32"}
              strokeWidth="3"
            />
            <circle
              cx="461"
              cy="305"
              r="20"
              fill="none"
              stroke="#557c71"
              strokeWidth="2"
            />
            <path
              d="M461 289V321M445 305H477M450 294L472 316M450 316L472 294"
              stroke="#557c71"
              strokeWidth="2"
            />
            <path
              d="M484 289H494M484 297H494M484 313H494M484 321H494"
              stroke="#557c71"
              strokeWidth="2"
            />
          </g>
        )}
        {(controls || has("smart_controls")) && (
          <g>
            <rect
              x="364"
              y="311"
              width="23"
              height="18"
              rx="4"
              fill="#225c48"
            />
            <circle cx="375" cy="320" r="5" fill="#b4d5c5" />
          </g>
        )}
        <path d="M79 337H519" stroke="#517669" strokeWidth="2" />
        <g fill="#8bb19a">
          <ellipse cx="103" cy="307" rx="24" ry="34" />
          <ellipse cx="512" cy="312" rx="19" ry="28" />
        </g>
        <path d="M103 312V341M512 320V340" stroke="#517669" strokeWidth="3" />
      </svg>
      <div className="schematic-legend" aria-label="Schematic feature status">
        {(
          [
            ["Loft insulation", loft, "loft_insulation"],
            ["Glazing", glazing, "double_glazing"],
            ["Heat pump", pump, "heat_pump"],
            ["Solar panels", solar, "solar_pv"],
            ["Smart controls", controls, "smart_controls"],
          ] as [string, boolean, RetrofitId][]
        )
          .filter(([, installed, id]) => installed || has(id))
          .map(([label, installed, id]) => (
            <span
              key={id}
              className={installed ? "feature-installed" : "feature-proposed"}
            >
              {label} · {status(installed, id)}
            </span>
          ))}
        {!selected.length &&
          !solar &&
          !pump &&
          !loft &&
          !glazing &&
          !controls && <span>Your current recorded features</span>}
      </div>
      <figcaption>
        Illustrative schematic, not a surveyed home. Proposed work is not
        installed work.
      </figcaption>
    </figure>
  );
}
