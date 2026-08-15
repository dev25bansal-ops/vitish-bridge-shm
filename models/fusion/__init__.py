"""fusion — auditable health fusion for VITISH SHM.

Standalone reference implementation of the weighted BHI
(``bhi.compute_bhi`` = 100*(1 - 0.40*cv - 0.35*vib - 0.25*load), rounded to 0.1)
and the regulator condition-card mapping (``condition``, NBI 0-9 + FHWA rating).
The running backend fuses via backend/app/contract.compute_bhi (single source
of truth); this package holds the standalone reference used by scripts/tests.

Module marker only — see models/cv/__init__.py for why an explicit package
matters beyond Python 3 namespace-package defaults.
"""
