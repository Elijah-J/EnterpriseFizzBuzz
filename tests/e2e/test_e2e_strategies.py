"""
Enterprise FizzBuzz Platform - E2E Test Suite: Evaluation Strategies

This test suite exercises every computational strategy the platform offers,
from the humble standard evaluator to the quantum simulator that checks
divisibility by 3 using Shor's algorithm. Each test spawns a real subprocess,
because the only way to truly verify an enterprise FizzBuzz deployment is
to boot the entire middleware stack from scratch and pray.

Categories covered:
- Core evaluation strategies (standard, chain_of_responsibility, parallel_async, machine_learning)
- Cross-strategy consistency verification
- Async mode combinations
- Bytecode VM (FBVM) execution
- Quantum Computing Simulator
- Genetic Algorithm for Optimal Rule Discovery
- Distributed Paxos Consensus
- Combined computational strategies
- Invalid strategy rejection
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ============================================================
# Constants
# ============================================================

MAIN_PY = str(Path(__file__).parent.parent.parent / "main.py")
CWD = str(Path(__file__).parent.parent.parent)
PYTHON = sys.executable

DEFAULT_TIMEOUT = 30
ML_TIMEOUT = 60
QUANTUM_TIMEOUT = 60

# The canonical FizzBuzz answers for 1-30, because enterprise correctness
# demands a truth table long enough to include two full FizzBuzz cycles.
FIZZBUZZ_1_30 = [
    "1", "2", "Fizz", "4", "Buzz",
    "Fizz", "7", "8", "Fizz", "Buzz",
    "11", "Fizz", "13", "14", "FizzBuzz",
    "16", "17", "Fizz", "19", "Buzz",
    "Fizz", "22", "23", "Fizz", "Buzz",
    "26", "Fizz", "28", "29", "FizzBuzz",
]

FIZZBUZZ_1_20 = FIZZBUZZ_1_30[:20]


# ============================================================
# Helpers (per-file, no conftest.py -- the Enterprise way)
# ============================================================

def run_cli(*args: str, timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """Invoke the Enterprise FizzBuzz Platform CLI as a subprocess.

    Returns the CompletedProcess so callers can inspect stdout, stderr,
    and returncode. Adds --no-banner and --no-summary by default because
    ASCII art banners and session summaries, while magnificent, turn
    assertion parsing into an archaeological excavation.
    """
    cmd = [PYTHON, MAIN_PY, "--no-banner", "--no-summary", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=CWD,
        env=None,
        encoding="utf-8",
        errors="replace",
    )


def extract_fizzbuzz_lines(stdout: str) -> list[str]:
    """Extract the FizzBuzz result lines from CLI output.

    The CLI emits status lines (strategy, format, range), subsystem banners,
    dashboard renderings, and occasionally existential commentary before
    delivering the actual FizzBuzz results. This function strips everything
    that isn't a result line, returning only the modulo verdicts.
    """
    lines = stdout.strip().splitlines()
    results = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip status/info/dashboard lines
        if stripped.startswith((
            "Evaluating", "Strategy:", "Output Format:",
            "Authenticated", "+-", "|", "WARNING",
            "Wall clock", "Trust-mode", "verified",
            "your password", "monitor.", "Proceed",
            "Session Summary", "Total Numbers",
            "Fizz Count", "Buzz Count", "FizzBuzz Count",
            "Plain Count", "Processing Time",
            "+=", ";", "ADDR", "---",
            "FBVM", "Because Python", "Average cycles",
            "QUANTUM", "Qubits:", "Hilbert", "Divisibility",
            "using a simplified", "is armed", "Quantum Advantage",
            "PAXOS", "Nodes:", "Quorum:", "Byzantine",
            "Every number", "ratified", "modulo operation",
            "Rules compiled:", "Instructions:", "Optimized:",
            "[GA]", "q0:", "q1:", "q2:", "q3:",
            "DISTRIBUTED", "CONSENSUS",
        )):
            continue
        results.append(stripped)
    return results


# ============================================================
# Test Class: Core Strategies in Isolation
# ============================================================

class TestCoreStrategies:
    """Tests for the four core evaluation strategies in isolation.

    Each strategy represents the platform's commitment to offering
    multiple paths to the same modulo operation, because choice is
    the hallmark of enterprise software.
    """

    def test_strategy_standard_produces_correct_fizzbuzz(self):
        """Standard strategy: the boring, correct, O(1)-per-number
        evaluation that the other three strategies aspire to match."""
        result = run_cli("--range", "1", "30", "--strategy", "standard")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30

    def test_strategy_chain_of_responsibility_produces_correct_fizzbuzz(self):
        """Chain of Responsibility strategy: the same modulo operation,
        but now it passes through a linked list of handlers first.
        Enterprise architects consider this an improvement."""
        result = run_cli("--range", "1", "30",
                         "--strategy", "chain_of_responsibility")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30

    def test_strategy_parallel_async_produces_correct_fizzbuzz(self):
        """Parallel Async strategy: evaluates FizzBuzz concurrently,
        because the modulo operation was bottlenecking the CPU."""
        result = run_cli("--range", "1", "30",
                         "--strategy", "parallel_async")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30

    def test_strategy_machine_learning_produces_correct_fizzbuzz(self):
        """Machine Learning strategy: trains a neural network from scratch
        to learn the deeply complex pattern of divisibility by 3 and 5.
        The longer timeout acknowledges that gradient descent needs time
        to contemplate what modulo does in a single clock cycle."""
        result = run_cli("--range", "1", "30",
                         "--strategy", "machine_learning",
                         timeout=ML_TIMEOUT)
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30


# ============================================================
# Test Class: Cross-Strategy Consistency
# ============================================================

class TestCrossStrategyConsistency:
    """Verify that all four strategies produce identical output.

    This test exists to confirm that replacing a modulo operation
    with gradient descent, a chain of handlers, or an async task
    pool produces the same result. The fact that this needs testing
    says everything about the platform's design philosophy.
    """

    def test_all_strategies_produce_identical_output(self):
        """Every strategy must agree on what FizzBuzz is. If they
        diverge, the platform has a distributed consensus problem
        that even Paxos cannot resolve."""
        strategies = [
            "standard",
            "chain_of_responsibility",
            "parallel_async",
            "machine_learning",
        ]
        results_by_strategy = {}
        for strategy in strategies:
            timeout = ML_TIMEOUT if strategy == "machine_learning" else DEFAULT_TIMEOUT
            result = run_cli("--range", "1", "30", "--strategy", strategy,
                             timeout=timeout)
            assert result.returncode == 0, (
                f"Strategy '{strategy}' exited with code {result.returncode}. "
                f"stderr: {result.stderr}"
            )
            results_by_strategy[strategy] = extract_fizzbuzz_lines(result.stdout)

        baseline = results_by_strategy["standard"]
        for strategy, lines in results_by_strategy.items():
            assert lines == baseline, (
                f"Strategy '{strategy}' diverged from 'standard'. "
                f"Expected {baseline}, got {lines}"
            )


# ============================================================
# Test Class: Async Mode Combinations
# ============================================================

class TestAsyncModeCombinations:
    """Tests for --async flag in combination with various strategies.

    The --async flag routes evaluation through asyncio.run(), adding
    an event loop to a synchronous modulo operation. Each combination
    must still produce correct FizzBuzz, proving that concurrency
    overhead is worth it for a single-threaded calculation.
    """

    def test_async_with_standard_strategy(self):
        """--async with standard: the event loop wraps a modulo."""
        result = run_cli("--range", "1", "20", "--strategy", "standard",
                         "--async")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_async_with_chain_of_responsibility(self):
        """--async with chain_of_responsibility: an event loop wrapping
        a linked list wrapping a modulo. Three layers of indirection."""
        result = run_cli("--range", "1", "20",
                         "--strategy", "chain_of_responsibility", "--async")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_async_with_parallel_async_strategy(self):
        """--async with parallel_async: asynchronous evaluation of
        asynchronous evaluation. Enterprise inception."""
        result = run_cli("--range", "1", "20",
                         "--strategy", "parallel_async", "--async")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_async_with_machine_learning(self):
        """--async with machine_learning: the neural network trains
        inside an event loop, because even gradient descent deserves
        non-blocking I/O."""
        result = run_cli("--range", "1", "20",
                         "--strategy", "machine_learning", "--async",
                         timeout=ML_TIMEOUT)
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20


# ============================================================
# Test Class: Bytecode VM (FBVM)
# ============================================================

class TestBytecodeVM:
    """Tests for --vm, --vm-disasm, and --vm-dashboard flags.

    The FBVM compiles FizzBuzz rules into a custom bytecode instruction
    set and executes them on a register-based virtual machine, because
    Python's interpreter was already doing that and one level of
    bytecode abstraction is never enough.
    """

    def test_vm_produces_correct_fizzbuzz(self):
        """The FBVM must produce correct FizzBuzz results. If a custom
        bytecode VM cannot perform modulo arithmetic, the instruction
        set needs a patch release."""
        result = run_cli("--range", "1", "30", "--vm")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30

    def test_vm_displays_banner(self):
        """The FBVM must announce itself with the appropriate enterprise
        gravitas when activated."""
        result = run_cli("--range", "1", "5", "--vm")
        assert result.returncode == 0
        assert "FBVM" in result.stdout
        assert "FizzBuzz Bytecode Virtual Machine ENABLED" in result.stdout

    def test_vm_disasm_shows_instruction_listing(self):
        """--vm-disasm must produce a disassembly listing with opcodes,
        operands, and comments. The instruction set includes MOD, CMP_ZERO,
        and PUSH_LABEL -- everything a bytecode VM needs for modulo."""
        result = run_cli("--range", "1", "5", "--vm", "--vm-disasm")
        assert result.returncode == 0
        assert "FBVM Disassembly" in result.stdout
        assert "OPCODE" in result.stdout
        assert "MOD" in result.stdout
        assert "HALT" in result.stdout

    def test_vm_dashboard_renders(self):
        """--vm-dashboard must produce the FBVM dashboard with register
        file, execution stats, and the quiet satisfaction of having
        compiled FizzBuzz to bytecode."""
        result = run_cli("--range", "1", "5", "--vm", "--vm-dashboard")
        assert result.returncode == 0
        assert "FBVM DASHBOARD" in result.stdout
        assert "Execution Stats" in result.stdout or "Program Info" in result.stdout


# ============================================================
# Test Class: Quantum Computing Simulator
# ============================================================

class TestQuantumSimulator:
    """Tests for --quantum and --quantum-circuit flags.

    The Quantum Computing Simulator checks divisibility using Shor's
    algorithm, which is designed for integer factorization of numbers
    with hundreds of digits. Applying it to the number 3 is either
    visionary or absurd. The tests do not distinguish.
    """

    def test_quantum_produces_correct_fizzbuzz(self):
        """Quantum-assisted FizzBuzz must produce correct results.
        The Quantum Advantage Ratio is NEGATIVE, as expected, but
        the results must still be classically correct."""
        result = run_cli("--range", "1", "30", "--quantum",
                         timeout=QUANTUM_TIMEOUT)
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30

    def test_quantum_displays_shor_banner(self):
        """The quantum simulator must announce Shor's algorithm
        with the appropriate quantum gravitas."""
        result = run_cli("--range", "1", "5", "--quantum",
                         timeout=QUANTUM_TIMEOUT)
        assert result.returncode == 0
        assert "QUANTUM COMPUTING" in result.stdout
        assert "Shor" in result.stdout

    def test_quantum_circuit_renders(self):
        """--quantum-circuit must display an ASCII quantum circuit
        diagram with qubit lines and gate operations."""
        result = run_cli("--range", "1", "5", "--quantum",
                         "--quantum-circuit", timeout=QUANTUM_TIMEOUT)
        assert result.returncode == 0
        assert "Quantum Period-Finding Circuit" in result.stdout
        # Circuit diagram uses qubit labels like q0:, q1:
        assert "q0:" in result.stdout


# ============================================================
# Test Class: Genetic Algorithm
# ============================================================

class TestGeneticAlgorithm:
    """Tests for --genetic and --genetic-generations flags.

    The Genetic Algorithm evolves a population of candidate FizzBuzz
    rule sets through selection, crossover, and mutation until it
    rediscovers {3:'Fizz', 5:'Buzz'} -- the rules that were hardcoded
    in the original 5-line solution. Darwin would appreciate the irony.
    """

    def test_genetic_algorithm_runs_and_discovers_rules(self):
        """The GA must complete its evolution and report discovered rules.
        With 10 generations, it should find something resembling the
        canonical FizzBuzz rules."""
        result = run_cli("--range", "1", "20",
                         "--genetic", "--genetic-generations", "10")
        assert result.returncode == 0
        assert "[GA]" in result.stdout
        assert "Evolution complete" in result.stdout

    def test_genetic_algorithm_fizzbuzz_still_correct(self):
        """While the GA evolves rules in the background, the main
        FizzBuzz evaluation must still produce correct results.
        The GA is a sideshow, not a replacement."""
        result = run_cli("--range", "1", "20",
                         "--genetic", "--genetic-generations", "10")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_genetic_dashboard_renders(self):
        """--genetic-dashboard must produce the evolution dashboard
        with fitness charts, chromosome details, and the quiet shame
        of having spent CPU cycles rediscovering modulo."""
        result = run_cli("--range", "1", "5",
                         "--genetic", "--genetic-generations", "10",
                         "--genetic-dashboard")
        assert result.returncode == 0
        assert "GENETIC ALGORITHM EVOLUTION DASHBOARD" in result.stdout
        assert "BEST CHROMOSOME" in result.stdout


# ============================================================
# Test Class: Distributed Paxos Consensus
# ============================================================

class TestPaxosConsensus:
    """Tests for --paxos, --paxos-nodes, --paxos-byzantine, and
    --paxos-dashboard flags.

    Paxos consensus ensures that all cluster nodes agree on whether
    15 is FizzBuzz. In a production deployment, this would involve
    network round-trips across data centers. Here, it involves
    Python lists pretending to be a network.
    """

    def test_paxos_produces_correct_fizzbuzz(self):
        """Paxos-ratified FizzBuzz must produce correct results.
        Five nodes voting on modulo arithmetic is overkill, but
        at least they agree."""
        result = run_cli("--range", "1", "30", "--paxos")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_30

    def test_paxos_custom_node_count(self):
        """--paxos-nodes allows configuring the cluster size.
        Three nodes is the minimum for a meaningful quorum,
        and also the minimum for a meaningful committee."""
        result = run_cli("--range", "1", "20", "--paxos", "--paxos-nodes", "3")
        assert result.returncode == 0
        assert "Nodes: 3" in result.stdout
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_paxos_byzantine_fault_injection(self):
        """--paxos-byzantine injects a lying node into the cluster.
        The consensus protocol must still produce correct results
        because the honest majority outvotes the traitor."""
        result = run_cli("--range", "1", "20", "--paxos", "--paxos-byzantine")
        assert result.returncode == 0
        assert "Byzantine traitor:" in result.stdout
        # Even with a byzantine node, consensus should hold
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_paxos_dashboard_renders(self):
        """--paxos-dashboard must display the consensus dashboard
        with cluster configuration, message statistics, and
        round-by-round voting records."""
        result = run_cli("--range", "1", "5", "--paxos", "--paxos-dashboard")
        assert result.returncode == 0
        assert "DISTRIBUTED PAXOS CONSENSUS DASHBOARD" in result.stdout
        assert "Cluster Configuration" in result.stdout
        assert "Consensus Rounds" in result.stdout


# ============================================================
# Test Class: Combined Computational Strategies
# ============================================================

class TestCombinedComputationalStrategies:
    """Tests for combining multiple computational subsystems.

    These tests verify that the platform can activate quantum
    simulation, Paxos consensus, genetic evolution, and the
    bytecode VM simultaneously without the middleware stack
    collapsing under its own weight. If these pass, the builder
    pattern has earned its keep.
    """

    def test_quantum_plus_paxos(self):
        """Quantum simulation and Paxos consensus together: divisibility
        is checked via Shor's algorithm and then ratified by five nodes.
        This is the computational equivalent of belt and suspenders."""
        result = run_cli("--range", "1", "20", "--quantum", "--paxos",
                         timeout=QUANTUM_TIMEOUT)
        assert result.returncode == 0
        assert "QUANTUM COMPUTING" in result.stdout
        assert "PAXOS CONSENSUS" in result.stdout
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_vm_plus_genetic_via_async(self):
        """The bytecode VM executes FizzBuzz while the genetic algorithm
        independently evolves the rules. Requires --async because the VM's
        early-exit path would otherwise skip post-execution subsystems.
        Two subsystems, both convinced that modulo needs their help."""
        result = run_cli("--range", "1", "20", "--vm", "--async",
                         "--genetic", "--genetic-generations", "10")
        assert result.returncode == 0
        assert "FBVM" in result.stdout
        assert "[GA]" in result.stdout

    def test_paxos_plus_genetic(self):
        """Paxos consensus ratifies each FizzBuzz evaluation while
        the genetic algorithm evolves rules in the background.
        Distributed systems meet evolutionary biology."""
        result = run_cli("--range", "1", "20", "--paxos",
                         "--genetic", "--genetic-generations", "10")
        assert result.returncode == 0
        assert "PAXOS CONSENSUS" in result.stdout
        assert "[GA]" in result.stdout
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_quantum_plus_genetic_plus_paxos(self):
        """The ultimate computational strategy trifecta: quantum
        period-finding, genetic evolution, and distributed consensus.
        Three subsystems collaborating to determine that 15 mod 3 == 0.
        The combined overhead is measured in CPU-centuries per modulo."""
        result = run_cli("--range", "1", "20", "--quantum", "--paxos",
                         "--genetic", "--genetic-generations", "10",
                         timeout=QUANTUM_TIMEOUT)
        assert result.returncode == 0
        assert "QUANTUM COMPUTING" in result.stdout
        assert "PAXOS CONSENSUS" in result.stdout
        assert "[GA]" in result.stdout
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20


# ============================================================
# Test Class: Invalid Strategy Handling
# ============================================================

class TestInvalidStrategies:
    """Tests for invalid or malformed strategy arguments.

    The argument parser should reject invalid strategy names with
    the same firm professionalism that an enterprise gatekeeper
    rejects unauthorized JIRA transitions.
    """

    def test_invalid_strategy_name_rejected(self):
        """An unrecognized strategy name should cause argparse to
        reject the input and exit with code 2, which is the Unix
        convention for 'you typed it wrong'."""
        cmd = [PYTHON, MAIN_PY, "--strategy", "deep_thought_42"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_empty_strategy_name_rejected(self):
        """An empty string strategy should be rejected. Even
        enterprise software has standards for non-emptiness."""
        cmd = [PYTHON, MAIN_PY, "--strategy", ""]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_strategy_flag_is_case_sensitive(self):
        """Strategy names are case-sensitive. 'Standard' is not
        'standard', because enterprise naming conventions are
        lowercase_with_underscores and we don't negotiate."""
        cmd = [PYTHON, MAIN_PY, "--strategy", "Standard"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr
