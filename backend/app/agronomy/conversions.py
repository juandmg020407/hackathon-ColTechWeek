"""Explicit adapters for nutrient conventions.

The engine never silently accepts oxide grades. Callers must name that basis
and use this adapter before values enter the elemental core.
"""

from __future__ import annotations

from ..domain.errors import IncompatibleNPKBasis
from ..domain.models import NPKPercent

# Stoichiometric elemental mass fractions. They are conversion constants, not
# crop assumptions: P/P2O5 and K/K2O respectively.
P_FROM_P2O5 = 0.4364
K_FROM_K2O = 0.8301


def oxide_grade_to_elemental(
    *,
    N_pct: float,
    P2O5_pct: float,
    K2O_pct: float,
    basis: str,
) -> NPKPercent:
    if basis != "fertilizer_oxide_mass_pct":
        raise IncompatibleNPKBasis(
            "la conversión de óxidos exige basis='fertilizer_oxide_mass_pct'"
        )
    return NPKPercent(
        N=N_pct,
        P=P2O5_pct * P_FROM_P2O5,
        K=K2O_pct * K_FROM_K2O,
        basis="elemental_mass_pct",
    )


def require_elemental_basis(basis: str) -> None:
    if basis != "elemental_mass_pct":
        raise IncompatibleNPKBasis(
            f"el núcleo solo acepta elemental_mass_pct y recibió {basis!r}; "
            "use un adaptador explícito"
        )
