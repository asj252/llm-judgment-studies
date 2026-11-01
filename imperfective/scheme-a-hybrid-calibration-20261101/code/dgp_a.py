"""Finite joint populations and DGP for Scheme A Step 5b (m=4 confirmatory family).

Preserves 100% population table and SHA256 fingerprint parity with P16.4.5 (`scheme-a-calibration-20261031`).
Truth is enumerated 100% from support points and rational weights (truth_calibration_error == 0.0),
never manually assigned. Includes exact 4x4 covariance calculation, minimum positive support gap,
adverse missingness pooled normalization, and empirical convex mixture attenuation.
"""

from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from .core_a import NAMES_A
    from .inputs import ClusterSampleA
except (ImportError, ValueError):
    import sys
    from pathlib import Path
    _code_dir = Path(__file__).resolve().parent
    if str(_code_dir) not in sys.path:
        sys.path.insert(0, str(_code_dir))
    from core_a import NAMES_A
    from inputs import ClusterSampleA


def to_fraction(val: Any) -> Fraction:
    """Convert any float/int/str/Fraction to exact Fraction."""
    if isinstance(val, Fraction):
        return val
    return Fraction(str(val))


@dataclass
class StratumAC:
    """AC stratum support points and rational weights."""
    scores: List[List[List[Fraction]]]
    weights: List[Fraction]

    def __post_init__(self):
        w_sum = sum(self.weights)
        if w_sum != Fraction(1):
            raise ValueError(f"StratumAC weights must sum to 1, got {w_sum}")

    @cached_property
    def numeric(self) -> Tuple[np.ndarray, np.ndarray]:
        arr_scores = np.array([[[float(v) for v in role] for role in row] for row in self.scores], dtype=np.float64)
        arr_weights = np.array([float(w) for w in self.weights], dtype=np.float64)
        return arr_scores, arr_weights


@dataclass
class StratumBD:
    """BD stratum support points and rational weights."""
    cont_scores: List[List[List[Fraction]]]
    l_acc_scores: List[List[Fraction]]
    weights: List[Fraction]

    def __post_init__(self):
        w_sum = sum(self.weights)
        if w_sum != Fraction(1):
            raise ValueError(f"StratumBD weights must sum to 1, got {w_sum}")

    @cached_property
    def numeric(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        arr_cont = np.array([[[float(v) for v in role] for role in row] for row in self.cont_scores], dtype=np.float64)
        arr_l_acc = np.array([[float(v) for v in row] for row in self.l_acc_scores], dtype=np.float64)
        arr_weights = np.array([float(w) for w in self.weights], dtype=np.float64)
        return arr_cont, arr_l_acc, arr_weights


@dataclass
class PopulationA:
    """Finite joint population for Scheme A."""
    name: str
    stratum_ac: StratumAC
    stratum_bd: StratumBD
    metadata: dict

    def truth(self) -> Tuple[Fraction, Fraction, Fraction, Fraction]:
        """Compute exact 4-dimensional truth purely from support points and rational weights."""
        theta1 = Fraction(0)
        for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights):
            c_pcot = row[1][0]
            c_muz = row[1][1]
            i_pcot = Fraction(1) if c_pcot >= Fraction(95) else Fraction(0)
            i_muz = Fraction(1) if c_muz >= Fraction(95) else Fraction(0)
            theta1 += w * (i_pcot - i_muz)

        theta2 = Fraction(0)
        for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights):
            a_pcot, a_muz = row[0][0], row[0][1]
            c_pcot, c_muz = row[1][0], row[1][1]
            contrast = (c_pcot - a_pcot) - (c_muz - a_muz)
            theta2 += w * contrast

        theta3 = Fraction(0)
        for row, w in zip(self.stratum_bd.cont_scores, self.stratum_bd.weights):
            b_mucot, b_pcot = row[0][0], row[0][1]
            d_mucot, d_pcot = row[1][0], row[1][1]
            contrast = (d_mucot - b_mucot) - (d_pcot - b_pcot)
            theta3 += w * contrast

        theta4 = Fraction(0)
        for row, w in zip(self.stratum_bd.l_acc_scores, self.stratum_bd.weights):
            acc_lcot, acc_lz = row[0], row[1]
            theta4 += w * (acc_lcot - acc_lz)

        return (theta1, theta2, theta3, theta4)

    def min_positive_support_gap(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Compute the minimum positive difference between support contrast values for each slot."""
        v1_set = set()
        for row in self.stratum_ac.scores:
            c_pcot, c_muz = row[1][0], row[1][1]
            i1 = Fraction(1) if c_pcot >= Fraction(95) else Fraction(0)
            i2 = Fraction(1) if c_muz >= Fraction(95) else Fraction(0)
            v1_set.add(i1 - i2)
        v1_sorted = sorted(list(v1_set))
        g1 = min((b - a for a, b in zip(v1_sorted, v1_sorted[1:])), default=None)

        v2_set = set()
        for row in self.stratum_ac.scores:
            a_pcot, a_muz = row[0][0], row[0][1]
            c_pcot, c_muz = row[1][0], row[1][1]
            v2_set.add((c_pcot - a_pcot) - (c_muz - a_muz))
        v2_sorted = sorted(list(v2_set))
        g2 = min((b - a for a, b in zip(v2_sorted, v2_sorted[1:])), default=None)

        v3_set = set()
        for row in self.stratum_bd.cont_scores:
            b_mucot, b_pcot = row[0][0], row[0][1]
            d_mucot, d_pcot = row[1][0], row[1][1]
            v3_set.add((d_mucot - b_mucot) - (d_pcot - b_pcot))
        v3_sorted = sorted(list(v3_set))
        g3 = min((b - a for a, b in zip(v3_sorted, v3_sorted[1:])), default=None)

        v4_set = set()
        for row in self.stratum_bd.l_acc_scores:
            v4_set.add(row[0] - row[1])
        v4_sorted = sorted(list(v4_set))
        g4 = min((b - a for a, b in zip(v4_sorted, v4_sorted[1:])), default=None)

        def fmt_gap(g):
            if g is None:
                return None
            return {"fraction": str(g), "float": float(g)}

        return {
            "SA1": fmt_gap(g1),
            "SA2": fmt_gap(g2),
            "SA3": fmt_gap(g3),
            "SA4": fmt_gap(g4),
        }

    def population_covariance_4x4(self) -> Dict[str, Any]:
        """Compute exact 4x4 population variance-covariance matrix."""
        t1, t2, t3, t4 = self.truth()

        var1 = Fraction(0)
        var2 = Fraction(0)
        cov12 = Fraction(0)
        for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights):
            c_pcot, c_muz = row[1][0], row[1][1]
            a_pcot, a_muz = row[0][0], row[0][1]
            i1 = Fraction(1) if c_pcot >= Fraction(95) else Fraction(0)
            i2 = Fraction(1) if c_muz >= Fraction(95) else Fraction(0)
            v1 = i1 - i2
            v2 = (c_pcot - a_pcot) - (c_muz - a_muz)
            var1 += w * (v1 - t1) ** 2
            var2 += w * (v2 - t2) ** 2
            cov12 += w * (v1 - t1) * (v2 - t2)

        var3 = Fraction(0)
        var4 = Fraction(0)
        cov34 = Fraction(0)
        for r_cont, r_l, w in zip(self.stratum_bd.cont_scores, self.stratum_bd.l_acc_scores, self.stratum_bd.weights):
            b_mucot, b_pcot = r_cont[0][0], r_cont[0][1]
            d_mucot, d_pcot = r_cont[1][0], r_cont[1][1]
            v3 = (d_mucot - b_mucot) - (d_pcot - b_pcot)
            v4 = r_l[0] - r_l[1]
            var3 += w * (v3 - t3) ** 2
            var4 += w * (v4 - t4) ** 2
            cov34 += w * (v3 - t3) * (v4 - t4)

        z = Fraction(0)
        cov_matrix_frac = [
            [var1, cov12, z, z],
            [cov12, var2, z, z],
            [z, z, var3, cov34],
            [z, z, cov34, var4]
        ]

        cov_matrix_float = [[float(v) for v in row] for row in cov_matrix_frac]
        cov_matrix_str = [[str(v) for v in row] for row in cov_matrix_frac]

        return {
            "fractions": cov_matrix_str,
            "floats": cov_matrix_float,
        }

    def compute_adverse_normalizers(self) -> Dict[str, Any]:
        """Compute exact per-condition adverse missingness normalizers pooled equally over participating roles."""
        w_a_pcot = sum(w * (Fraction(1) + (Fraction(1) if row[0][0] >= Fraction(95) else Fraction(0)))
                       for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights))
        w_c_pcot = sum(w * (Fraction(1) + (Fraction(1) if row[1][0] >= Fraction(95) else Fraction(0)))
                       for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights))
        w_a_muz = sum(w * (Fraction(1) + (Fraction(1) if row[0][1] >= Fraction(95) else Fraction(0)))
                      for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights))
        w_c_muz = sum(w * (Fraction(1) + (Fraction(1) if row[1][1] >= Fraction(95) else Fraction(0)))
                      for row, w in zip(self.stratum_ac.scores, self.stratum_ac.weights))

        w_b_mucot = sum(w * (Fraction(1) + (Fraction(1) if row[0][0] >= Fraction(95) else Fraction(0)))
                        for row, w in zip(self.stratum_bd.cont_scores, self.stratum_bd.weights))
        w_d_mucot = sum(w * (Fraction(1) + (Fraction(1) if row[1][0] >= Fraction(95) else Fraction(0)))
                        for row, w in zip(self.stratum_bd.cont_scores, self.stratum_bd.weights))
        w_b_pcot = sum(w * (Fraction(1) + (Fraction(1) if row[0][1] >= Fraction(95) else Fraction(0)))
                       for row, w in zip(self.stratum_bd.cont_scores, self.stratum_bd.weights))
        w_d_pcot = sum(w * (Fraction(1) + (Fraction(1) if row[1][1] >= Fraction(95) else Fraction(0)))
                       for row, w in zip(self.stratum_bd.cont_scores, self.stratum_bd.weights))

        w_d_lcot = sum(w * (Fraction(1) + (Fraction(1) if row[0] == Fraction(1) else Fraction(0)))
                       for row, w in zip(self.stratum_bd.l_acc_scores, self.stratum_bd.weights))
        w_d_lz = sum(w * (Fraction(1) + (Fraction(1) if row[1] == Fraction(1) else Fraction(0)))
                     for row, w in zip(self.stratum_bd.l_acc_scores, self.stratum_bd.weights))

        return {
            "P_CoT": (w_a_pcot + w_c_pcot + w_b_pcot + w_d_pcot) / Fraction(4),
            "MU_Z": (w_a_muz + w_c_muz) / Fraction(2),
            "MU_CoT": (w_b_mucot + w_d_mucot) / Fraction(2),
            "L_CoT": w_d_lcot,
            "L_Z": w_d_lz,
            "_role_weights": {
                "A_P_CoT": w_a_pcot,
                "C_P_CoT": w_c_pcot,
                "B_P_CoT": w_b_pcot,
                "D_P_CoT": w_d_pcot,
                "A_MU_Z": w_a_muz,
                "C_MU_Z": w_c_muz,
                "B_MU_CoT": w_b_mucot,
                "D_MU_CoT": w_d_mucot,
                "D_L_CoT": w_d_lcot,
                "D_L_Z": w_d_lz,
            },
        }

    def expected_missing_rates(
        self,
        missing: str = "none",
        missing_rate: Fraction = Fraction(0)
    ) -> Dict[str, Any]:
        """Compute exact rational expected missingness rates per condition and role."""
        r = to_fraction(missing_rate)
        role_keys = [
            "A_P_CoT", "C_P_CoT", "B_P_CoT", "D_P_CoT",
            "A_MU_Z", "C_MU_Z",
            "B_MU_CoT", "D_MU_CoT",
            "D_L_CoT", "D_L_Z",
        ]
        if missing == "none" or r == Fraction(0):
            return {
                "mechanism": missing,
                "target_rate": "0",
                "by_role_channel": {k: "0" for k in role_keys},
                "pooled_by_condition": {
                    c: "0" for c in ("P_CoT", "MU_Z", "MU_CoT", "L_CoT", "L_Z")
                },
            }
        if missing == "mcar":
            if r < Fraction(0) or r > Fraction(1):
                raise ValueError(f"Invalid MCAR missing_rate: {r}")
            return {
                "mechanism": "mcar",
                "target_rate": str(r),
                "by_role_channel": {k: str(r) for k in role_keys},
                "pooled_by_condition": {
                    c: str(r) for c in ("P_CoT", "MU_Z", "MU_CoT", "L_CoT", "L_Z")
                },
            }
        if missing != "adverse":
            raise ValueError(f"Unknown missing mechanism: {missing}")

        norms = self.compute_adverse_normalizers()
        rw = norms["_role_weights"]
        cond_map = {
            "A_P_CoT": "P_CoT", "C_P_CoT": "P_CoT", "B_P_CoT": "P_CoT", "D_P_CoT": "P_CoT",
            "A_MU_Z": "MU_Z", "C_MU_Z": "MU_Z",
            "B_MU_CoT": "MU_CoT", "D_MU_CoT": "MU_CoT",
            "D_L_CoT": "L_CoT",
            "D_L_Z": "L_Z",
        }
        for cond in ("P_CoT", "MU_Z", "MU_CoT", "L_CoT", "L_Z"):
            max_possible_p = (Fraction(2) * r) / norms[cond]
            if max_possible_p > Fraction(1):
                raise ValueError(
                    f"Adverse missingness probability {max_possible_p} exceeds 1 for {cond} at r={r}"
                )

        by_role = {k: r * rw[k] / norms[cond_map[k]] for k in role_keys}
        pooled = {
            "P_CoT": (by_role["A_P_CoT"] + by_role["C_P_CoT"] + by_role["B_P_CoT"] + by_role["D_P_CoT"]) / Fraction(4),
            "MU_Z": (by_role["A_MU_Z"] + by_role["C_MU_Z"]) / Fraction(2),
            "MU_CoT": (by_role["B_MU_CoT"] + by_role["D_MU_CoT"]) / Fraction(2),
            "L_CoT": by_role["D_L_CoT"],
            "L_Z": by_role["D_L_Z"],
        }
        for cond, p_val in pooled.items():
            if p_val != r:
                raise AssertionError(f"Adverse pooled rate mismatch on {cond}: got {p_val}, expected {r}")

        return {
            "mechanism": "adverse",
            "target_rate": str(r),
            "normalizers": {c: str(norms[c]) for c in ("P_CoT", "MU_Z", "MU_CoT", "L_CoT", "L_Z")},
            "by_role_channel": {k: str(v) for k, v in by_role.items()},
            "by_role_channel_float": {k: float(v) for k, v in by_role.items()},
            "pooled_by_condition": {k: str(v) for k, v in pooled.items()},
        }

    def sample(
        self,
        rng: np.random.Generator,
        n_ac: int = 80,
        n_bd: int = 80,
        missing: str = "none",
        missing_rate: Fraction = Fraction(1, 50)
    ) -> ClusterSampleA:
        """Sample n_ac and n_bd clusters from the population and apply missingness."""
        ac_scores, ac_weights = self.stratum_ac.numeric
        bd_cont, bd_l_acc, bd_weights = self.stratum_bd.numeric

        idx_ac = rng.choice(len(ac_weights), size=n_ac, p=ac_weights)
        idx_bd = rng.choice(len(bd_weights), size=n_bd, p=bd_weights)

        ac_latent = ac_scores[idx_ac]
        bd_cont_latent = bd_cont[idx_bd]
        bd_l_latent = bd_l_acc[idx_bd]

        ac_cont_lo = ac_latent.copy()
        ac_cont_hi = ac_latent.copy()
        bd_cont_lo = bd_cont_latent.copy()
        bd_cont_hi = bd_cont_latent.copy()
        bd_l_lo = bd_l_latent.copy()
        bd_l_hi = bd_l_latent.copy()

        r_f = float(missing_rate)

        if missing == "mcar":
            mask_ac = rng.random(ac_latent.shape) < r_f
            mask_bd_cont = rng.random(bd_cont_latent.shape) < r_f
            mask_bd_l = rng.random(bd_l_latent.shape) < r_f

            ac_cont_lo[mask_ac] = 0.0
            ac_cont_hi[mask_ac] = 100.0
            bd_cont_lo[mask_bd_cont] = 0.0
            bd_cont_hi[mask_bd_cont] = 100.0
            bd_l_lo[mask_bd_l] = 0.0
            bd_l_hi[mask_bd_l] = 1.0

        elif missing == "adverse":
            norms = self.compute_adverse_normalizers()
            z_pcot = float(norms["P_CoT"])
            z_muz = float(norms["MU_Z"])
            z_mucot = float(norms["MU_CoT"])
            z_lcot = float(norms["L_CoT"])
            z_lz = float(norms["L_Z"])

            z_ac = np.array([z_pcot, z_muz], dtype=np.float64)[None, None, :]
            z_bd_cont = np.array([z_mucot, z_pcot], dtype=np.float64)[None, None, :]
            z_bd_l = np.array([z_lcot, z_lz], dtype=np.float64)[None, :]

            prob_ac = r_f * (1.0 + (ac_latent >= 95.0).astype(float)) / z_ac
            prob_bd_cont = r_f * (1.0 + (bd_cont_latent >= 95.0).astype(float)) / z_bd_cont
            prob_bd_l = r_f * (1.0 + (bd_l_latent == 1.0).astype(float)) / z_bd_l

            if np.any(prob_ac > 1.0) or np.any(prob_bd_cont > 1.0) or np.any(prob_bd_l > 1.0):
                raise ValueError("Adverse missingness probability exceeded 1.0")

            mask_ac = rng.random(ac_latent.shape) < prob_ac
            mask_bd_cont = rng.random(bd_cont_latent.shape) < prob_bd_cont
            mask_bd_l = rng.random(bd_l_latent.shape) < prob_bd_l

            ac_cont_lo[mask_ac] = 0.0
            ac_cont_hi[mask_ac] = 100.0
            bd_cont_lo[mask_bd_cont] = 0.0
            bd_cont_hi[mask_bd_cont] = 100.0
            bd_l_lo[mask_bd_l] = 0.0
            bd_l_hi[mask_bd_l] = 1.0

        elif missing != "none":
            raise ValueError(f"Unknown missing mechanism: {missing}")

        if np.any(ac_cont_lo > ac_latent) or np.any(ac_cont_hi < ac_latent):
            raise ValueError("AC latent score outside observed interval")
        if np.any(bd_cont_lo > bd_cont_latent) or np.any(bd_cont_hi < bd_cont_latent):
            raise ValueError("BD continuous latent score outside observed interval")
        if np.any(bd_l_lo > bd_l_latent) or np.any(bd_l_hi < bd_l_latent):
            raise ValueError("BD discrete L latent accuracy outside observed interval")

        return ClusterSampleA(
            ac_cont_lower=ac_cont_lo,
            ac_cont_upper=ac_cont_hi,
            bd_cont_lower=bd_cont_lo,
            bd_cont_upper=bd_cont_hi,
            bd_l_acc_lower=bd_l_lo,
            bd_l_acc_upper=bd_l_hi,
        )

    def table(self) -> dict:
        """Convert population to JSON-serializable dictionary."""
        truth_tuple = self.truth()
        truth_dict = {name: str(val) for name, val in zip(NAMES_A, truth_tuple)}
        gap_dict = self.min_positive_support_gap()
        cov_dict = self.population_covariance_4x4()

        ac_dict = {
            "weights": [str(w) for w in self.stratum_ac.weights],
            "scores": [[[str(v) for v in role] for role in row] for row in self.stratum_ac.scores],
        }
        bd_dict = {
            "weights": [str(w) for w in self.stratum_bd.weights],
            "cont_scores": [[[str(v) for v in role] for role in row] for row in self.stratum_bd.cont_scores],
            "l_acc_scores": [[str(v) for v in row] for row in self.stratum_bd.l_acc_scores],
        }

        return {
            "name": self.name,
            "metadata": self.metadata,
            "truth": truth_dict,
            "min_positive_support_gap": gap_dict,
            "population_covariance_4x4": cov_dict,
            "stratum_ac": ac_dict,
            "stratum_bd": bd_dict,
        }

    def fingerprint(self) -> str:
        """Compute SHA256 canonical hash of the population table."""
        tbl = self.table()
        ser = json.dumps(tbl, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(ser.encode("utf-8")).hexdigest()


def from_table(table: dict) -> PopulationA:
    """Reconstruct PopulationA from dictionary table."""
    ac_data = table["stratum_ac"]
    ac_weights = [Fraction(w) for w in ac_data["weights"]]
    ac_scores = [[[Fraction(v) for v in role] for role in row] for row in ac_data["scores"]]
    stratum_ac = StratumAC(scores=ac_scores, weights=ac_weights)

    bd_data = table["stratum_bd"]
    bd_weights = [Fraction(w) for w in bd_data["weights"]]
    bd_cont = [[[Fraction(v) for v in role] for role in row] for row in bd_data["cont_scores"]]
    bd_l = [[Fraction(v) for v in row] for row in bd_data["l_acc_scores"]]
    stratum_bd = StratumBD(cont_scores=bd_cont, l_acc_scores=bd_l, weights=bd_weights)

    return PopulationA(
        name=table["name"],
        stratum_ac=stratum_ac,
        stratum_bd=stratum_bd,
        metadata=table.get("metadata", {}),
    )


def _dist(values: List[Any], probabilities: List[Any]) -> List[Tuple[Fraction, Fraction]]:
    """Helper to construct discrete probability distribution."""
    frac_vals = [to_fraction(v) for v in values]
    frac_probs = [to_fraction(p) for p in probabilities]
    if any(p < 0 for p in frac_probs) or sum(frac_probs) != Fraction(1):
        raise ValueError(f"Infeasible probability distribution: {frac_probs}")
    return [(v, p) for v, p in zip(frac_vals, frac_probs) if p > Fraction(0)]


def _finite_joint_ac(
    a_dists: List[List[Tuple[Fraction, Fraction]]],
    c_dists: List[List[Tuple[Fraction, Fraction]]]
) -> StratumAC:
    """Generate StratumAC using rotating-quantile support with coprime phases."""
    group_indices = [0, 2]
    dists_by_role = [a_dists, c_dists]

    points = {Fraction(0), Fraction(1)}
    phases = [[Fraction((7 * j + 11 * g) % 97, 97) for j in range(2)] for g in group_indices]

    for role in range(2):
        for j, dist in enumerate(dists_by_role[role]):
            phi = phases[role][j]
            points.add((-phi) % 1)
            total = Fraction(0)
            for _, p in dist[:-1]:
                total += p
                points.add((total - phi) % 1)

    sorted_points = sorted(points)
    scores = []
    weights = []

    for a, b in zip(sorted_points, sorted_points[1:]):
        u = (a + b) / 2
        row = []
        for role in range(2):
            vector = []
            for j, dist in enumerate(dists_by_role[role]):
                coord = (u + phases[role][j]) % 1
                total = Fraction(0)
                for val, p in dist:
                    total += p
                    if coord < total:
                        vector.append(val)
                        break
                else:
                    raise AssertionError("Quantile coordinate lookup failed")
            row.append(vector)
        scores.append(row)
        weights.append(b - a)

    return StratumAC(scores=scores, weights=weights)


def _finite_joint_bd(
    b_cont_dists: List[List[Tuple[Fraction, Fraction]]],
    d_cont_dists: List[List[Tuple[Fraction, Fraction]]],
    d_l_dists: List[List[Tuple[Fraction, Fraction]]]
) -> StratumBD:
    """Generate StratumBD using rotating-quantile support with coprime phases."""
    points = {Fraction(0), Fraction(1)}

    phases_b = [Fraction((7 * j + 11 * 1) % 97, 97) for j in range(2)]
    phases_d = [Fraction((7 * j + 11 * 3) % 97, 97) for j in range(4)]

    for j, dist in enumerate(b_cont_dists):
        phi = phases_b[j]
        points.add((-phi) % 1)
        tot = Fraction(0)
        for _, p in dist[:-1]:
            tot += p
            points.add((tot - phi) % 1)

    for j, dist in enumerate(d_cont_dists):
        phi = phases_d[j]
        points.add((-phi) % 1)
        tot = Fraction(0)
        for _, p in dist[:-1]:
            tot += p
            points.add((tot - phi) % 1)

    for j, dist in enumerate(d_l_dists):
        phi = phases_d[j + 2]
        points.add((-phi) % 1)
        tot = Fraction(0)
        for _, p in dist[:-1]:
            tot += p
            points.add((tot - phi) % 1)

    sorted_points = sorted(points)
    cont_scores = []
    l_acc_scores = []
    weights = []

    for a, b in zip(sorted_points, sorted_points[1:]):
        u = (a + b) / 2

        vec_b = []
        for j, dist in enumerate(b_cont_dists):
            coord = (u + phases_b[j]) % 1
            tot = Fraction(0)
            for val, p in dist:
                tot += p
                if coord < tot:
                    vec_b.append(val)
                    break
            else:
                raise AssertionError("Quantile coordinate lookup failed")

        vec_d = []
        for j, dist in enumerate(d_cont_dists):
            coord = (u + phases_d[j]) % 1
            tot = Fraction(0)
            for val, p in dist:
                tot += p
                if coord < tot:
                    vec_d.append(val)
                    break
            else:
                raise AssertionError("Quantile coordinate lookup failed")

        vec_d_l = []
        for j, dist in enumerate(d_l_dists):
            coord = (u + phases_d[j + 2]) % 1
            tot = Fraction(0)
            for val, p in dist:
                tot += p
                if coord < tot:
                    vec_d_l.append(val)
                    break
            else:
                raise AssertionError("Quantile coordinate lookup failed")

        cont_scores.append([vec_b, vec_d])
        l_acc_scores.append(vec_d_l)
        weights.append(b - a)

    return StratumBD(cont_scores=cont_scores, l_acc_scores=l_acc_scores, weights=weights)


def make_synthetic_population(
    name: str,
    shape: str = "regular",
    effects: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    explicit_infeasible_combinations: Optional[List[dict]] = None
) -> PopulationA:
    """Create a synthetic rotating-quantile PopulationA with certified Fraction truth."""
    eff = effects or {}
    theta1 = to_fraction(eff.get("SA1", 0))
    theta2 = to_fraction(eff.get("SA2", 0))
    theta3 = to_fraction(eff.get("SA3", 0))
    theta4 = to_fraction(eff.get("SA4", 0))

    req_truth = (theta1, theta2, theta3, theta4)

    if shape == "regular":
        base_ac = (Fraction(1, 5), Fraction(2, 5), Fraction(2, 5))
        base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
        base_l_acc = Fraction(1, 2)
    elif shape == "power-SA1-base":
        base_ac = (Fraction(1, 2), Fraction(2, 5), Fraction(1, 10))
        base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
        base_l_acc = Fraction(1, 2)
    elif shape == "power-SA4-base":
        base_ac = (Fraction(1, 5), Fraction(2, 5), Fraction(2, 5))
        base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
        base_l_acc = Fraction(17, 20)
    elif shape == "skew":
        base_ac = (Fraction(17, 20), Fraction(1, 10), Fraction(1, 20))
        base_bd = (Fraction(17, 20), Fraction(1, 10), Fraction(1, 20))
        base_l_acc = Fraction(1, 10)
    elif shape == "rare":
        base_ac = (Fraction(99, 100), Fraction(0), Fraction(1, 100))
        base_bd = (Fraction(1, 100), Fraction(0), Fraction(99, 100))
        base_l_acc = Fraction(1, 100)
    elif shape == "ties":
        base_ac = (Fraction(19, 40), Fraction(1, 20), Fraction(19, 40))
        base_bd = (Fraction(19, 40), Fraction(1, 20), Fraction(19, 40))
        base_l_acc = Fraction(1, 2)
    elif shape == "sparse-endpoint":
        base_ac = (Fraction(19, 20), Fraction(0), Fraction(1, 20))
        base_bd = (Fraction(19, 20), Fraction(0), Fraction(1, 20))
        base_l_acc = Fraction(19, 20)
    elif shape in ("bimodal", "bimodal-polarized"):
        base_ac = (Fraction(1, 2), Fraction(0), Fraction(1, 2))
        base_bd = (Fraction(1, 2), Fraction(0), Fraction(1, 2))
        base_l_acc = Fraction(1, 2)
    elif shape.startswith("pinned-"):
        if shape == "pinned-SA1-devlike":
            base_ac = (Fraction(4, 5), Fraction(1, 5), Fraction(0))
            base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
            base_l_acc = Fraction(1, 2)
        elif shape == "pinned-SA1-shrunken":
            base_ac = (Fraction(7, 8), Fraction(1, 8), Fraction(0))
            base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
            base_l_acc = Fraction(1, 2)
        elif shape == "pinned-SA4-devlike":
            base_ac = (Fraction(1, 5), Fraction(2, 5), Fraction(2, 5))
            base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
            base_l_acc = Fraction(1)
        elif shape == "pinned-SA4-moderate-ceiling":
            base_ac = (Fraction(1, 5), Fraction(2, 5), Fraction(2, 5))
            base_bd = (Fraction(1, 4), Fraction(1, 2), Fraction(1, 4))
            base_l_acc = Fraction(19, 20)
        else:
            raise ValueError(f"Unknown pinned shape: {shape}")
    else:
        raise ValueError(f"Unknown distribution shape: {shape}")

    muz_high = base_ac[2]
    pcot_high = muz_high + theta1
    if pcot_high < Fraction(0) or pcot_high > Fraction(1):
        err_msg = f"Infeasible SA1 effect {theta1} for shape {shape}: requires P/CoT high rate {pcot_high} outside [0, 1]"
        if explicit_infeasible_combinations is not None:
            explicit_infeasible_combinations.append({
                "shape": shape, "effects": eff, "reason": err_msg
            })
        raise ValueError(err_msg)

    lz_acc = base_l_acc
    lcot_acc = lz_acc + theta4
    if lcot_acc < Fraction(0) or lcot_acc > Fraction(1):
        err_msg = f"Infeasible SA4 effect {theta4} for shape {shape}: requires L/CoT accuracy {lcot_acc} outside [0, 1]"
        if explicit_infeasible_combinations is not None:
            explicit_infeasible_combinations.append({
                "shape": shape, "effects": eff, "reason": err_msg
            })
        raise ValueError(err_msg)

    if shape == "rare":
        dist_c_muz = _dist([94, 95], [Fraction(99, 100), Fraction(1, 100)])
        dist_c_pcot = _dist([94, 95], [Fraction(1) - pcot_high, pcot_high])
        dist_a_muz = _dist([0, 100], [Fraction(1, 100), Fraction(99, 100)])
        mean_a_pcot = Fraction(99) + theta1 - theta2
        if mean_a_pcot < Fraction(0) or mean_a_pcot > Fraction(100):
            err_msg = f"Infeasible SA2 effect {theta2} for shape rare: requires A_PCoT {mean_a_pcot} outside [0, 100]"
            if explicit_infeasible_combinations is not None:
                explicit_infeasible_combinations.append({
                    "shape": shape, "effects": eff, "reason": err_msg
                })
            raise ValueError(err_msg)
        dist_a_pcot = _dist([mean_a_pcot], [1])
        stratum_ac = _finite_joint_ac(
            a_dists=[dist_a_pcot, dist_a_muz],
            c_dists=[dist_c_pcot, dist_c_muz],
        )

        mean_b_pcot = Fraction(50) + theta3
        if mean_b_pcot < Fraction(0) or mean_b_pcot > Fraction(100):
            err_msg = f"Infeasible SA3 effect {theta3} for shape rare: requires B_PCoT {mean_b_pcot} outside [0, 100]"
            if explicit_infeasible_combinations is not None:
                explicit_infeasible_combinations.append({
                    "shape": shape, "effects": eff, "reason": err_msg
                })
            raise ValueError(err_msg)
        dist_d_mucot = _dist([0, 100], [Fraction(1, 100), Fraction(99, 100)])
        dist_b_mucot = _dist([99], [1])
        dist_d_pcot = _dist([50], [1])
        dist_b_pcot = _dist([mean_b_pcot], [1])
        dist_lz = _dist([0, 1], [Fraction(1) - lz_acc, lz_acc])
        dist_lcot = _dist([0, 1], [Fraction(1) - lcot_acc, lcot_acc])
        stratum_bd = _finite_joint_bd(
            b_cont_dists=[dist_b_mucot, dist_b_pcot],
            d_cont_dists=[dist_d_mucot, dist_d_pcot],
            d_l_dists=[dist_lcot, dist_lz],
        )
    else:
        p_muz_0, p_muz_50, p_muz_100 = base_ac
        dist_c_muz = _dist([0, 50, 100], [p_muz_0, p_muz_50, p_muz_100])
        mean_c_muz = Fraction(50) * p_muz_50 + Fraction(100) * p_muz_100

        rem_c = Fraction(1) - pcot_high
        if rem_c >= base_ac[1]:
            p_c_50 = base_ac[1]
            p_c_0 = rem_c - p_c_50
        else:
            p_c_50 = rem_c
            p_c_0 = Fraction(0)
        dist_c_pcot = _dist([0, 50, 100], [p_c_0, p_c_50, pcot_high])
        mean_c_pcot = Fraction(50) * p_c_50 + Fraction(100) * pcot_high

        delta_a = theta2 - (mean_c_pcot - mean_c_muz)
        if delta_a < Fraction(-100) or delta_a > Fraction(100):
            err_msg = f"Infeasible SA2 effect {theta2} for shape {shape}: requires delta_A {delta_a} outside [-100, 100]"
            if explicit_infeasible_combinations is not None:
                explicit_infeasible_combinations.append({
                    "shape": shape, "effects": eff, "reason": err_msg
                })
            raise ValueError(err_msg)

        if Fraction(0) <= mean_c_muz - delta_a <= Fraction(100):
            dist_a_muz = dist_c_muz
            mean_a_pcot = mean_c_muz - delta_a
        elif delta_a >= Fraction(0):
            pad = min(Fraction(5), (Fraction(100) - delta_a) / Fraction(2))
            mean_a_pcot = pad
            mean_a_muz = pad + delta_a
            p_am_100 = mean_a_muz / Fraction(100)
            dist_a_muz = _dist([0, 100], [Fraction(1) - p_am_100, p_am_100])
        else:
            pad = min(Fraction(5), (Fraction(100) + delta_a) / Fraction(2))
            mean_a_muz = pad
            mean_a_pcot = pad - delta_a
            p_am_100 = mean_a_muz / Fraction(100)
            dist_a_muz = _dist([0, 100], [Fraction(1) - p_am_100, p_am_100])

        p_a_100 = mean_a_pcot / Fraction(100)
        p_a_0 = Fraction(1) - p_a_100
        dist_a_pcot = _dist([0, 100], [p_a_0, p_a_100])

        stratum_ac = _finite_joint_ac(
            a_dists=[dist_a_pcot, dist_a_muz],
            c_dists=[dist_c_pcot, dist_c_muz]
        )

        p_b_cont_0, p_b_cont_50, p_b_cont_100 = base_bd
        dist_d_pcot = _dist([0, 50, 100], [p_b_cont_0, p_b_cont_50, p_b_cont_100])
        mean_d_pcot = Fraction(50) * p_b_cont_50 + Fraction(100) * p_b_cont_100

        dist_d_mucot = dist_d_pcot
        mean_d_mucot = mean_d_pcot

        if theta3 < Fraction(-100) or theta3 > Fraction(100):
            err_msg = f"Infeasible SA3 effect {theta3} for shape {shape}: requires delta_B {theta3} outside [-100, 100]"
            if explicit_infeasible_combinations is not None:
                explicit_infeasible_combinations.append({
                    "shape": shape, "effects": eff, "reason": err_msg
                })
            raise ValueError(err_msg)

        if Fraction(0) <= mean_d_mucot - theta3 <= Fraction(100):
            dist_b_pcot = dist_d_pcot
            mean_b_mucot = mean_d_mucot - theta3
        elif theta3 >= Fraction(0):
            pad = min(Fraction(5), (Fraction(100) - theta3) / Fraction(2))
            mean_b_mucot = pad
            mean_b_pcot = pad + theta3
            p_bp_100 = mean_b_pcot / Fraction(100)
            dist_b_pcot = _dist([0, 100], [Fraction(1) - p_bp_100, p_bp_100])
        else:
            pad = min(Fraction(5), (Fraction(100) + theta3) / Fraction(2))
            mean_b_pcot = pad
            mean_b_mucot = pad - theta3
            p_bp_100 = mean_b_pcot / Fraction(100)
            dist_b_pcot = _dist([0, 100], [Fraction(1) - p_bp_100, p_bp_100])

        p_b_100 = mean_b_mucot / Fraction(100)
        p_b_0 = Fraction(1) - p_b_100
        dist_b_mucot = _dist([0, 100], [p_b_0, p_b_100])

        dist_lz = _dist([0, 1], [Fraction(1) - lz_acc, lz_acc])
        dist_lcot = _dist([0, 1], [Fraction(1) - lcot_acc, lcot_acc])

        stratum_bd = _finite_joint_bd(
            b_cont_dists=[dist_b_mucot, dist_b_pcot],
            d_cont_dists=[dist_d_mucot, dist_d_pcot],
            d_l_dists=[dist_lcot, dist_lz]
        )

    meta = metadata or {}
    meta_full = {
        **meta,
        "shape": shape,
        "requested_effects": {name: str(val) for name, val in zip(NAMES_A, req_truth)},
        "construction": "rational rotating-quantile finite joint support",
    }

    pop = PopulationA(
        name=name,
        stratum_ac=stratum_ac,
        stratum_bd=stratum_bd,
        metadata=meta_full,
    )

    actual_truth = pop.truth()
    if actual_truth != req_truth:
        raise ValueError(f"Truth calibration error != 0.0 in {name}: actual={actual_truth} vs requested={req_truth}")

    return pop


def make_empirical_population(
    name: str,
    rational_data: dict,
    gamma: Fraction = Fraction(1),
    metadata: Optional[Dict[str, Any]] = None
) -> PopulationA:
    """Construct empirical convex mixture attenuation population."""
    gamma = to_fraction(gamma)
    if gamma < Fraction(0) or gamma > Fraction(1):
        raise ValueError(f"gamma must be in [0, 1], got {gamma}")

    ac_frac = rational_data["ac_cont_frac"]
    bd_cont_frac = rational_data["bd_cont_frac"]
    bd_l_frac = rational_data["bd_l_acc_frac"]

    ac_scores = []
    ac_weights = []
    w_orig_ac = (Fraction(1) + gamma) / Fraction(40)
    w_swap_ac = (Fraction(1) - gamma) / Fraction(40)

    for i in range(len(ac_frac)):
        a_row = ac_frac[i][0]
        c_row = ac_frac[i][1]

        orig_row = [[a_row[0], a_row[1]], [c_row[0], c_row[1]]]
        if w_orig_ac > Fraction(0):
            ac_scores.append(orig_row)
            ac_weights.append(w_orig_ac)

        swap_row = [[a_row[1], a_row[0]], [c_row[1], c_row[0]]]
        if w_swap_ac > Fraction(0):
            ac_scores.append(swap_row)
            ac_weights.append(w_swap_ac)

    stratum_ac = StratumAC(scores=ac_scores, weights=ac_weights)

    bd_cont_scores = []
    bd_l_scores = []
    bd_weights = []

    w_orig_bd = (Fraction(1) + Fraction(3) * gamma) / Fraction(80)
    w_swap_bd = (Fraction(1) - gamma) / Fraction(80)

    for i in range(len(bd_cont_frac)):
        b_c = bd_cont_frac[i][0]
        d_c = bd_cont_frac[i][1]
        d_l = bd_l_frac[i]

        combos = [
            ([[b_c[0], b_c[1]], [d_c[0], d_c[1]]], [d_l[0], d_l[1]], w_orig_bd),
            ([[b_c[1], b_c[0]], [d_c[1], d_c[0]]], [d_l[0], d_l[1]], w_swap_bd),
            ([[b_c[0], b_c[1]], [d_c[0], d_c[1]]], [d_l[1], d_l[0]], w_swap_bd),
            ([[b_c[1], b_c[0]], [d_c[1], d_c[0]]], [d_l[1], d_l[0]], w_swap_bd),
        ]

        for c_row, l_row, w in combos:
            if w > Fraction(0):
                bd_cont_scores.append(c_row)
                bd_l_scores.append(l_row)
                bd_weights.append(w)

    stratum_bd = StratumBD(cont_scores=bd_cont_scores, l_acc_scores=bd_l_scores, weights=bd_weights)

    meta = metadata or {}
    meta_full = {
        **meta,
        "gamma": str(gamma),
        "construction": "empirical condition-swapping convex mixture attenuation",
        "description": f"Empirical population attenuated by gamma={gamma} using condition swapping",
    }

    return PopulationA(
        name=name,
        stratum_ac=stratum_ac,
        stratum_bd=stratum_bd,
        metadata=meta_full,
    )
