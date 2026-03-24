"""
Enterprise FizzBuzz Platform - FizzProof — Proof Certificate Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ProofCertificateError(FizzBuzzError):
    """Base exception for the FizzProof proof certificate subsystem.

    The proof certificate engine constructs machine-checkable proofs
    in the Calculus of Constructions for every FizzBuzz classification.
    When proof construction, verification, or export encounters an
    error, the appropriate subclass of this exception is raised.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PF00"),
            context=kwargs.pop("context", {}),
        )


class ProofTermError(ProofCertificateError):
    """Raised when a proof term is structurally malformed.

    This indicates a bug in the CertificateGenerator: it produced
    a term that violates the syntactic invariants of the Calculus
    of Constructions — for example, a negative de Bruijn index
    after substitution, or a lambda without a body. The trusted
    kernel refuses to examine such terms.
    """

    def __init__(self, message: str, *, term_repr: str = "") -> None:
        self.term_repr = term_repr
        super().__init__(
            f"Malformed proof term: {message}",
            error_code="EFP-PF01",
            context={"term_repr": term_repr},
        )


class ProofCheckError(ProofCertificateError):
    """Raised when the trusted proof checker rejects a proof term.

    This is the most significant error in the FizzProof subsystem:
    it means the proof term does not type-check under the rules of
    the Calculus of Constructions. Either the proposition is false,
    or (more likely) the CertificateGenerator constructed an
    incorrect proof. In either case, no certificate is issued.
    """

    def __init__(self, message: str, *, step: str = "") -> None:
        self.step = step
        super().__init__(
            f"Proof check failed at '{step}': {message}",
            error_code="EFP-PF02",
            context={"step": step},
        )


class CertificateExportError(ProofCertificateError):
    """Raised when LaTeX export of a proof certificate fails.

    The LaTeX exporter encountered an error while rendering the
    proof certificate as a LaTeX document. This could indicate
    an encoding issue, a missing template component, or a proof
    term that cannot be pretty-printed.
    """

    def __init__(self, message: str, *, certificate_id: str = "") -> None:
        self.certificate_id = certificate_id
        super().__init__(
            f"Certificate export failed: {message}",
            error_code="EFP-PF03",
            context={"certificate_id": certificate_id},
        )

