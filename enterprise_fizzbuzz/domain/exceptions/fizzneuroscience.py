"""
Enterprise FizzBuzz Platform - FizzNeuroscience Exceptions (EFP-NEU00 through EFP-NEU09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzNeuroscienceError(FizzBuzzError):
    """Base exception for all FizzNeuroscience brain simulation errors.

    The FizzNeuroscience engine models biologically accurate neural circuits
    using the Hodgkin-Huxley formalism to determine whether neurons fire
    action potentials in response to FizzBuzz stimuli. Errors in membrane
    potential computation, ion channel kinetics, or synaptic transmission
    propagate through the neural circuit and compromise the integrity of
    divisibility classification.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NEU00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class MembranePotentialError(FizzNeuroscienceError):
    """Raised when the membrane potential exceeds biophysical bounds.

    The neuronal membrane potential is constrained by the Nernst equilibrium
    potentials of the constituent ion species. A potential outside the range
    [-100 mV, +60 mV] indicates a failure in the Hodgkin-Huxley integration
    and renders the action potential waveform non-physical.
    """

    def __init__(self, potential_mv: float, neuron_id: str) -> None:
        super().__init__(
            f"Membrane potential {potential_mv:.2f} mV in neuron '{neuron_id}' "
            f"exceeds biophysical bounds [-100, +60] mV",
            error_code="EFP-NEU01",
            context={"potential_mv": potential_mv, "neuron_id": neuron_id},
        )


class IonChannelError(FizzNeuroscienceError):
    """Raised when ion channel gating variables become non-physical.

    The Hodgkin-Huxley gating variables m, h, and n must remain in [0, 1]
    as they represent the probability that a single gate subunit is in its
    open configuration. Values outside this range violate the stochastic
    interpretation of channel kinetics.
    """

    def __init__(self, channel_type: str, variable: str, value: float) -> None:
        super().__init__(
            f"Ion channel '{channel_type}' gating variable '{variable}' = {value:.6f} "
            f"is outside the valid probability range [0, 1]",
            error_code="EFP-NEU02",
            context={"channel_type": channel_type, "variable": variable, "value": value},
        )


class SynapticTransmissionError(FizzNeuroscienceError):
    """Raised when synaptic transmission parameters are invalid.

    Synaptic conductance must be non-negative, and the reversal potential
    must lie within the physiological range. A negative synaptic weight
    for an excitatory synapse, or a positive reversal potential for an
    inhibitory synapse, would produce paradoxical postsynaptic currents.
    """

    def __init__(self, synapse_id: str, reason: str) -> None:
        super().__init__(
            f"Synaptic transmission error at synapse '{synapse_id}': {reason}",
            error_code="EFP-NEU03",
            context={"synapse_id": synapse_id, "reason": reason},
        )


class NeuralCircuitError(FizzNeuroscienceError):
    """Raised when the neural circuit topology is invalid.

    A neural circuit requires at least one input neuron and one output
    neuron. Disconnected components prevent signal propagation from
    FizzBuzz input encoding to classification output.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Neural circuit topology error: {reason}",
            error_code="EFP-NEU04",
            context={"reason": reason},
        )


class ActionPotentialError(FizzNeuroscienceError):
    """Raised when action potential propagation fails.

    An action potential must depolarize beyond the threshold potential
    (approximately -55 mV) to initiate regenerative sodium channel
    opening. If the depolarization stalls before threshold, the signal
    cannot propagate along the axon to downstream neurons.
    """

    def __init__(self, neuron_id: str, peak_mv: float, threshold_mv: float) -> None:
        super().__init__(
            f"Action potential propagation failure in neuron '{neuron_id}': "
            f"peak {peak_mv:.2f} mV did not reach threshold {threshold_mv:.2f} mV",
            error_code="EFP-NEU05",
            context={"neuron_id": neuron_id, "peak_mv": peak_mv, "threshold_mv": threshold_mv},
        )


class IntegrationStepError(FizzNeuroscienceError):
    """Raised when the numerical integration timestep is too large.

    The Hodgkin-Huxley equations are stiff and require sufficiently small
    timesteps for stable Euler integration. A timestep exceeding 0.1 ms
    risks numerical instability in the sodium activation gate dynamics.
    """

    def __init__(self, dt_ms: float, max_dt_ms: float) -> None:
        super().__init__(
            f"Integration timestep {dt_ms:.4f} ms exceeds maximum stable "
            f"timestep {max_dt_ms:.4f} ms for Hodgkin-Huxley equations",
            error_code="EFP-NEU06",
            context={"dt_ms": dt_ms, "max_dt_ms": max_dt_ms},
        )


class NeuroscienceMiddlewareError(FizzNeuroscienceError):
    """Raised when the FizzNeuroscience middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzNeuroscience middleware error: {reason}",
            error_code="EFP-NEU07",
            context={"reason": reason},
        )
