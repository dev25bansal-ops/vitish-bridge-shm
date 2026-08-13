"""
fusion/bhi.py — BridgeHealthIndex: transparent, auditable 3-sub-index fusion.

Wraps the FROZEN contract formula from backend/app/contract.py:
    BHI = 100 * (1 - 0.40*cv - 0.35*vib - 0.25*load) * age_factor * traffic_factor
    GREEN >= 70, AMBER in [50, 70), RED < 50

The contract is imported verbatim when reachable (`backend.app.contract`); if
it is not importable the exact formula is replicated locally so this module is
fully standalone. Sub-indices are clamped to [0,1]; BHI is clamped to [0,100].

The uncertainty `u` returned is a +/- BHI-point interval (0..20 points) mapped
from the 0..1 model uncertainty, so the dashboard can draw an honest error bar.

demo() feeds a scripted 5-stage damage scenario and prints the BHI trajectory
starting at 87 (GREEN) down through AMBER to RED — the demo storyline.
"""
from __future__ import annotations

import sys
from pathlib import Path

# -- prefer the frozen contract; replicate exactly if unreachable -------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from backend.app.contract import (  # noqa: F401
        compute_bhi, state_for, BHI_W, BHI_GREEN, BHI_AMBER,
    )
    _CONTRACT_SOURCE = "imported backend.app.contract"
except Exception:  # pragma: no cover - fallback, keep exact copy of the formula
    _CONTRACT_SOURCE = "replicated (backend.app.contract not importable)"

    def compute_bhi(cv: float, vib: float, load: float, w=None,
                    age_factor: float = 1.0, traffic_factor: float = 1.0) -> float:
        w = w or {"cv": 0.40, "vib": 0.35, "load": 0.25}
        cv = max(0.0, min(1.0, cv))
        vib = max(0.0, min(1.0, vib))
        load = max(0.0, min(1.0, load))
        penalty = w["cv"] * cv + w["vib"] * vib + w["load"] * load
        bhi = 100.0 * (1.0 - penalty) * age_factor * traffic_factor
        return round(max(0.0, min(100.0, bhi)), 1)

    def state_for(bhi: float) -> str:
        if bhi >= 70.0:
            return "GREEN"
        if bhi >= 50.0:
            return "AMBER"
        return "RED"

    BHI_W = {"cv": 0.40, "vib": 0.35, "load": 0.25}
    BHI_GREEN = 70.0
    BHI_AMBER = 50.0


class BridgeHealthIndex:
    """Auditable BHI fusion. update() is the only call the backend needs."""

    def __init__(self, w=None, age_factor: float = 1.0, traffic_factor: float = 1.0,
                 unc_to_points: float = 20.0) -> None:
        self.w = dict(w) if w else dict(BHI_W)
        self.age_factor = float(age_factor)
        self.traffic_factor = float(traffic_factor)
        self.unc_to_points = float(unc_to_points)  # 0..1 uncertainty -> +/- BHI pts
        self.history: list[dict] = []

    def update(self, cv_score: float, vib_score: float, load: float,
               uncertainty: float = 0.0) -> dict:
        """Fuse sub-indices -> contract BHI message.

        Args:
            cv_score:   computer-vision evidence in [0,1] (higher = worse)
            vib_score:  vibration anomaly evidence in [0,1]
            load:       traffic/load factor in [0,1]
            uncertainty: model uncertainty in [0,1] (mapped to +/- BHI points)
        """
        bhi = compute_bhi(cv_score, vib_score, load, w=self.w,
                          age_factor=self.age_factor, traffic_factor=self.traffic_factor)
        unc = float(uncertainty)
        unc = max(0.0, min(1.0, unc))
        u_pts = round(unc * self.unc_to_points, 1)
        msg = {
            "bhi": bhi,
            "u": u_pts,
            "cv": round(max(0.0, min(1.0, float(cv_score))), 3),
            "vib": round(max(0.0, min(1.0, float(vib_score))), 3),
            "load": round(max(0.0, min(1.0, float(load))), 3),
            "state": state_for(bhi),
        }
        self.history.append(msg)
        return msg

    @property
    def contract_source(self) -> str:
        return _CONTRACT_SOURCE

    @property
    def weights(self) -> dict[str, float]:
        return dict(self.w)


def demo() -> None:
    """Scripted scenario: 87 (GREEN) -> RED. Prints the auditable trajectory."""
    bhi = BridgeHealthIndex()
    scenario = [
        ("Baseline healthy", 0.22, 0.12, 0.00, 0.15),
        ("Early warning",    0.30, 0.20, 0.10, 0.20),
        ("Damage onset",     0.45, 0.35, 0.20, 0.25),
        ("Significant",      0.65, 0.55, 0.30, 0.35),
        ("Critical",         0.90, 0.85, 0.40, 0.45),
    ]
    print(f"BHI demo (formula: {_CONTRACT_SOURCE}) weights={bhi.weights}")
    print(f"{'stage':<20}{'cv':>6}{'vib':>6}{'load':>6}{'unc':>6}  {'BHI':>6}  {'state':>6}")
    for name, cv, vib, ld, unc in scenario:
        msg = bhi.update(cv, vib, ld, unc)
        print(f"{name:<20}{cv:>6.2f}{vib:>6.2f}{ld:>6.2f}{unc:>6.2f}  "
              f"{msg['bhi']:>6.1f}  {msg['state']:>6}")
    states = [m["state"] for m in bhi.history]
    assert abs(bhi.history[0]["bhi"] - 87.0) < 1e-6, bhi.history[0]["bhi"]
    assert states == ["GREEN", "GREEN", "AMBER", "RED", "RED"], states
    print("BHI demo PASS: trajectory 87.0 GREEN -> AMBER -> RED")


if __name__ == "__main__":
    demo()
