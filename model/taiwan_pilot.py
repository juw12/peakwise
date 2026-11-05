"""
Watt Reserve - Taiwan factory pilot economics (behind-the-meter BESS)
=====================================================================
1 MW / 2 MWh LFP battery behind the meter of a high-voltage (高壓) factory in a
science / industrial park, on Taipower three-stage time-of-use (三段式時間電價).

Researched inputs (verify against the actual bill and supplier quotes):
  * Taipower 高壓三段式, effective 2025-10-01 (114年10月電價表):
      summer (5/16-10/15) peak 16-22 = 9.39, semi-peak 5.85, off-peak 2.53 NT$/kWh
      non-summer semi-peak 5.47, off-peak 2.32 (off-peak 00-06 and 11-14)
      demand charge 經常契約 223.6, 半尖峰契約 166.9 NT$/kW-month (summer)
  * 2023 tariff (for comparison): summer 5.80 / 3.63 / 1.58, non-summer 3.40 / 1.45
  * Proposed 表後儲能 storage TOU (design targets, CNA 2025-01): summer 10.2 / 6.0 / 2.61,
    non-summer peak (15-21) 9.9, off-peak 2.39
  * Taiwan BESS build cost ≈ NT$12.5 M/MWh (UDN 2025-10)
  * MOEA industrial storage subsidy NT$5 M/MWh, <= 50 % of cost, 1-10 MWh,
    domestic cells, 3-year peak-shift obligation
  * Ancillary services (dReg / E-dReg): saturated, ≈ NT$0/MWh late 2025 -> excluded

Engineering assumptions (not researched - edit as needed):
  round-trip 88 % (C&I incl. auxiliaries), 90 % usable discharge per cycle,
  O&M 1.5 %/yr of gross capex, capacity fade 2 %/yr, cycle life 6000,
  project life 15 yr, discount rate 6 %, 248 working days/yr (106 summer),
  demand shave 333 kW (2 MWh spread over the 6 h peak).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = Path(__file__).resolve().parent / "taiwan_pilot_output"
NTD_PER_USD = 32.0

SYSTEM = {
    "power_kw": 1000.0,
    "energy_kwh": 2000.0,
    "capex_ntd_per_kwh": 12_500.0,
    "subsidy_ntd_per_kwh": 5_000.0,
    "round_trip_eff": 0.88,
    "usable_fraction": 0.90,
    "om_frac_per_year": 0.015,
    "fade_per_year": 0.02,
    "cycle_life": 6000,
    "life_years": 15,
    "discount_rate": 0.06,
    "summer_workdays": 106,
    "nonsummer_workdays": 142,
    "demand_shave_kw": 333.0,
}

TARIFFS = {
    "2023 tariff": {
        "summer_peak": 5.80, "summer_semi": 3.63, "summer_off": 1.58,
        "nonsummer_high": 3.40, "nonsummer_off": 1.45, "nonsummer_cycles": 2,
    },
    "Current (Oct 2025)": {
        "summer_peak": 9.39, "summer_semi": 5.85, "summer_off": 2.53,
        "nonsummer_high": 5.47, "nonsummer_off": 2.32, "nonsummer_cycles": 2,
    },
    "Storage TOU (proposed)": {
        "summer_peak": 10.2, "summer_semi": 6.0, "summer_off": 2.61,
        "nonsummer_high": 9.9, "nonsummer_off": 2.39, "nonsummer_cycles": 1,
    },
}

# Effective demand-charge saving per shaved kW-month:
#   low  = shift from 經常契約 to 半尖峰契約 (223.6 - 166.9)
#   high = factory's max demand occurs in the 16-22 peak (full 223.6)
DEMAND_SAVING = {"low": 223.6 - 166.9, "high": 223.6}


def cycle_margin(sell_price, buy_price, system):
    """Net NT$ per kWh of nameplate per cycle, before wear."""
    discharged = system["usable_fraction"]
    charged = discharged / system["round_trip_eff"]
    return discharged * sell_price - charged * buy_price


def annual_operation(tariff, system, wear_ntd_per_kwh_discharged):
    """Choose cycles that beat battery wear; return revenue and cycles per kWh nameplate."""
    usable = system["usable_fraction"]
    wear_per_cycle = wear_ntd_per_kwh_discharged * usable

    options = [
        ("summer: off-peak -> peak", cycle_margin(tariff["summer_peak"], tariff["summer_off"], system),
         system["summer_workdays"]),
        ("summer: semi-peak -> peak (2nd cycle)",
         cycle_margin(tariff["summer_peak"], tariff["summer_semi"], system), system["summer_workdays"]),
    ]
    for index in range(tariff["nonsummer_cycles"]):
        options.append((
            f"non-summer cycle {index + 1}",
            cycle_margin(tariff["nonsummer_high"], tariff["nonsummer_off"], system),
            system["nonsummer_workdays"],
        ))

    revenue = 0.0
    cycles = 0
    used = []
    for name, margin, days in options:
        if margin > wear_per_cycle:
            revenue += margin * days
            cycles += days
            used.append({"cycle": name, "margin_ntd_per_kwh_cap": round(margin, 2), "days": days})
    return revenue, cycles, used


def project_cashflows(tariff_name, subsidy, demand_case, system=SYSTEM):
    tariff = TARIFFS[tariff_name]
    energy = system["energy_kwh"]
    gross_capex = system["capex_ntd_per_kwh"] * energy
    subsidy_ntd = min(system["subsidy_ntd_per_kwh"] * energy, 0.5 * gross_capex) if subsidy else 0.0
    net_capex = gross_capex - subsidy_ntd

    wear = (net_capex / energy) / (system["cycle_life"] * system["usable_fraction"])
    energy_revenue_per_kwh, cycles_per_year, used = annual_operation(tariff, system, wear)

    demand_saving_year = 0.0
    if demand_case:
        demand_saving_year = system["demand_shave_kw"] * DEMAND_SAVING[demand_case] * 12

    om = system["om_frac_per_year"] * gross_capex
    cashflows = [-net_capex]
    lifetime_cycles = 0
    for year in range(1, system["life_years"] + 1):
        health = (1 - system["fade_per_year"]) ** (year - 1)
        lifetime_cycles += cycles_per_year
        flow = energy_revenue_per_kwh * energy * health + demand_saving_year * health - om
        if lifetime_cycles > system["cycle_life"] and lifetime_cycles - cycles_per_year <= system["cycle_life"]:
            flow -= 0.25 * gross_capex * 0.6          # augmentation at ~60 % of today's price
        cashflows.append(flow)

    cashflows = np.array(cashflows)
    discount = (1 + system["discount_rate"]) ** -np.arange(len(cashflows))
    npv = float((cashflows * discount).sum())
    cumulative = np.cumsum(cashflows)
    payback = next((year for year, value in enumerate(cumulative) if value >= 0), None)

    irr = None
    low, high = -0.5, 1.0
    if (cashflows.sum()) > 0:
        for _ in range(200):
            mid = (low + high) / 2
            value = (cashflows / (1 + mid) ** np.arange(len(cashflows))).sum()
            if value > 0:
                low = mid
            else:
                high = mid
        irr = mid

    return {
        "tariff": tariff_name,
        "subsidy": subsidy,
        "demand_saving_case": demand_case or "none",
        "net_capex_ntd_m": net_capex / 1e6,
        "wear_ntd_per_kwh": round(wear, 2),
        "cycles_per_year": cycles_per_year,
        "year1_energy_revenue_ntd_m": energy_revenue_per_kwh * energy / 1e6,
        "year1_demand_saving_ntd_m": demand_saving_year / 1e6,
        "om_ntd_m": om / 1e6,
        "simple_payback_years": payback,
        "npv_ntd_m": npv / 1e6,
        "irr_pct": None if irr is None else 100 * irr,
        "cycles_used": used,
        "cumulative": cumulative.tolist(),
    }


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    scenarios = []
    for tariff_name in TARIFFS:
        for subsidy in (False, True):
            for demand_case in (None, "low", "high"):
                scenarios.append(project_cashflows(tariff_name, subsidy, demand_case))

    report = {
        "system": SYSTEM,
        "fx_ntd_per_usd": NTD_PER_USD,
        "scenarios": [{k: v for k, v in s.items() if k != "cumulative"} for s in scenarios],
    }
    (OUTPUT_DIR / "taiwan_pilot_results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    colors = {"2023 tariff": "gray", "Current (Oct 2025)": "tab:blue", "Storage TOU (proposed)": "tab:green"}
    for s in scenarios:
        if s["demand_saving_case"] != "low":
            continue
        style = "-" if s["subsidy"] else "--"
        label = f"{s['tariff']} - {'with' if s['subsidy'] else 'no'} subsidy"
        ax.plot(np.array(s["cumulative"]) / 1e6, style, color=colors[s["tariff"]], label=label, lw=2)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative cash flow (NT$ million)")
    ax.set_title("1 MW / 2 MWh factory battery - cumulative cash flow\n(low demand-saving case)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1]
    labels = []
    irr_values = []
    bar_colors = []
    for s in scenarios:
        if s["demand_saving_case"] != "low":
            continue
        labels.append(f"{s['tariff']}\n{'subsidy' if s['subsidy'] else 'no subsidy'}")
        irr_values.append(s["irr_pct"] if s["irr_pct"] is not None else -5)
        bar_colors.append(colors[s["tariff"]])
    ax.barh(labels, irr_values, color=bar_colors)
    ax.axvline(SYSTEM["discount_rate"] * 100, color="red", ls="--", label="6 % hurdle")
    ax.set_xlabel("Project IRR %")
    ax.set_title("Project IRR by tariff and subsidy")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "taiwan_pilot.png", dpi=130)
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
