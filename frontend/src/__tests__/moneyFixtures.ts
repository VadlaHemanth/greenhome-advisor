import type { MoneyPlanResponse, MoneyTariffs } from "../moneyTypes";
import type { RetrofitId } from "../types";
import { home } from "./fixtures";

// Offline, fictional contract fixtures, not a replacement money calculator.
export const moneyHome = { ...home, property_id: "DEMO01" };
export const moneySelected: RetrofitId[] = ["loft_insulation", "heat_pump"];
export const illustrativeTariffs: MoneyTariffs = {
  electricity_pence: 25,
  gas_pence: 7,
  source: "illustrative",
  as_of: null,
  electricity_standing_before_pence_per_day: null,
  electricity_standing_after_pence_per_day: null,
  gas_standing_before_pence_per_day: null,
  gas_standing_after_pence_per_day: null,
};

export function moneyResponse(): MoneyPlanResponse {
  return {
    money: {
      status: "available",
      electricity: { before_gbp: 1200, after_gbp: 1778, saving_gbp: -578 },
      gas: { before_gbp: 840, after_gbp: 168, saving_gbp: 672 },
      total: { before_gbp: 2040, after_gbp: 1946, saving_gbp: 94 },
      monthly_average_gbp: 7.83,
      payback_years: { low: 104.26, high: 176.6 },
      cost_gbp: [9800, 16600],
      standing_charge_note:
        "Standing charges excluded and assumed unchanged, not zero. Gas supply is retained.",
    },
    packages: [
      {
        id: "loft_insulation",
        retrofits: ["loft_insulation"],
        cost_gbp: [800, 1600],
        net_saving_kwh: 1440,
        improvement_percent: 8.571428571428571,
        carbon_reduction_kgco2e: 262.5264,
        money_saving_gbp: 100.8,
        recommendation_reason: "Largest positive annual bill saving.",
      },
    ],
    picks: {
      energy: "loft_insulation",
      bills: "loft_insulation",
      lowest_cost: "loft_insulation",
    },
    tariffs: { ...illustrativeTariffs },
    warnings: ["Fictional demonstration; not measured household savings."],
  };
}

export function negativeMoney(): MoneyPlanResponse {
  const data = moneyResponse();
  data.money.electricity = {
    before_gbp: 1200,
    after_gbp: 1880,
    saving_gbp: -680,
  };
  data.money.total = { before_gbp: 2040, after_gbp: 2048, saving_gbp: -8 };
  data.money.monthly_average_gbp = -0.67;
  data.money.cost_gbp = [9000, 15000];
  data.money.payback_years = null;
  return data;
}

export function partialMoney(): MoneyPlanResponse {
  const data = moneyResponse();
  data.money.status = "partial";
  data.money.gas = { before_gbp: null, after_gbp: null, saving_gbp: null };
  data.money.total = { before_gbp: null, after_gbp: null, saving_gbp: null };
  data.money.monthly_average_gbp = null;
  data.money.payback_years = null;
  data.tariffs.gas_pence = null;
  data.tariffs.source = "user_entered";
  data.packages[0].money_saving_gbp = null;
  data.picks.bills = null;
  return data;
}

export function zeroMoney(): MoneyPlanResponse {
  const data = moneyResponse();
  for (const fuel of ["electricity", "gas", "total"] as const)
    data.money[fuel] = { before_gbp: 0, after_gbp: 0, saving_gbp: 0 };
  data.money.monthly_average_gbp = 0;
  data.money.payback_years = null;
  data.tariffs = {
    ...illustrativeTariffs,
    electricity_pence: 0,
    gas_pence: 0,
    source: "user_entered",
  };
  data.packages[0].money_saving_gbp = 0;
  data.picks.bills = null;
  return data;
}

export function unchangedMoney(): MoneyPlanResponse {
  const data = moneyResponse();
  data.money.electricity = {
    before_gbp: 1200,
    after_gbp: 1200,
    saving_gbp: 0,
  };
  data.money.gas = { before_gbp: 840, after_gbp: 840, saving_gbp: 0 };
  data.money.total = { before_gbp: 2040, after_gbp: 2040, saving_gbp: 0 };
  data.money.monthly_average_gbp = 0;
  data.money.payback_years = null;
  data.money.cost_gbp = [0, 0];
  return data;
}
