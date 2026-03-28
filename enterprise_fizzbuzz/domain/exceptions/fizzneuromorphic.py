"""
Enterprise FizzBuzz Platform - Neuromorphic Computing Exceptions (EFP-NM00 through EFP-NM09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class NeuromorphicComputingError(FizzBuzzError):
    """Base exception for all FizzNeuromorphic computing subsystem errors.

    Neuromorphic computing emulates biological neural circuits using
    spiking neural networks for energy-efficient FizzBuzz evaluation.
    When the neuromorphic pipeline fails, the platform loses its
    brain-inspired inference capability and must rely on conventional
    Von Neumann computation for divisibility checking.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NM00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class NeuronModelError(NeuromorphicComputingError):
    """Raised when a neuron model has invalid parameters.

    The leaky integrate-and-fire (LIF) neuron model requires valid
    membrane time constant, threshold voltage, and reset potential.
    Invalid parameters produce biologically implausible dynamics
    that cannot reliably classify FizzBuzz inputs.
    """

    def __init__(self, neuron_id: str, parameter: str, value: float, reason: str) -> None:
        super().__init__(
            f"Neuron '{neuron_id}' has invalid parameter '{parameter}' = {value}: {reason}",
            error_code="EFP-NM01",
            context={"neuron_id": neuron_id, "parameter": parameter, "value": value},
        )


class SynapticWeightError(NeuromorphicComputingError):
    """Raised when a synaptic weight exceeds the representable range.

    Synaptic weights in neuromorphic hardware are stored with fixed-point
    precision. Weights that overflow this range cannot be faithfully
    represented and will produce incorrect post-synaptic currents.
    """

    def __init__(self, pre_id: str, post_id: str, weight: float, max_weight: float) -> None:
        super().__init__(
            f"Synapse {pre_id}->{post_id} weight {weight:.4f} exceeds maximum {max_weight:.4f}.",
            error_code="EFP-NM02",
            context={"pre_id": pre_id, "post_id": post_id, "weight": weight},
        )


class STDPConvergenceError(NeuromorphicComputingError):
    """Raised when spike-timing-dependent plasticity fails to converge.

    STDP updates synaptic weights based on the relative timing of pre-
    and post-synaptic spikes. If the learning rate is too high or the
    weight bounds are too loose, STDP can oscillate without converging,
    leaving the network unable to learn the FizzBuzz classification task.
    """

    def __init__(self, epoch: int, weight_delta: float) -> None:
        super().__init__(
            f"STDP failed to converge after {epoch} epochs "
            f"(weight delta still {weight_delta:.6f}).",
            error_code="EFP-NM03",
            context={"epoch": epoch, "weight_delta": weight_delta},
        )


class SpikeTimingError(NeuromorphicComputingError):
    """Raised when spike timestamps are out of order or negative.

    The event-driven simulation engine processes spikes in chronological
    order. Out-of-order or negative timestamps violate causality and
    produce undefined network behavior.
    """

    def __init__(self, neuron_id: str, timestamp: float) -> None:
        super().__init__(
            f"Invalid spike timestamp {timestamp:.6f} ms for neuron '{neuron_id}'.",
            error_code="EFP-NM04",
            context={"neuron_id": neuron_id, "timestamp": timestamp},
        )


class NetworkTopologyError(NeuromorphicComputingError):
    """Raised when the spiking neural network topology is invalid.

    The network must have at least one input layer and one output layer,
    and all neurons must be reachable from the input layer through
    synaptic connections. Disconnected neurons waste hardware resources
    and indicate a topology specification error.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Invalid neuromorphic network topology: {reason}",
            error_code="EFP-NM05",
            context={"reason": reason},
        )
