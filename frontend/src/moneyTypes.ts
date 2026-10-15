import type { NullableNumber, RetrofitId } from "./types";

/** Expanded TariffInput returned by /money-plan. Rates are pence, not GBP. */
export type MoneyTariffs = {
  electricity_pence: NullableNumber;
  gas_pence: NullableNumber;
  source: "user_entered" | "illustrative";
  as_of: string | null;
  electricity_standing_before_pence_per_day: NullableNumber;
  electricity_standing_after_pence_per_day: NullableNumber;
  gas_standing_before_pence_per_day: NullableNumber;
  gas_standing_after_pence_per_day: NullableNumber;
};

export type MoneyTariffDraft = {
  electricity_pence: string;
  gas_pence: string;
  as_of: string;
  source: MoneyTariffs["source"];
};
export type MoneyTariffField = Exclude<keyof MoneyTariffDraft, "source">;
export type MoneyTariffErrors = Partial<Record<MoneyTariffField, string>>;

export type MoneyAmounts = {
  before_gbp: NullableNumber;
  after_gbp: NullableNumber;
  saving_gbp: NullableNumber;
};

export type MoneyPackage = {
  id: string;
  retrofits: RetrofitId[];
  cost_gbp: [number, number];
  net_saving_kwh: NullableNumber;
  improvement_percent: NullableNumber;
  carbon_reduction_kgco2e: NullableNumber;
  money_saving_gbp: NullableNumber;
  recommendation_reason: string;
};

export type MoneyPlanResponse = {
  money: {
    status: "available" | "partial" | "unavailable";
    electricity: MoneyAmounts;
    gas: MoneyAmounts;
    total: MoneyAmounts;
    /** Signed annual saving / 12; NOT a predicted monthly bill. */
    monthly_average_gbp: NullableNumber;
    payback_years: { low: number; high: number } | null;
    cost_gbp: [number, number];
    standing_charge_note: string;
  };
  packages: MoneyPackage[];
  picks: {
    energy: string | null;
    bills: string | null;
    lowest_cost: string | null;
  };
  tariffs: MoneyTariffs;
  warnings: string[];
};
