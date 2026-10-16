"""Shared building blocks for the CS2 Part 6 calculators.

Every calculator is a pure function: same inputs -> same output, no file or
network access. Each result is a Calc that carries:
  - calc_id: a stable id built from the formula and its input ids, so the same
    calculation always gets the same id (needed for replay and for citations);
  - inputs:  the (role, fact_id/calc_id) pairs it was computed from, which is
    the click-through trace Rachel asked for;
  - tier:    the weakest tier among its inputs (CS2 Section 5: a derived value
    "inherits the lowest tier of its inputs"). Tiers are numbered 1 = most
    reliable ... 6 = least, so the weakest tier is the HIGHEST number.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class FactRef:
    """The minimum a calculator needs from one fact-store row."""
    fact_id: str
    value: float
    tier: int
    unit: str = "USD"


@dataclass(frozen=True)
class Calc:
    """One calculator output, with its trace."""
    calc_id: str
    name: str
    value: float | None          # None means "n.m." (not meaningful)
    unit: str
    tier: int
    inputs: tuple[tuple[str, str], ...]   # ((role, id), ...)
    formula: str
    note: str = ""


Operand = Union[FactRef, Calc]


def ref_id(op: Operand) -> str:
    """The id a trace points to: a fact_id for facts, a calc_id for calcs."""
    return op.fact_id if isinstance(op, FactRef) else op.calc_id


def make_calc(name: str, value: float | None, unit: str,
              inputs: dict[str, Operand], formula: str, note: str = "") -> Calc:
    """Build a Calc with a deterministic calc_id and an inherited tier."""
    if not inputs:
        raise ValueError(f"{name}: a calculation needs at least one input")
    pairs = tuple(sorted((role, ref_id(op)) for role, op in inputs.items()))
    payload = json.dumps({"name": name, "formula": formula, "inputs": pairs},
                         sort_keys=True)
    calc_id = "calc-" + hashlib.sha256(payload.encode()).hexdigest()[:12]
    tier = max(op.tier for op in inputs.values())
    return Calc(calc_id, name, value, unit, tier, pairs, formula, note)
