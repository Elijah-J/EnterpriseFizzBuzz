"""
Enterprise FizzBuzz Platform - FizzChemistry Exceptions (EFP-CHM00 through EFP-CHM09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzChemistryError(FizzBuzzError):
    """Base exception for the FizzChemistry molecular dynamics subsystem.

    The FizzChemistry engine models chemical reactions and molecular
    properties to provide a rigorous physicochemical context for FizzBuzz
    evaluations. Molecular dynamics simulations, electron configuration
    calculations, and reaction balancing each involve complex numerical
    procedures that can fail under specific conditions.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CHM00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ElementNotFoundError(FizzChemistryError):
    """Raised when an element symbol is not found in the periodic table.

    The periodic table contains 118 confirmed elements. Symbols outside
    this set cannot be resolved to atomic properties and therefore
    cannot participate in molecular simulations.
    """

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"Element symbol '{symbol}' not found in the periodic table",
            error_code="EFP-CHM01",
            context={"symbol": symbol},
        )


class ReactionBalanceError(FizzChemistryError):
    """Raised when a chemical reaction cannot be balanced.

    Conservation of mass requires that the number of atoms of each
    element is equal on both sides of a chemical equation. If the
    system of linear equations is singular or has no non-negative
    integer solution, the reaction cannot be balanced.
    """

    def __init__(self, equation: str, reason: str) -> None:
        super().__init__(
            f"Cannot balance reaction '{equation}': {reason}",
            error_code="EFP-CHM02",
            context={"equation": equation, "reason": reason},
        )


class ElectronConfigurationError(FizzChemistryError):
    """Raised when electron shell configuration is invalid.

    Electron configurations must obey the Pauli exclusion principle,
    the Aufbau principle, and Hund's rule. A configuration that
    violates these quantum mechanical constraints is non-physical.
    """

    def __init__(self, atomic_number: int, reason: str) -> None:
        super().__init__(
            f"Invalid electron configuration for Z={atomic_number}: {reason}",
            error_code="EFP-CHM03",
            context={"atomic_number": atomic_number, "reason": reason},
        )


class MolecularBondError(FizzChemistryError):
    """Raised when a molecular bond specification is invalid.

    Bond orders must be positive integers (or 1.5 for aromatic bonds).
    Bonds between atoms that exceed their maximum valence are chemically
    impossible.
    """

    def __init__(self, atom1: str, atom2: str, bond_order: float, reason: str) -> None:
        super().__init__(
            f"Invalid bond {atom1}-{atom2} (order={bond_order}): {reason}",
            error_code="EFP-CHM04",
            context={
                "atom1": atom1,
                "atom2": atom2,
                "bond_order": bond_order,
                "reason": reason,
            },
        )


class VSEPRGeometryError(FizzChemistryError):
    """Raised when VSEPR geometry prediction fails.

    The Valence Shell Electron Pair Repulsion model predicts molecular
    geometry from the number of bonding and lone pairs. Configurations
    with more than six electron domains require extended models not
    currently supported by the FizzChemistry engine.
    """

    def __init__(self, central_atom: str, electron_domains: int, reason: str) -> None:
        super().__init__(
            f"VSEPR geometry error for atom '{central_atom}' with "
            f"{electron_domains} electron domains: {reason}",
            error_code="EFP-CHM05",
            context={
                "central_atom": central_atom,
                "electron_domains": electron_domains,
                "reason": reason,
            },
        )


class EnthalpyError(FizzChemistryError):
    """Raised when enthalpy calculation produces non-physical results.

    Standard enthalpy of formation values are defined at 298.15 K and
    1 atm. Reactions with missing thermodynamic data cannot have their
    enthalpy computed from first principles without additional input.
    """

    def __init__(self, reaction: str, reason: str) -> None:
        super().__init__(
            f"Enthalpy calculation failed for '{reaction}': {reason}",
            error_code="EFP-CHM06",
            context={"reaction": reaction, "reason": reason},
        )


class ChemistryMiddlewareError(FizzChemistryError):
    """Raised when the FizzChemistry middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzChemistry middleware error: {reason}",
            error_code="EFP-CHM07",
            context={"reason": reason},
        )
