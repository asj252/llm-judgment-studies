"""Per-item missing-value substitutions from PLAN v0.5 section 5.3.

Each argument is None (whole missing cell) or a dict of observed a/b/conj/disj
percentage values, with absent/None entries missing. S uses only b and conj;
J treats any missing statement as a whole missing cell. No coherence
constraints are imposed on model answers. Bounds preserve all observed values.
"""
import math

from prompts_d import STATEMENTS


def _delta_interval(cell, joint=False):
    cell = {} if cell is None else cell
    for s in STATEMENTS:
        v = cell.get(s)
        if v is not None and (not math.isfinite(v) or not 0 <= v <= 100):
            raise ValueError("Observed probabilities must be finite and in [0, 100]")
    if joint and any(cell.get(s) is None for s in STATEMENTS):
        cell = {}
    b, conj = cell.get("b"), cell.get("conj")
    low = (0 if conj is None else conj) - (100 if b is None else b)
    high = (100 if conj is None else conj) - (0 if b is None else b)
    return low, high


def d1(s_direct):
    """Conservative value of Delta_S,direct (positive direction)."""
    return _delta_interval(s_direct)[0]


def d2(s_direct, j_direct):
    """Conservative Delta_S,direct - Delta_J,direct (positive direction)."""
    return _delta_interval(s_direct)[0] - _delta_interval(j_direct, joint=True)[1]


def d3(s_multi, s_direct):
    """Feasible (lower, upper) for Delta_S,multi - Delta_S,direct."""
    ml, mh = _delta_interval(s_multi)
    dl, dh = _delta_interval(s_direct)
    return ml - dh, mh - dl


def d4(j_multi, j_direct):
    """Feasible (lower, upper) for Delta_J,multi - Delta_J,direct."""
    ml, mh = _delta_interval(j_multi, joint=True)
    dl, dh = _delta_interval(j_direct, joint=True)
    return ml - dh, mh - dl
