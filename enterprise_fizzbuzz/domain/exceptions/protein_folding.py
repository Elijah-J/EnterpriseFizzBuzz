"""
Enterprise FizzBuzz Platform - FizzFold Protein Folding Exceptions (EFP-PF00 through EFP-PF02)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzFoldError(FizzBuzzError):
    """Base exception for the FizzFold protein folding subsystem.

    Protein structure prediction is a computationally intensive process
    that can fail for a variety of reasons: invalid amino acid sequences,
    energy function singularities, convergence failures, or insufficient
    Monte Carlo steps. This hierarchy classifies each failure mode to
    enable targeted recovery strategies at the middleware level.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-PF00"),
            context=kwargs.get("context", {}),
        )


class FizzFoldSequenceError(FizzFoldError):
    """Raised when an amino acid sequence contains unrecognized residues.

    The IUPAC single-letter code table defines 20 standard amino acids
    plus several ambiguity codes. Characters outside this table cannot
    be mapped to biophysical properties and therefore cannot participate
    in the energy function. This exception is raised during sequence
    validation, before any Monte Carlo steps are attempted.
    """

    def __init__(self, invalid_residue: str) -> None:
        super().__init__(
            f"Unrecognized amino acid code: '{invalid_residue}'. "
            f"Valid codes for FizzFold: F, I, Z, B, U, A, G, L, V, P.",
            error_code="EFP-PF01",
            context={"invalid_residue": invalid_residue},
        )
        self.invalid_residue = invalid_residue


class FizzFoldConvergenceError(FizzFoldError):
    """Raised when simulated annealing fails to reach a stable conformation.

    If the energy at the end of the annealing schedule remains above the
    convergence threshold, the folding simulation is considered to have
    failed. This may indicate an insufficient number of Monte Carlo steps,
    an overly aggressive cooling schedule, or a sequence that resists
    compact folding due to charge repulsion.
    """

    def __init__(self, sequence: str, final_energy: float, steps: int) -> None:
        super().__init__(
            f"Folding of '{sequence}' did not converge after {steps} MC steps. "
            f"Final energy: {final_energy:.3f} kcal/mol. Consider increasing "
            f"--fold-steps or adjusting the cooling schedule.",
            error_code="EFP-PF02",
            context={
                "sequence": sequence,
                "final_energy": final_energy,
                "steps": steps,
            },
        )
        self.sequence = sequence
        self.final_energy = final_energy
        self.steps = steps


class RayTracerError(FizzBuzzError):
    """Base exception for all FizzTrace ray tracing subsystem errors.

    The physically-based rendering pipeline involves numerous mathematical
    operations — quadratic solvers, trigonometric functions, recursive ray
    bouncing — each of which can fail under degenerate conditions. This
    hierarchy classifies each failure mode to enable targeted diagnostics
    at the rendering middleware level.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-RT00"),
            context=kwargs.get("context", {}),
        )


class RayTracerSceneError(RayTracerError):
    """Raised when the scene configuration is invalid or degenerate.

    A scene must contain at least one object for rendering to produce
    meaningful output. An empty scene results in a pure background
    image, which, while technically correct, does not convey any
    FizzBuzz classification information and therefore fails to meet
    the minimum viable rendering threshold.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Scene configuration error: {reason}",
            error_code="EFP-RT01",
            context={"reason": reason},
        )


class RayTracerConvergenceError(RayTracerError):
    """Raised when the path tracer fails to converge within the maximum depth.

    If every sample ray reaches the maximum bounce depth without escaping
    to the background or being terminated by Russian Roulette, the image
    may contain significant bias. This condition is monitored but not
    typically fatal — the rendering equation is being approximated, after all.
    """

    def __init__(self, max_depth: int, samples: int) -> None:
        super().__init__(
            f"Path tracer reached maximum depth {max_depth} on all {samples} samples. "
            f"Consider increasing max_depth or reducing scene complexity.",
            error_code="EFP-RT02",
            context={"max_depth": max_depth, "samples": samples},
        )

