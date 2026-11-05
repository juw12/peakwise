"""Regression and parity tests for the Watt Reserve Taiwan model.

Run:  python -m pytest tests      (or: python tests/test_model.py)

The browser calculator (docs/calculator/index.html#selftest) must reproduce the
same numbers as model/taiwan_pilot.py for the reference case below.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model"))

from taiwan_pilot import project_cashflows  # noqa: E402

# Reference: 1 MW / 2 MWh, current (Oct 2025) tariff, subsidy, low demand-saving case
REFERENCE = {
    "net_capex_ntd_m": 15.0,
    "cycles_per_year": 496,
    "simple_payback_years": 6,
    "irr_pct": 15.94,
    "npv_ntd_m": 9.36,
}


def test_reference_case():
    result = project_cashflows("Current (Oct 2025)", subsidy=True, demand_case="low")
    assert abs(result["net_capex_ntd_m"] - REFERENCE["net_capex_ntd_m"]) < 1e-9
    assert result["cycles_per_year"] == REFERENCE["cycles_per_year"]
    assert result["simple_payback_years"] == REFERENCE["simple_payback_years"]
    assert abs(result["irr_pct"] - REFERENCE["irr_pct"]) < 0.01
    assert abs(result["npv_ntd_m"] - REFERENCE["npv_ntd_m"]) < 0.01


def test_2023_tariff_without_subsidy_never_pays_back():
    result = project_cashflows("2023 tariff", subsidy=False, demand_case="low")
    assert result["simple_payback_years"] is None
    assert result["npv_ntd_m"] < 0


def test_subsidy_improves_every_tariff():
    for tariff in ("2023 tariff", "Current (Oct 2025)", "Storage TOU (proposed)"):
        without = project_cashflows(tariff, subsidy=False, demand_case="low")
        with_subsidy = project_cashflows(tariff, subsidy=True, demand_case="low")
        assert with_subsidy["npv_ntd_m"] > without["npv_ntd_m"]


def test_calculator_contains_same_reference():
    calculator = (Path(__file__).resolve().parents[1] / "docs" / "calculator" / "index.html").read_text(encoding="utf-8")
    assert "irrPct: 15.94" in calculator
    assert "npvM: 9.36" in calculator
    assert "value: 9.39" in calculator      # summer peak tariff
    assert "value: 12500" in calculator     # build cost NT$/kWh


if __name__ == "__main__":
    for name, function in list(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok  {name}")
