"""
Enterprise FizzBuzz Platform - FizzNeuromorphic Computing Test Suite

Validates the spiking neural network pipeline from neuron membrane
dynamics through synapse transmission, STDP learning, and event-driven
simulation. These tests ensure that the brain-inspired FizzBuzz classifier
produces correct spike-timing-based classifications.

A neuron with an incorrect membrane time constant could fire too early
or too late, misclassifying a number's divisibility properties based on
which output neuron reaches threshold first.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzneuromorphic import (
    DEFAULT_TAU_M,
    DEFAULT_V_REST,
    DEFAULT_V_THRESHOLD,
    FizzNeuromorphicMiddleware,
    LIFNeuron,
    NeuromorphicFizzBuzzClassifier,
    NeuronType,
    SpikingNeuralNetwork,
    SpikeEvent,
    SpikeEventType,
    STDPParams,
    Synapse,
)
from enterprise_fizzbuzz.domain.exceptions import (
    NeuronModelError,
    SynapticWeightError,
    SpikeTimingError,
    NetworkTopologyError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


def _make_context(number: int) -> ProcessingContext:
    return ProcessingContext(number=number, session_id=str(uuid.uuid4()))


# ============================================================
# LIF Neuron Tests
# ============================================================


class TestLIFNeuron:
    def test_resting_potential(self):
        n = LIFNeuron("n0")
        assert n.membrane_potential == DEFAULT_V_REST

    def test_invalid_tau_m_raises(self):
        with pytest.raises(NeuronModelError):
            LIFNeuron("bad", tau_m=-1.0)

    def test_threshold_below_rest_raises(self):
        with pytest.raises(NeuronModelError):
            LIFNeuron("bad", v_rest=-50.0, v_threshold=-60.0)

    def test_current_injection_depolarizes(self):
        n = LIFNeuron("n1")
        n.inject_current(5.0)  # Small current: enough to depolarize but not fire
        n.update(0.5, 0.0)
        assert n.membrane_potential > DEFAULT_V_REST

    def test_spike_on_threshold_crossing(self):
        n = LIFNeuron("n2", tau_m=10.0, r_membrane=20.0)
        n.inject_current(200.0)
        fired = n.update(5.0, 0.0)
        assert fired is True
        assert n.spike_count == 1

    def test_refractory_period_prevents_firing(self):
        n = LIFNeuron("n3", tau_m=10.0, r_membrane=20.0, tau_ref=5.0)
        n.inject_current(200.0)
        n.update(5.0, 0.0)  # Should fire
        # Immediately try again within refractory
        n.inject_current(200.0)
        fired = n.update(1.0, 1.0)  # Within tau_ref
        assert fired is False

    def test_reset_clears_state(self):
        n = LIFNeuron("n4")
        n.inject_current(100.0)
        n.update(1.0, 0.0)
        n.reset()
        assert n.membrane_potential == DEFAULT_V_REST
        assert n.spike_count == 0

    def test_negative_dt_raises(self):
        n = LIFNeuron("n5")
        with pytest.raises(SpikeTimingError):
            n.update(-1.0, 0.0)


# ============================================================
# Synapse Tests
# ============================================================


class TestSynapse:
    def test_transmit_returns_current(self):
        pre = LIFNeuron("pre")
        post = LIFNeuron("post")
        syn = Synapse(pre, post, weight=0.5)
        current = syn.transmit()
        assert current > 0

    def test_weight_exceeds_max_raises(self):
        pre = LIFNeuron("pre")
        post = LIFNeuron("post")
        with pytest.raises(SynapticWeightError):
            Synapse(pre, post, weight=5.0, stdp_params=STDPParams(w_max=1.0))

    def test_stdp_ltp(self):
        pre = LIFNeuron("pre")
        post = LIFNeuron("post")
        syn = Synapse(pre, post, weight=0.5)
        initial_w = syn.weight
        # Pre before post: potentiation
        delta = syn.apply_stdp(pre_spike_time=10.0, post_spike_time=15.0)
        assert delta > 0
        assert syn.weight > initial_w

    def test_stdp_ltd(self):
        pre = LIFNeuron("pre")
        post = LIFNeuron("post")
        syn = Synapse(pre, post, weight=0.5)
        initial_w = syn.weight
        # Post before pre: depression
        delta = syn.apply_stdp(pre_spike_time=15.0, post_spike_time=10.0)
        assert delta < 0
        assert syn.weight < initial_w

    def test_stdp_weight_clipping(self):
        pre = LIFNeuron("pre")
        post = LIFNeuron("post")
        params = STDPParams(a_plus=1.0, w_max=0.6)
        syn = Synapse(pre, post, weight=0.5, stdp_params=params)
        syn.apply_stdp(10.0, 10.1)
        assert syn.weight <= 0.6


# ============================================================
# Network Tests
# ============================================================


class TestSpikingNeuralNetwork:
    def test_add_neurons_and_connect(self):
        net = SpikingNeuralNetwork()
        net.add_neuron(LIFNeuron("a"))
        net.add_neuron(LIFNeuron("b"))
        syn = net.connect("a", "b", weight=0.5)
        assert net.neuron_count == 2
        assert net.synapse_count == 1

    def test_connect_nonexistent_raises(self):
        net = SpikingNeuralNetwork()
        net.add_neuron(LIFNeuron("a"))
        with pytest.raises(NetworkTopologyError):
            net.connect("a", "missing")

    def test_simulate_returns_spike_trains(self):
        net = SpikingNeuralNetwork()
        n = LIFNeuron("stim", tau_m=10.0, r_membrane=20.0)
        net.add_neuron(n)
        net.inject_spike("stim", 1.0, current=200.0)
        trains = net.simulate(20.0, dt=0.5)
        assert "stim" in trains

    def test_negative_spike_time_raises(self):
        net = SpikingNeuralNetwork()
        net.add_neuron(LIFNeuron("n"))
        with pytest.raises(SpikeTimingError):
            net.inject_spike("n", -5.0)

    def test_reset_clears_everything(self):
        net = SpikingNeuralNetwork()
        net.add_neuron(LIFNeuron("r"))
        net.inject_spike("r", 1.0)
        net.simulate(10.0)
        net.reset()
        assert len(net.spike_log) == 0


# ============================================================
# Classifier Tests
# ============================================================


class TestNeuromorphicFizzBuzzClassifier:
    def test_classify_fizzbuzz(self):
        clf = NeuromorphicFizzBuzzClassifier(num_hidden=10, simulation_ms=50.0)
        result = clf.classify(15)
        assert result["result"] == "FizzBuzz"

    def test_classify_fizz(self):
        clf = NeuromorphicFizzBuzzClassifier()
        result = clf.classify(9)
        assert result["result"] == "Fizz"

    def test_classify_buzz(self):
        clf = NeuromorphicFizzBuzzClassifier()
        result = clf.classify(10)
        assert result["result"] == "Buzz"

    def test_classify_plain(self):
        clf = NeuromorphicFizzBuzzClassifier()
        result = clf.classify(7)
        assert result["result"] == "7"

    def test_network_has_correct_topology(self):
        clf = NeuromorphicFizzBuzzClassifier(num_hidden=5)
        net = clf.network
        # 1 input + 5 hidden + 3 output = 9
        assert net.neuron_count == 9


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzNeuromorphicMiddleware:
    def test_middleware_annotates_context(self):
        mw = FizzNeuromorphicMiddleware(num_hidden=5, simulation_ms=30.0)
        ctx = _make_context(15)
        called = []
        mw.process(ctx, lambda c: called.append(True))
        assert called
        assert ctx.metadata["neuromorphic_result"] == "FizzBuzz"
        assert "neuromorphic_total_spikes" in ctx.metadata
