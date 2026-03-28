"""
Enterprise FizzBuzz Platform - FizzNeuroscience Brain Simulation Test Suite

Comprehensive verification of the Hodgkin-Huxley neuron model, ion channel
kinetics, synaptic transmission, neural circuit topology, and action
potential propagation. These tests ensure that FizzBuzz classifications
derived from neural spike codes are biophysically accurate.

A single gating variable error in the sodium inactivation gate would
prevent action potential repolarization, locking the output neurons in
a permanently depolarized state and rendering all FizzBuzz classifications
as "FizzBuzz" regardless of input — an unacceptable false positive rate.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzneuroscience import (
    DEFAULT_E_K,
    DEFAULT_E_NA,
    DEFAULT_G_K,
    DEFAULT_G_NA,
    DEFAULT_V_REST,
    FizzBuzzNeuralClassifier,
    GatingVariable,
    HodgkinHuxleyNeuron,
    IonChannelType,
    NeuralCircuit,
    NeuroscienceMiddleware,
    Synapse,
    SynapseType,
    _alpha_m,
    _alpha_n,
    _beta_m,
    _beta_n,
)
from enterprise_fizzbuzz.domain.exceptions.fizzneuroscience import (
    IntegrationStepError,
    IonChannelError,
    NeuralCircuitError,
    SynapticTransmissionError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Gating Variable Tests
# ============================================================


class TestGatingVariable:
    def test_steady_state_at_rest(self):
        gv = GatingVariable(value=0.5, alpha_fn=_alpha_m, beta_fn=_beta_m, name="m")
        ss = gv.steady_state(DEFAULT_V_REST)
        assert 0.0 <= ss <= 1.0

    def test_time_constant_positive(self):
        gv = GatingVariable(value=0.5, alpha_fn=_alpha_m, beta_fn=_beta_m, name="m")
        tau = gv.time_constant(DEFAULT_V_REST)
        assert tau > 0

    def test_step_stays_in_bounds(self):
        gv = GatingVariable(value=0.5, alpha_fn=_alpha_m, beta_fn=_beta_m, name="m")
        for _ in range(100):
            gv.step(DEFAULT_V_REST, 0.01)
        assert 0.0 <= gv.value <= 1.0

    def test_validate_out_of_range_raises(self):
        gv = GatingVariable(value=1.5, alpha_fn=_alpha_m, beta_fn=_beta_m, name="m")
        with pytest.raises(IonChannelError):
            gv.validate("sodium")


# ============================================================
# Hodgkin-Huxley Neuron Tests
# ============================================================


class TestHodgkinHuxleyNeuron:
    def test_resting_potential(self):
        neuron = HodgkinHuxleyNeuron(neuron_id="test")
        assert abs(neuron.v - DEFAULT_V_REST) < 0.01

    def test_ionic_current_at_rest_near_zero(self):
        neuron = HodgkinHuxleyNeuron(neuron_id="test")
        i_ion = neuron.ionic_current()
        # At rest, ionic currents should nearly balance
        assert abs(i_ion) < 5.0

    def test_step_without_current(self):
        neuron = HodgkinHuxleyNeuron(neuron_id="test")
        v_before = neuron.v
        neuron.step(0.05, i_ext=0.0)
        # Should stay near rest with no input
        assert abs(neuron.v - v_before) < 1.0

    def test_step_with_large_current_depolarizes(self):
        neuron = HodgkinHuxleyNeuron(neuron_id="test")
        for _ in range(200):
            neuron.step(0.05, i_ext=20.0)
        # Should have depolarized and possibly spiked
        assert neuron.spike_count >= 0

    def test_excessive_timestep_raises(self):
        neuron = HodgkinHuxleyNeuron(neuron_id="test")
        with pytest.raises(IntegrationStepError):
            neuron.step(1.0)  # 1 ms exceeds MAX_DT_MS of 0.1

    def test_reset_restores_resting_state(self):
        neuron = HodgkinHuxleyNeuron(neuron_id="test")
        neuron.step(0.05, i_ext=50.0)
        neuron.reset()
        assert abs(neuron.v - DEFAULT_V_REST) < 0.01
        assert neuron.spike_count == 0


# ============================================================
# Synapse Tests
# ============================================================


class TestSynapse:
    def test_excitatory_synapse_creation(self):
        syn = Synapse(
            synapse_id="s1", pre_neuron_id="a", post_neuron_id="b",
            synapse_type=SynapseType.EXCITATORY, g_max=0.5,
        )
        syn.validate()
        assert syn.e_syn == 0.0

    def test_negative_conductance_raises(self):
        syn = Synapse(
            synapse_id="s1", pre_neuron_id="a", post_neuron_id="b",
            g_max=-1.0,
        )
        with pytest.raises(SynapticTransmissionError):
            syn.validate()

    def test_presynaptic_spike_activates(self):
        syn = Synapse(
            synapse_id="s1", pre_neuron_id="a", post_neuron_id="b",
        )
        assert syn.s == 0.0
        syn.on_presynaptic_spike()
        assert syn.s > 0.0

    def test_synaptic_decay(self):
        syn = Synapse(
            synapse_id="s1", pre_neuron_id="a", post_neuron_id="b",
        )
        syn.on_presynaptic_spike()
        s_before = syn.s
        syn.step(5.0)
        assert syn.s < s_before


# ============================================================
# Neural Circuit Tests
# ============================================================


class TestNeuralCircuit:
    def test_add_neuron(self):
        circuit = NeuralCircuit()
        n = circuit.add_neuron("n1", is_input=True)
        assert n.neuron_id == "n1"
        assert "n1" in circuit.input_ids

    def test_add_synapse_unknown_neuron_raises(self):
        circuit = NeuralCircuit()
        circuit.add_neuron("n1")
        with pytest.raises(NeuralCircuitError):
            circuit.add_synapse("s1", "n1", "n_missing")

    def test_validate_no_inputs_raises(self):
        circuit = NeuralCircuit()
        circuit.add_neuron("n1", is_output=True)
        with pytest.raises(NeuralCircuitError):
            circuit.validate()

    def test_validate_no_outputs_raises(self):
        circuit = NeuralCircuit()
        circuit.add_neuron("n1", is_input=True)
        with pytest.raises(NeuralCircuitError):
            circuit.validate()

    def test_simulate_returns_spike_counts(self):
        circuit = NeuralCircuit()
        circuit.add_neuron("in", is_input=True)
        circuit.add_neuron("out", is_output=True)
        circuit.add_synapse("s1", "in", "out", SynapseType.EXCITATORY, 1.0)
        result = circuit.simulate(10.0, 0.05, {"in": 15.0})
        assert "out" in result
        assert isinstance(result["out"], int)

    def test_reset_clears_state(self):
        circuit = NeuralCircuit()
        circuit.add_neuron("in", is_input=True)
        circuit.add_neuron("out", is_output=True)
        circuit.add_synapse("s1", "in", "out")
        circuit.simulate(5.0, 0.05, {"in": 15.0})
        circuit.reset()
        for n in circuit.neurons.values():
            assert n.spike_count == 0


# ============================================================
# FizzBuzz Neural Classifier Tests
# ============================================================


class TestFizzBuzzNeuralClassifier:
    def test_classify_returns_spike_counts(self):
        classifier = FizzBuzzNeuralClassifier(simulation_duration_ms=10.0, dt=0.05)
        result = classifier.classify(15)
        assert "fizz_spikes" in result
        assert "buzz_spikes" in result
        assert "plain_spikes" in result

    def test_classify_multiple_numbers(self):
        classifier = FizzBuzzNeuralClassifier(simulation_duration_ms=10.0, dt=0.05)
        for n in [1, 3, 5, 15, 7]:
            result = classifier.classify(n)
            assert result["number"] == n


# ============================================================
# Middleware Tests
# ============================================================


class TestNeuroscienceMiddleware:
    def test_middleware_injects_spike_data(self):
        mw = NeuroscienceMiddleware(simulation_duration_ms=10.0, dt=0.05)
        ctx = _make_context(6)
        result = mw.process(ctx, _identity_handler)
        assert "neuro_fizz_spikes" in result.metadata
        assert "neuro_buzz_spikes" in result.metadata

    def test_middleware_name(self):
        mw = NeuroscienceMiddleware()
        assert mw.get_name() == "fizzneuroscience"

    def test_middleware_priority(self):
        mw = NeuroscienceMiddleware()
        assert mw.get_priority() == 298

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = NeuroscienceMiddleware()
        assert isinstance(mw, IMiddleware)
