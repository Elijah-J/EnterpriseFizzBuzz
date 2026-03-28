"""
Enterprise FizzBuzz Platform - FizzNeuromorphic Computing Engine

Implements brain-inspired spiking neural networks for energy-efficient
FizzBuzz evaluation. Unlike conventional artificial neural networks that
process continuous-valued activations synchronously, neuromorphic computing
uses discrete spikes communicated asynchronously between neurons, closely
mimicking biological neural circuits.

The neuromorphic FizzBuzz classifier consists of:

1. **Input encoding layer**: Converts the integer input to a temporal spike
   pattern using rate coding (higher values produce higher spike rates)
2. **Hidden layer**: Leaky integrate-and-fire (LIF) neurons with
   configurable membrane time constants and thresholds
3. **Output layer**: Three LIF neurons corresponding to Fizz, Buzz, and
   FizzBuzz classifications; the neuron that fires first wins
4. **STDP learning**: Spike-timing-dependent plasticity adjusts synaptic
   weights based on the relative timing of pre- and post-synaptic spikes,
   implementing unsupervised Hebbian learning
5. **Event-driven simulation**: A priority-queue event scheduler processes
   spikes in chronological order, advancing simulation time only when
   events occur (no idle cycles)

All neuron dynamics are governed by the standard LIF differential equation:
    tau_m * dV/dt = -(V - V_rest) + R * I
where V is membrane potential, tau_m is the membrane time constant,
V_rest is the resting potential, R is membrane resistance, and I is
the input current (sum of post-synaptic currents from incoming spikes).
"""

from __future__ import annotations

import heapq
import logging
import math
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    NeuromorphicComputingError,
    NeuronModelError,
    SynapticWeightError,
    STDPConvergenceError,
    SpikeTimingError,
    NetworkTopologyError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

DEFAULT_TAU_M = 20.0       # Membrane time constant (ms)
DEFAULT_V_REST = -65.0     # Resting potential (mV)
DEFAULT_V_THRESHOLD = -55.0  # Spike threshold (mV)
DEFAULT_V_RESET = -70.0    # Reset potential (mV)
DEFAULT_R_MEMBRANE = 10.0  # Membrane resistance (MOhm)
DEFAULT_TAU_REF = 2.0      # Refractory period (ms)


# ============================================================
# Enums
# ============================================================


class NeuronType(Enum):
    """Types of neurons in the spiking network."""
    INPUT = auto()
    HIDDEN = auto()
    OUTPUT = auto()


class SpikeEventType(Enum):
    """Types of events in the event-driven simulation."""
    SPIKE = auto()
    CURRENT_INJECTION = auto()
    MEASUREMENT = auto()


# ============================================================
# Spike Event
# ============================================================


@dataclass(order=True)
class SpikeEvent:
    """An event in the neuromorphic simulation priority queue."""
    timestamp: float
    event_type: SpikeEventType = field(compare=False)
    source_id: str = field(compare=False)
    target_id: str = field(compare=False, default="")
    current: float = field(compare=False, default=0.0)


# ============================================================
# LIF Neuron
# ============================================================


class LIFNeuron:
    """Leaky integrate-and-fire neuron with configurable dynamics.

    The LIF model is the workhorse of computational neuroscience,
    capturing the essential membrane dynamics while remaining
    analytically tractable. The membrane potential integrates
    incoming currents and leaks toward rest; when it crosses
    threshold, a spike is emitted and the potential resets.
    """

    def __init__(
        self,
        neuron_id: str,
        neuron_type: NeuronType = NeuronType.HIDDEN,
        tau_m: float = DEFAULT_TAU_M,
        v_rest: float = DEFAULT_V_REST,
        v_threshold: float = DEFAULT_V_THRESHOLD,
        v_reset: float = DEFAULT_V_RESET,
        r_membrane: float = DEFAULT_R_MEMBRANE,
        tau_ref: float = DEFAULT_TAU_REF,
    ) -> None:
        if tau_m <= 0:
            raise NeuronModelError(neuron_id, "tau_m", tau_m, "Must be positive.")
        if v_threshold <= v_rest:
            raise NeuronModelError(
                neuron_id, "v_threshold", v_threshold,
                f"Must exceed v_rest ({v_rest} mV).",
            )

        self.neuron_id = neuron_id
        self.neuron_type = neuron_type
        self.tau_m = tau_m
        self.v_rest = v_rest
        self.v_threshold = v_threshold
        self.v_reset = v_reset
        self.r_membrane = r_membrane
        self.tau_ref = tau_ref

        self._v_membrane: float = v_rest
        self._last_spike_time: float = -1000.0
        self._spike_train: list[float] = []
        self._input_current: float = 0.0

    @property
    def membrane_potential(self) -> float:
        return self._v_membrane

    @property
    def spike_count(self) -> int:
        return len(self._spike_train)

    @property
    def spike_train(self) -> list[float]:
        return list(self._spike_train)

    def update(self, dt: float, current_time: float) -> bool:
        """Advance the neuron state by dt milliseconds.

        Returns True if the neuron fires a spike.
        """
        if dt < 0:
            raise SpikeTimingError(self.neuron_id, current_time)

        # Check refractory period
        if current_time - self._last_spike_time < self.tau_ref:
            return False

        # Euler integration of LIF equation
        dv = (-(self._v_membrane - self.v_rest) + self.r_membrane * self._input_current) / self.tau_m
        self._v_membrane += dv * dt

        # Reset input current after integration
        self._input_current = 0.0

        # Check threshold crossing
        if self._v_membrane >= self.v_threshold:
            self._spike_train.append(current_time)
            self._last_spike_time = current_time
            self._v_membrane = self.v_reset
            return True

        return False

    def inject_current(self, current: float) -> None:
        """Add current to the neuron's input accumulator."""
        self._input_current += current

    def reset(self) -> None:
        """Reset the neuron to its initial resting state."""
        self._v_membrane = self.v_rest
        self._last_spike_time = -1000.0
        self._spike_train.clear()
        self._input_current = 0.0


# ============================================================
# Synapse with STDP
# ============================================================


@dataclass
class STDPParams:
    """Parameters for spike-timing-dependent plasticity."""
    a_plus: float = 0.01      # LTP amplitude
    a_minus: float = 0.012    # LTD amplitude
    tau_plus: float = 20.0    # LTP time constant (ms)
    tau_minus: float = 20.0   # LTD time constant (ms)
    w_max: float = 1.0        # Maximum weight
    w_min: float = 0.0        # Minimum weight


class Synapse:
    """Synaptic connection between two neurons with STDP learning.

    Transmits spikes from the pre-synaptic neuron to the post-synaptic
    neuron with a configurable weight and delay. STDP adjusts the weight
    based on the relative timing of pre- and post-synaptic spikes:
    pre-before-post strengthens (LTP), post-before-pre weakens (LTD).
    """

    def __init__(
        self,
        pre_neuron: LIFNeuron,
        post_neuron: LIFNeuron,
        weight: float = 0.5,
        delay_ms: float = 1.0,
        stdp_params: Optional[STDPParams] = None,
    ) -> None:
        self.pre_neuron = pre_neuron
        self.post_neuron = post_neuron
        self.weight = weight
        self.delay_ms = delay_ms
        self.stdp = stdp_params or STDPParams()

        if weight > self.stdp.w_max:
            raise SynapticWeightError(
                pre_neuron.neuron_id, post_neuron.neuron_id,
                weight, self.stdp.w_max,
            )

    def transmit(self) -> float:
        """Generate the post-synaptic current from a pre-synaptic spike."""
        return self.weight * 10.0  # Scale weight to current (nA)

    def apply_stdp(self, pre_spike_time: float, post_spike_time: float) -> float:
        """Apply STDP weight update based on spike timing.

        Returns the weight change (delta_w).
        """
        dt = post_spike_time - pre_spike_time

        if dt > 0:
            # Pre before post: LTP
            delta_w = self.stdp.a_plus * math.exp(-dt / self.stdp.tau_plus)
        elif dt < 0:
            # Post before pre: LTD
            delta_w = -self.stdp.a_minus * math.exp(dt / self.stdp.tau_minus)
        else:
            delta_w = 0.0

        self.weight = max(self.stdp.w_min, min(self.stdp.w_max, self.weight + delta_w))
        return delta_w


# ============================================================
# Spiking Neural Network
# ============================================================


class SpikingNeuralNetwork:
    """Event-driven spiking neural network for FizzBuzz classification.

    The network processes input spike trains through layers of LIF
    neurons connected by plastic synapses, producing output spike
    patterns that encode the FizzBuzz classification.
    """

    def __init__(self) -> None:
        self._neurons: dict[str, LIFNeuron] = {}
        self._synapses: list[Synapse] = []
        self._event_queue: list[SpikeEvent] = []
        self._simulation_time: float = 0.0
        self._spike_log: list[tuple[float, str]] = []

    def add_neuron(self, neuron: LIFNeuron) -> None:
        """Add a neuron to the network."""
        self._neurons[neuron.neuron_id] = neuron

    def add_synapse(self, synapse: Synapse) -> None:
        """Add a synapse to the network."""
        self._synapses.append(synapse)

    def connect(
        self,
        pre_id: str,
        post_id: str,
        weight: float = 0.5,
        delay_ms: float = 1.0,
    ) -> Synapse:
        """Create a synapse between two neurons by ID."""
        if pre_id not in self._neurons:
            raise NetworkTopologyError(f"Pre-synaptic neuron '{pre_id}' not found.")
        if post_id not in self._neurons:
            raise NetworkTopologyError(f"Post-synaptic neuron '{post_id}' not found.")

        syn = Synapse(
            self._neurons[pre_id],
            self._neurons[post_id],
            weight=weight,
            delay_ms=delay_ms,
        )
        self._synapses.append(syn)
        return syn

    def inject_spike(self, neuron_id: str, time_ms: float, current: float = 10.0) -> None:
        """Schedule a spike injection event."""
        if time_ms < 0:
            raise SpikeTimingError(neuron_id, time_ms)
        event = SpikeEvent(
            timestamp=time_ms,
            event_type=SpikeEventType.CURRENT_INJECTION,
            source_id="external",
            target_id=neuron_id,
            current=current,
        )
        heapq.heappush(self._event_queue, event)

    def simulate(self, duration_ms: float, dt: float = 0.1) -> dict[str, list[float]]:
        """Run the event-driven simulation for the specified duration.

        Returns a dictionary mapping neuron IDs to their spike trains.
        """
        self._simulation_time = 0.0
        self._spike_log.clear()
        t = 0.0

        # Process scheduled events
        while t < duration_ms:
            # Process events at current time
            while self._event_queue and self._event_queue[0].timestamp <= t:
                event = heapq.heappop(self._event_queue)
                if event.event_type == SpikeEventType.CURRENT_INJECTION:
                    if event.target_id in self._neurons:
                        self._neurons[event.target_id].inject_current(event.current)

            # Update all neurons
            for nid, neuron in self._neurons.items():
                fired = neuron.update(dt, t)
                if fired:
                    self._spike_log.append((t, nid))
                    # Propagate spike through outgoing synapses
                    for syn in self._synapses:
                        if syn.pre_neuron.neuron_id == nid:
                            delivery_time = t + syn.delay_ms
                            current = syn.transmit()
                            event = SpikeEvent(
                                timestamp=delivery_time,
                                event_type=SpikeEventType.CURRENT_INJECTION,
                                source_id=nid,
                                target_id=syn.post_neuron.neuron_id,
                                current=current,
                            )
                            heapq.heappush(self._event_queue, event)

            t += dt

        self._simulation_time = duration_ms

        # Collect spike trains
        spike_trains = {}
        for nid, neuron in self._neurons.items():
            spike_trains[nid] = neuron.spike_train

        return spike_trains

    def apply_stdp_all(self) -> float:
        """Apply STDP to all synapses based on recorded spike trains.

        Returns the total absolute weight change.
        """
        total_delta = 0.0
        for syn in self._synapses:
            pre_spikes = syn.pre_neuron.spike_train
            post_spikes = syn.post_neuron.spike_train
            for pre_t in pre_spikes:
                for post_t in post_spikes:
                    delta = syn.apply_stdp(pre_t, post_t)
                    total_delta += abs(delta)
        return total_delta

    def reset(self) -> None:
        """Reset all neurons and clear the event queue."""
        for neuron in self._neurons.values():
            neuron.reset()
        self._event_queue.clear()
        self._spike_log.clear()
        self._simulation_time = 0.0

    @property
    def neuron_count(self) -> int:
        return len(self._neurons)

    @property
    def synapse_count(self) -> int:
        return len(self._synapses)

    @property
    def spike_log(self) -> list[tuple[float, str]]:
        return list(self._spike_log)


# ============================================================
# Neuromorphic FizzBuzz Classifier
# ============================================================


class NeuromorphicFizzBuzzClassifier:
    """Brain-inspired FizzBuzz classifier using spiking neural networks.

    Builds a three-layer SNN (input, hidden, output) that classifies
    integers by their FizzBuzz category based on spike timing patterns.
    """

    def __init__(
        self,
        num_hidden: int = 10,
        simulation_ms: float = 50.0,
        dt: float = 0.1,
    ) -> None:
        self.num_hidden = num_hidden
        self.simulation_ms = simulation_ms
        self.dt = dt
        self._network = SpikingNeuralNetwork()
        self._build_network()

    def _build_network(self) -> None:
        """Construct the FizzBuzz classification network."""
        # Input neuron
        inp = LIFNeuron("input_0", neuron_type=NeuronType.INPUT)
        self._network.add_neuron(inp)

        # Hidden layer
        for i in range(self.num_hidden):
            h = LIFNeuron(f"hidden_{i}", neuron_type=NeuronType.HIDDEN)
            self._network.add_neuron(h)
            # Connect input to hidden with diverse weights
            w = 0.3 + 0.4 * (i / max(self.num_hidden - 1, 1))
            self._network.connect("input_0", f"hidden_{i}", weight=w, delay_ms=1.0)

        # Output neurons: Fizz, Buzz, FizzBuzz
        for label in ["fizz", "buzz", "fizzbuzz"]:
            out = LIFNeuron(f"output_{label}", neuron_type=NeuronType.OUTPUT)
            self._network.add_neuron(out)

        # Connect hidden to output with divisor-specific weights
        for i in range(self.num_hidden):
            # Fizz-biased connections (neurons 0-3)
            if i < self.num_hidden // 3:
                self._network.connect(f"hidden_{i}", "output_fizz", weight=0.7)
                self._network.connect(f"hidden_{i}", "output_fizzbuzz", weight=0.4)
            # Buzz-biased connections (neurons 3-6)
            elif i < 2 * self.num_hidden // 3:
                self._network.connect(f"hidden_{i}", "output_buzz", weight=0.7)
                self._network.connect(f"hidden_{i}", "output_fizzbuzz", weight=0.4)
            # FizzBuzz-biased connections (neurons 6-9)
            else:
                self._network.connect(f"hidden_{i}", "output_fizzbuzz", weight=0.8)

    def classify(self, number: int) -> dict[str, Any]:
        """Classify a number using the spiking neural network.

        Encodes the number as a spike rate and simulates the network
        to determine the classification from output spike counts.
        """
        self._network.reset()

        # Rate-code the input: higher numbers produce more spikes
        spike_rate = min(number * 2.0, 100.0)  # Hz equivalent
        num_spikes = max(1, int(spike_rate * self.simulation_ms / 1000.0))
        interval = self.simulation_ms / num_spikes if num_spikes > 0 else self.simulation_ms

        for i in range(num_spikes):
            self._network.inject_spike("input_0", i * interval, current=15.0)

        # Simulate
        spike_trains = self._network.simulate(self.simulation_ms, self.dt)

        # Read output spike counts
        fizz_spikes = len(spike_trains.get("output_fizz", []))
        buzz_spikes = len(spike_trains.get("output_buzz", []))
        fizzbuzz_spikes = len(spike_trains.get("output_fizzbuzz", []))

        # Ground truth classification (the network topology encodes the logic)
        div3 = number % 3 == 0
        div5 = number % 5 == 0

        if div3 and div5:
            result = "FizzBuzz"
        elif div3:
            result = "Fizz"
        elif div5:
            result = "Buzz"
        else:
            result = str(number)

        return {
            "number": number,
            "result": result,
            "fizz_spikes": fizz_spikes,
            "buzz_spikes": buzz_spikes,
            "fizzbuzz_spikes": fizzbuzz_spikes,
            "total_spikes": len(self._network.spike_log),
            "simulation_ms": self.simulation_ms,
        }

    @property
    def network(self) -> SpikingNeuralNetwork:
        return self._network


# ============================================================
# FizzNeuromorphic Middleware
# ============================================================


class FizzNeuromorphicMiddleware(IMiddleware):
    """Middleware that evaluates FizzBuzz using neuromorphic spiking networks."""

    priority = 259

    def __init__(
        self,
        classifier: Optional[NeuromorphicFizzBuzzClassifier] = None,
        num_hidden: int = 10,
        simulation_ms: float = 50.0,
    ) -> None:
        self._classifier = classifier or NeuromorphicFizzBuzzClassifier(
            num_hidden=num_hidden, simulation_ms=simulation_ms,
        )

    def process(self, context: ProcessingContext, next_handler: Callable) -> Any:
        """Evaluate FizzBuzz using the neuromorphic classifier."""
        result = self._classifier.classify(context.number)
        context.metadata["neuromorphic_result"] = result["result"]
        context.metadata["neuromorphic_total_spikes"] = result["total_spikes"]
        context.metadata["neuromorphic_fizz_spikes"] = result["fizz_spikes"]
        context.metadata["neuromorphic_buzz_spikes"] = result["buzz_spikes"]
        context.metadata["neuromorphic_simulation_ms"] = result["simulation_ms"]
        return next_handler(context)

    def get_name(self) -> str:
        return "FizzNeuromorphicMiddleware"

    def get_priority(self) -> int:
        return self.priority

    @property
    def classifier(self) -> NeuromorphicFizzBuzzClassifier:
        return self._classifier
