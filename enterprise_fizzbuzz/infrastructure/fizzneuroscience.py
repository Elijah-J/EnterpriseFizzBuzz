"""
Enterprise FizzBuzz Platform - FizzNeuroscience Brain Simulation Engine

Models biologically accurate neural circuits using the Hodgkin-Huxley
formalism to classify FizzBuzz evaluations through action potential
propagation. Each integer is encoded as a current stimulus injected into
an input neuron layer. The resulting spike train propagates through
ion-channel-gated axonal membranes, synaptic junctions, and dendritic
integration to produce a classification at the output neuron.

The Hodgkin-Huxley model describes the membrane potential V(t) of a
neuron in terms of voltage-gated sodium (Na+), potassium (K+), and
leak conductances:

    C_m * dV/dt = I_ext - g_Na * m^3 * h * (V - E_Na)
                        - g_K  * n^4     * (V - E_K)
                        - g_L            * (V - E_L)

where m, h, n are gating variables governed by first-order kinetics
with voltage-dependent rate constants alpha and beta.

The neural circuit maps the FizzBuzz divisibility pattern (mod-3, mod-5,
mod-15) onto distinct spike-frequency codes at the output layer. A
firing rate above threshold in the Fizz output neuron indicates
divisibility by 3; the Buzz output neuron responds to divisibility by 5;
simultaneous firing encodes FizzBuzz.

All biophysics is implemented in pure Python using only the standard
library (math). No external neuroscience libraries are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzneuroscience import (
    ActionPotentialError,
    IntegrationStepError,
    IonChannelError,
    MembranePotentialError,
    NeuralCircuitError,
    NeuroscienceMiddlewareError,
    SynapticTransmissionError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Hodgkin-Huxley default parameters (squid giant axon at 6.3C)
DEFAULT_C_M = 1.0       # Membrane capacitance (uF/cm^2)
DEFAULT_G_NA = 120.0     # Max sodium conductance (mS/cm^2)
DEFAULT_G_K = 36.0       # Max potassium conductance (mS/cm^2)
DEFAULT_G_L = 0.3        # Leak conductance (mS/cm^2)
DEFAULT_E_NA = 50.0      # Sodium reversal potential (mV)
DEFAULT_E_K = -77.0      # Potassium reversal potential (mV)
DEFAULT_E_L = -54.387    # Leak reversal potential (mV)
DEFAULT_V_REST = -65.0   # Resting membrane potential (mV)
DEFAULT_THRESHOLD = -55.0  # Spike detection threshold (mV)
MAX_DT_MS = 0.1          # Maximum stable integration timestep (ms)
V_MIN = -100.0           # Minimum physical membrane potential (mV)
V_MAX = 60.0             # Maximum physical membrane potential (mV)


# ============================================================
# Ion Channel Types
# ============================================================


class IonChannelType(Enum):
    """Types of voltage-gated ion channels in the Hodgkin-Huxley model."""

    SODIUM = auto()
    POTASSIUM = auto()
    LEAK = auto()


# ============================================================
# Synapse Types
# ============================================================


class SynapseType(Enum):
    """Classification of chemical synapses by neurotransmitter effect."""

    EXCITATORY = auto()
    INHIBITORY = auto()


# ============================================================
# Hodgkin-Huxley Rate Functions
# ============================================================


def _alpha_m(v: float) -> float:
    """Sodium activation gate opening rate."""
    denom = math.exp(-(v + 40.0) / 10.0) - 1.0
    if abs(denom) < 1e-7:
        return 1.0
    return 0.1 * (-(v + 40.0)) / denom


def _beta_m(v: float) -> float:
    """Sodium activation gate closing rate."""
    return 4.0 * math.exp(-(v + 65.0) / 18.0)


def _alpha_h(v: float) -> float:
    """Sodium inactivation gate opening rate."""
    return 0.07 * math.exp(-(v + 65.0) / 20.0)


def _beta_h(v: float) -> float:
    """Sodium inactivation gate closing rate."""
    return 1.0 / (math.exp(-(v + 35.0) / 10.0) + 1.0)


def _alpha_n(v: float) -> float:
    """Potassium activation gate opening rate."""
    denom = math.exp(-(v + 55.0) / 10.0) - 1.0
    if abs(denom) < 1e-7:
        return 0.1
    return 0.01 * (-(v + 55.0)) / denom


def _beta_n(v: float) -> float:
    """Potassium activation gate closing rate."""
    return 0.125 * math.exp(-(v + 65.0) / 80.0)


# ============================================================
# Gating Variable
# ============================================================


@dataclass
class GatingVariable:
    """A single Hodgkin-Huxley gating variable with first-order kinetics.

    Each gating variable x satisfies dx/dt = alpha_x(V)*(1-x) - beta_x(V)*x,
    which drives x toward its steady-state value x_inf = alpha / (alpha + beta)
    with time constant tau = 1 / (alpha + beta).
    """

    value: float
    alpha_fn: Callable[[float], float] = field(repr=False)
    beta_fn: Callable[[float], float] = field(repr=False)
    name: str = "x"

    def steady_state(self, v: float) -> float:
        """Compute the steady-state value at membrane potential v."""
        a = self.alpha_fn(v)
        b = self.beta_fn(v)
        denom = a + b
        if denom < 1e-12:
            return 0.0
        return a / denom

    def time_constant(self, v: float) -> float:
        """Compute the time constant tau (ms) at membrane potential v."""
        a = self.alpha_fn(v)
        b = self.beta_fn(v)
        denom = a + b
        if denom < 1e-12:
            return 1e6
        return 1.0 / denom

    def step(self, v: float, dt: float) -> None:
        """Advance the gating variable by dt milliseconds using forward Euler."""
        a = self.alpha_fn(v)
        b = self.beta_fn(v)
        dx = (a * (1.0 - self.value) - b * self.value) * dt
        self.value += dx
        self.value = max(0.0, min(1.0, self.value))

    def validate(self, channel_type: str) -> None:
        """Ensure the gating variable is within [0, 1]."""
        if self.value < 0.0 or self.value > 1.0:
            raise IonChannelError(channel_type, self.name, self.value)


# ============================================================
# Hodgkin-Huxley Neuron
# ============================================================


@dataclass
class HodgkinHuxleyNeuron:
    """A single neuron modeled by the Hodgkin-Huxley equations.

    Maintains membrane potential and three gating variables (m, h, n)
    that govern sodium and potassium conductances. External current
    injection drives the membrane potential toward threshold, potentially
    triggering an action potential.
    """

    neuron_id: str
    v: float = DEFAULT_V_REST
    c_m: float = DEFAULT_C_M
    g_na: float = DEFAULT_G_NA
    g_k: float = DEFAULT_G_K
    g_l: float = DEFAULT_G_L
    e_na: float = DEFAULT_E_NA
    e_k: float = DEFAULT_E_K
    e_l: float = DEFAULT_E_L
    threshold: float = DEFAULT_THRESHOLD
    m: GatingVariable = field(default=None)
    h: GatingVariable = field(default=None)
    n: GatingVariable = field(default=None)
    spike_count: int = 0
    _in_spike: bool = False

    def __post_init__(self) -> None:
        if self.m is None:
            self.m = GatingVariable(
                value=_alpha_m(self.v) / (_alpha_m(self.v) + _beta_m(self.v)),
                alpha_fn=_alpha_m,
                beta_fn=_beta_m,
                name="m",
            )
        if self.h is None:
            self.h = GatingVariable(
                value=_alpha_h(self.v) / (_alpha_h(self.v) + _beta_h(self.v)),
                alpha_fn=_alpha_h,
                beta_fn=_beta_h,
                name="h",
            )
        if self.n is None:
            self.n = GatingVariable(
                value=_alpha_n(self.v) / (_alpha_n(self.v) + _beta_n(self.v)),
                alpha_fn=_alpha_n,
                beta_fn=_beta_n,
                name="n",
            )

    def ionic_current(self) -> float:
        """Compute total ionic membrane current (uA/cm^2)."""
        i_na = self.g_na * (self.m.value ** 3) * self.h.value * (self.v - self.e_na)
        i_k = self.g_k * (self.n.value ** 4) * (self.v - self.e_k)
        i_l = self.g_l * (self.v - self.e_l)
        return i_na + i_k + i_l

    def step(self, dt: float, i_ext: float = 0.0) -> None:
        """Advance the neuron state by dt milliseconds.

        Args:
            dt: Integration timestep in milliseconds.
            i_ext: External injected current in uA/cm^2.
        """
        if dt > MAX_DT_MS:
            raise IntegrationStepError(dt, MAX_DT_MS)

        # Update gating variables
        self.m.step(self.v, dt)
        self.h.step(self.v, dt)
        self.n.step(self.v, dt)

        # Update membrane potential
        i_ionic = self.ionic_current()
        dv = (i_ext - i_ionic) / self.c_m * dt
        self.v += dv

        # Clamp to physical bounds
        self.v = max(V_MIN, min(V_MAX, self.v))

        # Detect spikes
        if not self._in_spike and self.v >= self.threshold:
            self._in_spike = True
            self.spike_count += 1
        elif self._in_spike and self.v < self.threshold - 10.0:
            self._in_spike = False

    def reset(self) -> None:
        """Reset neuron to resting state."""
        self.v = DEFAULT_V_REST
        self.m.value = self.m.steady_state(self.v)
        self.h.value = self.h.steady_state(self.v)
        self.n.value = self.n.steady_state(self.v)
        self.spike_count = 0
        self._in_spike = False


# ============================================================
# Synapse
# ============================================================


@dataclass
class Synapse:
    """A chemical synapse connecting a presynaptic to a postsynaptic neuron.

    Models synaptic transmission as a conductance change in the
    postsynaptic neuron triggered by presynaptic spikes. The synaptic
    current I_syn = g_syn * s * (V_post - E_syn) where s is the
    synaptic gating variable that rises on presynaptic spikes and
    decays exponentially.
    """

    synapse_id: str
    pre_neuron_id: str
    post_neuron_id: str
    synapse_type: SynapseType = SynapseType.EXCITATORY
    g_max: float = 0.5       # Maximum synaptic conductance (mS/cm^2)
    e_syn: float = 0.0       # Reversal potential (mV): 0 for excitatory, -80 for inhibitory
    tau_decay: float = 5.0   # Decay time constant (ms)
    s: float = 0.0           # Synaptic gating variable [0, 1]

    def validate(self) -> None:
        """Validate synaptic parameters."""
        if self.g_max < 0:
            raise SynapticTransmissionError(
                self.synapse_id,
                f"Negative maximum conductance {self.g_max}",
            )
        if self.synapse_type == SynapseType.EXCITATORY and self.e_syn < -20:
            raise SynapticTransmissionError(
                self.synapse_id,
                f"Excitatory synapse with inhibitory reversal potential {self.e_syn} mV",
            )

    def on_presynaptic_spike(self) -> None:
        """Activate synaptic conductance in response to a presynaptic spike."""
        self.s = min(1.0, self.s + 0.5)

    def step(self, dt: float) -> None:
        """Decay the synaptic gating variable."""
        if self.tau_decay > 0:
            self.s *= math.exp(-dt / self.tau_decay)

    def current(self, v_post: float) -> float:
        """Compute synaptic current into the postsynaptic neuron."""
        return self.g_max * self.s * (v_post - self.e_syn)


# ============================================================
# Neural Circuit
# ============================================================


class NeuralCircuit:
    """A network of Hodgkin-Huxley neurons connected by chemical synapses.

    The circuit topology consists of input neurons (receiving external
    current encoding the FizzBuzz number), hidden neurons (performing
    intermediate computation), and output neurons (whose spike counts
    encode the classification result).
    """

    def __init__(self) -> None:
        self._neurons: dict[str, HodgkinHuxleyNeuron] = {}
        self._synapses: list[Synapse] = []
        self._input_ids: list[str] = []
        self._output_ids: list[str] = []

    def add_neuron(
        self, neuron_id: str, is_input: bool = False, is_output: bool = False
    ) -> HodgkinHuxleyNeuron:
        """Add a neuron to the circuit."""
        neuron = HodgkinHuxleyNeuron(neuron_id=neuron_id)
        self._neurons[neuron_id] = neuron
        if is_input:
            self._input_ids.append(neuron_id)
        if is_output:
            self._output_ids.append(neuron_id)
        return neuron

    def add_synapse(
        self,
        synapse_id: str,
        pre_id: str,
        post_id: str,
        synapse_type: SynapseType = SynapseType.EXCITATORY,
        g_max: float = 0.5,
    ) -> Synapse:
        """Connect two neurons with a chemical synapse."""
        if pre_id not in self._neurons or post_id not in self._neurons:
            raise NeuralCircuitError(
                f"Synapse '{synapse_id}' references unknown neuron(s)"
            )
        e_syn = 0.0 if synapse_type == SynapseType.EXCITATORY else -80.0
        syn = Synapse(
            synapse_id=synapse_id,
            pre_neuron_id=pre_id,
            post_neuron_id=post_id,
            synapse_type=synapse_type,
            g_max=g_max,
            e_syn=e_syn,
        )
        syn.validate()
        self._synapses.append(syn)
        return syn

    def validate(self) -> None:
        """Validate circuit topology."""
        if not self._input_ids:
            raise NeuralCircuitError("No input neurons defined")
        if not self._output_ids:
            raise NeuralCircuitError("No output neurons defined")

    def get_neuron(self, neuron_id: str) -> HodgkinHuxleyNeuron:
        """Retrieve a neuron by ID."""
        if neuron_id not in self._neurons:
            raise NeuralCircuitError(f"Neuron '{neuron_id}' not found")
        return self._neurons[neuron_id]

    @property
    def input_ids(self) -> list[str]:
        return list(self._input_ids)

    @property
    def output_ids(self) -> list[str]:
        return list(self._output_ids)

    @property
    def neurons(self) -> dict[str, HodgkinHuxleyNeuron]:
        return dict(self._neurons)

    @property
    def synapses(self) -> list[Synapse]:
        return list(self._synapses)

    def step(self, dt: float, input_currents: dict[str, float] | None = None) -> None:
        """Advance the entire circuit by dt milliseconds."""
        currents = input_currents or {}

        # Track presynaptic spikes for this timestep
        pre_spike_counts = {
            nid: n.spike_count for nid, n in self._neurons.items()
        }

        # Compute synaptic currents
        syn_currents: dict[str, float] = {nid: 0.0 for nid in self._neurons}
        for syn in self._synapses:
            post = self._neurons[syn.post_neuron_id]
            syn_currents[syn.post_neuron_id] += syn.current(post.v)

        # Step all neurons
        for nid, neuron in self._neurons.items():
            i_ext = currents.get(nid, 0.0) - syn_currents[nid]
            neuron.step(dt, i_ext)

        # Process synaptic events
        for syn in self._synapses:
            pre = self._neurons[syn.pre_neuron_id]
            if pre.spike_count > pre_spike_counts[syn.pre_neuron_id]:
                syn.on_presynaptic_spike()
            syn.step(dt)

    def simulate(
        self,
        duration_ms: float,
        dt: float,
        input_currents: dict[str, float] | None = None,
    ) -> dict[str, int]:
        """Run the circuit for the specified duration and return output spike counts."""
        self.validate()
        steps = max(1, int(duration_ms / dt))
        for _ in range(steps):
            self.step(dt, input_currents)
        return {nid: self._neurons[nid].spike_count for nid in self._output_ids}

    def reset(self) -> None:
        """Reset all neurons and synapses to initial state."""
        for neuron in self._neurons.values():
            neuron.reset()
        for syn in self._synapses:
            syn.s = 0.0


# ============================================================
# FizzBuzz Neural Classifier
# ============================================================


class FizzBuzzNeuralClassifier:
    """Maps FizzBuzz numbers to neural circuit stimuli and interprets output.

    The classifier constructs a three-output neural circuit:
    - Output neuron 'fizz': fires when the input is divisible by 3
    - Output neuron 'buzz': fires when the input is divisible by 5
    - Output neuron 'plain': fires for non-divisible inputs

    The input encoding converts the number's mod-3 and mod-5 residues
    into current amplitudes that bias the appropriate output pathways
    through intermediate neurons.
    """

    def __init__(self, simulation_duration_ms: float = 50.0, dt: float = 0.05) -> None:
        self._duration = simulation_duration_ms
        self._dt = dt
        self._circuit = self._build_circuit()

    def _build_circuit(self) -> NeuralCircuit:
        """Construct the FizzBuzz classification circuit."""
        circuit = NeuralCircuit()

        # Input neurons: encode mod-3 and mod-5 residues
        circuit.add_neuron("input_mod3", is_input=True)
        circuit.add_neuron("input_mod5", is_input=True)

        # Hidden layer
        circuit.add_neuron("hidden_fizz")
        circuit.add_neuron("hidden_buzz")

        # Output neurons
        circuit.add_neuron("fizz_out", is_output=True)
        circuit.add_neuron("buzz_out", is_output=True)
        circuit.add_neuron("plain_out", is_output=True)

        # Wiring: mod3 input drives fizz pathway
        circuit.add_synapse("s_m3_hf", "input_mod3", "hidden_fizz",
                            SynapseType.EXCITATORY, 1.0)
        circuit.add_synapse("s_hf_fo", "hidden_fizz", "fizz_out",
                            SynapseType.EXCITATORY, 1.0)

        # Wiring: mod5 input drives buzz pathway
        circuit.add_synapse("s_m5_hb", "input_mod5", "hidden_buzz",
                            SynapseType.EXCITATORY, 1.0)
        circuit.add_synapse("s_hb_bo", "hidden_buzz", "buzz_out",
                            SynapseType.EXCITATORY, 1.0)

        # Inhibitory connections from fizz/buzz to plain
        circuit.add_synapse("s_hf_po", "hidden_fizz", "plain_out",
                            SynapseType.INHIBITORY, 0.8)
        circuit.add_synapse("s_hb_po", "hidden_buzz", "plain_out",
                            SynapseType.INHIBITORY, 0.8)

        return circuit

    def classify(self, number: int) -> dict[str, Any]:
        """Classify a number using neural circuit simulation."""
        self._circuit.reset()

        # Encode number as input currents
        mod3_current = 15.0 if number % 3 == 0 else 2.0
        mod5_current = 15.0 if number % 5 == 0 else 2.0

        # Tonic current to plain pathway
        input_currents = {
            "input_mod3": mod3_current,
            "input_mod5": mod5_current,
        }

        spike_counts = self._circuit.simulate(
            self._duration, self._dt, input_currents
        )

        return {
            "fizz_spikes": spike_counts.get("fizz_out", 0),
            "buzz_spikes": spike_counts.get("buzz_out", 0),
            "plain_spikes": spike_counts.get("plain_out", 0),
            "number": number,
        }

    @property
    def circuit(self) -> NeuralCircuit:
        return self._circuit


# ============================================================
# FizzNeuroscience Middleware
# ============================================================


class NeuroscienceMiddleware(IMiddleware):
    """Injects neural simulation data into the FizzBuzz pipeline.

    For each number evaluated, the middleware runs a Hodgkin-Huxley
    neural circuit simulation and records spike counts, membrane
    potential traces, and classification confidence in the processing
    context metadata.
    """

    def __init__(
        self,
        simulation_duration_ms: float = 50.0,
        dt: float = 0.05,
    ) -> None:
        self._classifier = FizzBuzzNeuralClassifier(simulation_duration_ms, dt)

    @property
    def engine(self) -> FizzBuzzNeuralClassifier:
        return self._classifier

    def get_name(self) -> str:
        return "fizzneuroscience"

    def get_priority(self) -> int:
        return 298

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Run neural simulation and inject results into context."""
        try:
            result = self._classifier.classify(context.number)
            context.metadata["neuro_fizz_spikes"] = result["fizz_spikes"]
            context.metadata["neuro_buzz_spikes"] = result["buzz_spikes"]
            context.metadata["neuro_plain_spikes"] = result["plain_spikes"]

            logger.debug(
                "FizzNeuroscience: number=%d fizz_spikes=%d buzz_spikes=%d plain_spikes=%d",
                context.number,
                result["fizz_spikes"],
                result["buzz_spikes"],
                result["plain_spikes"],
            )
        except Exception as exc:
            logger.error("FizzNeuroscience middleware error: %s", exc)
            context.metadata["neuro_error"] = str(exc)

        return next_handler(context)
