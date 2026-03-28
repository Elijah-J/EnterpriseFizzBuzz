"""
Enterprise FizzBuzz Platform - FizzPaleontology Exceptions (EFP-PAL00 through EFP-PAL07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzPaleontologyError(FizzBuzzError):
    """Base exception for the FizzPaleontology fossil record analysis subsystem.

    Paleontological analysis involves taxonomic classification of fossil
    specimens, extinction event detection from stratigraphic data,
    phylogenetic tree inference, and morphometric measurement analysis.
    Each analytical stage can encounter incomplete or contradictory data
    requiring precise exception classification.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PAL00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TaxonomicError(FizzPaleontologyError):
    """Raised when taxonomic classification fails due to insufficient characters.

    Fossil specimens may lack diagnostic features needed to resolve
    classification below a certain taxonomic rank. A specimen missing
    both dental and postcranial material, for example, may only be
    classifiable to the order level.
    """

    def __init__(self, specimen_id: str, rank: str, reason: str) -> None:
        super().__init__(
            f"Taxonomic classification of specimen '{specimen_id}' failed at "
            f"rank {rank}: {reason}",
            error_code="EFP-PAL01",
            context={"specimen_id": specimen_id, "rank": rank, "reason": reason},
        )


class ExtinctionEventError(FizzPaleontologyError):
    """Raised when extinction event detection produces statistically insignificant results.

    Extinction events are identified by statistically significant drops
    in taxonomic diversity across stratigraphic boundaries. If the
    diversity change falls within the background extinction rate, no
    event can be confidently declared.
    """

    def __init__(self, boundary: str, diversity_drop: float, threshold: float) -> None:
        super().__init__(
            f"Extinction event at {boundary} boundary inconclusive: diversity drop "
            f"{diversity_drop:.1f}% below threshold {threshold:.1f}%",
            error_code="EFP-PAL02",
            context={
                "boundary": boundary,
                "diversity_drop": diversity_drop,
                "threshold": threshold,
            },
        )


class PhylogeneticError(FizzPaleontologyError):
    """Raised when phylogenetic inference produces ambiguous or contradictory trees.

    Maximum parsimony and likelihood methods can yield multiple equally
    optimal trees when the character matrix contains insufficient
    phylogenetic signal or excessive homoplasy.
    """

    def __init__(self, num_taxa: int, num_trees: int, reason: str) -> None:
        super().__init__(
            f"Phylogenetic inference for {num_taxa} taxa yielded {num_trees} "
            f"equally parsimonious trees: {reason}",
            error_code="EFP-PAL03",
            context={
                "num_taxa": num_taxa,
                "num_trees": num_trees,
                "reason": reason,
            },
        )


class BiostratigraphyError(FizzPaleontologyError):
    """Raised when biostratigraphic correlation fails across sections.

    Biostratigraphy relies on the first and last appearance datums of
    index fossils. When index taxa are absent from one or more sections,
    correlation becomes impossible without additional chronostratigraphic
    constraints.
    """

    def __init__(self, section_id: str, missing_taxon: str) -> None:
        super().__init__(
            f"Biostratigraphic correlation failed in section '{section_id}': "
            f"index taxon '{missing_taxon}' not found",
            error_code="EFP-PAL04",
            context={"section_id": section_id, "missing_taxon": missing_taxon},
        )


class MorphometricError(FizzPaleontologyError):
    """Raised when morphometric analysis produces statistically invalid results.

    Morphometric analysis requires a minimum sample size and assumes
    normally distributed measurements. Degenerate principal components
    or singular covariance matrices indicate insufficient data.
    """

    def __init__(self, measurement: str, sample_size: int, reason: str) -> None:
        super().__init__(
            f"Morphometric analysis of '{measurement}' failed with "
            f"n={sample_size}: {reason}",
            error_code="EFP-PAL05",
            context={
                "measurement": measurement,
                "sample_size": sample_size,
                "reason": reason,
            },
        )


class StratigraphicAgeError(FizzPaleontologyError):
    """Raised when stratigraphic age determination yields contradictory results."""

    def __init__(self, layer_id: str, age_mya: float, reason: str) -> None:
        super().__init__(
            f"Age determination for layer '{layer_id}' ({age_mya:.1f} Ma) "
            f"is inconsistent: {reason}",
            error_code="EFP-PAL06",
            context={"layer_id": layer_id, "age_mya": age_mya, "reason": reason},
        )


class PaleontologyMiddlewareError(FizzPaleontologyError):
    """Raised when the FizzPaleontology middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzPaleontology middleware error: {reason}",
            error_code="EFP-PAL07",
            context={"reason": reason},
        )
