"""Operating metrics for comps: LTM, EBITDA, growth, margins (CS2 Part 6).

Definitions we commit to (the brief asks us to state them):
  - LTM = latest fiscal year + current year-to-date - prior year-to-date.
    The caller must pass YTD facts covering the SAME number of months.
  - EBITDA = operating income + depreciation & amortization (D&A).
    D&A is an add-back, so we always add its absolute value: some filers
    report it with a negative sign, and it must never REDUCE EBITDA.
  - Growth = (current - prior) / |prior|. Dividing by |prior| keeps the sign
    meaningful when the prior value was negative. prior == 0 -> n.m.
  - Margin = numerator / revenue. revenue <= 0 -> n.m.
"n.m." (not meaningful) is value=None, so it can never be averaged as zero.
"""
from __future__ import annotations

from .core import Calc, FactRef, Operand, make_calc


def _unit_of(*ops: Operand) -> str:
    """All inputs must share one unit; return it or raise."""
    units = {op.unit for op in ops}
    if len(units) != 1:
        raise ValueError(f"mixed units {sorted(units)}: refusing to combine")
    return units.pop()


def ltm(latest_fy: Operand, current_ytd: Operand, prior_ytd: Operand,
        metric: str = "revenue") -> Calc:
    unit = _unit_of(latest_fy, current_ytd, prior_ytd)
    value = latest_fy.value + current_ytd.value - prior_ytd.value
    return make_calc(
        f"ltm_{metric}", value, unit,
        {"latest_fy": latest_fy, "current_ytd": current_ytd,
         "prior_ytd": prior_ytd},
        "latest_fy + current_ytd - prior_ytd")


def ebitda(operating_income: Operand, d_and_a: Operand) -> Calc:
    unit = _unit_of(operating_income, d_and_a)
    value = operating_income.value + abs(d_and_a.value)
    return make_calc(
        "ebitda", value, unit,
        {"operating_income": operating_income, "d_and_a": d_and_a},
        "operating_income + |d_and_a|")


def growth(current: Operand, prior: Operand, metric: str = "revenue") -> Calc:
    unit = _unit_of(current, prior)
    inputs = {"current": current, "prior": prior}
    formula = "(current - prior) / |prior|"
    if prior.value == 0:
        return make_calc(f"growth_{metric}", None, "ratio", inputs, formula,
                         note="n.m.: prior period is zero")
    value = (current.value - prior.value) / abs(prior.value)
    return make_calc(f"growth_{metric}", value, "ratio", inputs, formula)


def margin(numerator: Operand, revenue: Operand, name: str) -> Calc:
    _unit_of(numerator, revenue)
    inputs = {"numerator": numerator, "revenue": revenue}
    formula = "numerator / revenue"
    if revenue.value <= 0:
        return make_calc(f"{name}_margin", None, "ratio", inputs, formula,
                         note="n.m.: revenue is zero or negative")
    return make_calc(f"{name}_margin", numerator.value / revenue.value,
                     "ratio", inputs, formula)
