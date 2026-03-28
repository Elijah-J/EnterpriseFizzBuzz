"""
Enterprise FizzBuzz Platform - FizzEpidemiology: Disease Spread Modeler

Implements SIR and SEIR compartmental models, basic reproduction number
(R0) estimation, herd immunity threshold computation, contact tracing
graph analysis, and vaccination strategy optimization for modeling the
propagation of FizzBuzz classifications through a population of integers.

The spread of FizzBuzz classifications through the integer number line
follows epidemiological dynamics. A "Fizz infection" originates at
multiples of 3 and propagates through arithmetic proximity. A "Buzz
infection" originates at multiples of 5. The "FizzBuzz" state represents
co-infection. Understanding the reproduction number and herd immunity
threshold for each classification is critical for predicting how
quickly the entire number line will be classified and whether any
numbers will remain unclassified (susceptible).

The SIR model tracks numbers in three compartments: Susceptible
(unclassified), Infected (currently being classified), and Recovered
(classification complete). The SEIR extension adds an Exposed
compartment for numbers that are adjacent to a classified number but
have not yet been evaluated. These models enable capacity planning for
the evaluation pipeline.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_POPULATION = 1000
DEFAULT_BETA = 0.3  # Transmission rate
DEFAULT_GAMMA = 0.1  # Recovery rate
DEFAULT_SIGMA = 0.2  # Incubation rate (SEIR)
DEFAULT_TIME_STEPS = 100
DEFAULT_DT = 0.1


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Compartment(Enum):
    """Epidemiological compartments."""
    SUSCEPTIBLE = auto()
    EXPOSED = auto()
    INFECTED = auto()
    RECOVERED = auto()
    VACCINATED = auto()


class VaccinationStrategy(Enum):
    """Vaccination strategies."""
    NONE = auto()
    RANDOM = auto()
    RING = auto()  # Vaccinate contacts of infected
    TARGETED = auto()  # Vaccinate high-risk (FizzBuzz-adjacent)
    MASS = auto()  # Mass vaccination campaign


class ModelType(Enum):
    """Compartmental model types."""
    SIR = auto()
    SEIR = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SEIRState:
    """State of the SEIR model at a single time step."""
    time: float = 0.0
    susceptible: float = 0.0
    exposed: float = 0.0
    infected: float = 0.0
    recovered: float = 0.0
    vaccinated: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.susceptible + self.exposed + self.infected
            + self.recovered + self.vaccinated
        )

    @property
    def is_valid(self) -> bool:
        return (
            self.susceptible >= -1e-6
            and self.exposed >= -1e-6
            and self.infected >= -1e-6
            and self.recovered >= -1e-6
            and self.vaccinated >= -1e-6
        )


@dataclass
class R0Analysis:
    """Basic reproduction number analysis."""
    r0: float = 0.0
    beta: float = 0.0
    gamma: float = 0.0
    herd_immunity_threshold: float = 0.0
    epidemic_possible: bool = False
    doubling_time: float = 0.0


@dataclass
class ContactTracingResult:
    """Contact tracing analysis result."""
    index_case: int = 0
    contacts: list[int] = field(default_factory=list)
    secondary_cases: int = 0
    generation_time: float = 0.0
    trace_depth: int = 0


@dataclass
class VaccinationResult:
    """Vaccination strategy analysis result."""
    strategy: VaccinationStrategy = VaccinationStrategy.NONE
    coverage: float = 0.0
    efficacy: float = 0.0
    doses_required: int = 0
    herd_immunity_achieved: bool = False
    final_infected_fraction: float = 0.0


@dataclass
class EpidemiologyAnalysis:
    """Complete epidemiological analysis result."""
    model_type: ModelType = ModelType.SIR
    r0: R0Analysis = field(default_factory=R0Analysis)
    trajectory: list[SEIRState] = field(default_factory=list)
    peak_infected: float = 0.0
    peak_time: float = 0.0
    final_size: float = 0.0
    contact_tracing: ContactTracingResult = field(default_factory=ContactTracingResult)
    vaccination: VaccinationResult = field(default_factory=VaccinationResult)


# ---------------------------------------------------------------------------
# R0 Calculator
# ---------------------------------------------------------------------------


class R0Calculator:
    """Computes the basic reproduction number and derived quantities.

    R0 = beta / gamma for the SIR model, where beta is the transmission
    rate and gamma is the recovery rate. The herd immunity threshold
    is 1 - 1/R0, which gives the fraction of the population that must
    be immune to prevent epidemic spread.
    """

    def compute(self, beta: float, gamma: float) -> R0Analysis:
        """Compute R0 and derived quantities."""
        if gamma <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzepidemiology import (
                SEIRParameterError,
            )
            raise SEIRParameterError("gamma", gamma, "(0, inf)")

        if beta < 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzepidemiology import (
                SEIRParameterError,
            )
            raise SEIRParameterError("beta", beta, "[0, inf)")

        r0 = beta / gamma

        if r0 < 0 or not math.isfinite(r0):
            from enterprise_fizzbuzz.domain.exceptions.fizzepidemiology import (
                ReproductionNumberError,
            )
            raise ReproductionNumberError(r0, "non-physical value")

        if r0 > 1.0:
            hit = 1.0 - 1.0 / r0
            growth_rate = beta - gamma
            doubling = math.log(2.0) / growth_rate if growth_rate > 0 else float("inf")
        else:
            hit = 0.0
            doubling = float("inf")

        return R0Analysis(
            r0=r0,
            beta=beta,
            gamma=gamma,
            herd_immunity_threshold=hit,
            epidemic_possible=r0 > 1.0,
            doubling_time=doubling,
        )


# ---------------------------------------------------------------------------
# SIR/SEIR Solver
# ---------------------------------------------------------------------------


class CompartmentalSolver:
    """Solves SIR and SEIR models using Euler integration.

    The SIR model:
        dS/dt = -beta * S * I / N
        dI/dt = beta * S * I / N - gamma * I
        dR/dt = gamma * I

    The SEIR model adds:
        dE/dt = beta * S * I / N - sigma * E
        dI/dt = sigma * E - gamma * I
    """

    def solve_sir(
        self,
        population: float,
        initial_infected: float,
        beta: float,
        gamma: float,
        time_steps: int = DEFAULT_TIME_STEPS,
        dt: float = DEFAULT_DT,
    ) -> list[SEIRState]:
        """Solve the SIR model."""
        s = population - initial_infected
        i = initial_infected
        r = 0.0
        n = population

        trajectory: list[SEIRState] = []
        t = 0.0

        for step in range(time_steps):
            trajectory.append(SEIRState(
                time=t, susceptible=s, exposed=0.0,
                infected=i, recovered=r,
            ))

            ds = -beta * s * i / n * dt
            di = (beta * s * i / n - gamma * i) * dt
            dr = gamma * i * dt

            s += ds
            i += di
            r += dr
            t += dt

            # Clamp non-negative
            s = max(0.0, s)
            i = max(0.0, i)
            r = max(0.0, r)

        return trajectory

    def solve_seir(
        self,
        population: float,
        initial_exposed: float,
        beta: float,
        gamma: float,
        sigma: float,
        time_steps: int = DEFAULT_TIME_STEPS,
        dt: float = DEFAULT_DT,
    ) -> list[SEIRState]:
        """Solve the SEIR model."""
        if sigma <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzepidemiology import (
                SEIRParameterError,
            )
            raise SEIRParameterError("sigma", sigma, "(0, inf)")

        s = population - initial_exposed
        e = initial_exposed
        i = 0.0
        r = 0.0
        n = population

        trajectory: list[SEIRState] = []
        t = 0.0

        for step in range(time_steps):
            trajectory.append(SEIRState(
                time=t, susceptible=s, exposed=e,
                infected=i, recovered=r,
            ))

            ds = -beta * s * i / n * dt if n > 0 else 0.0
            de = (beta * s * i / n - sigma * e) * dt if n > 0 else 0.0
            di_val = (sigma * e - gamma * i) * dt
            dr = gamma * i * dt

            s += ds
            e += de
            i += di_val
            r += dr
            t += dt

            s = max(0.0, s)
            e = max(0.0, e)
            i = max(0.0, i)
            r = max(0.0, r)

        return trajectory


# ---------------------------------------------------------------------------
# Contact Tracing Engine
# ---------------------------------------------------------------------------


class ContactTracingEngine:
    """Traces contacts between FizzBuzz numbers.

    In the FizzBuzz epidemiological model, two numbers are "in contact"
    if they are within arithmetic distance delta of each other. A Fizz
    infection at number n can spread to any number in [n-delta, n+delta]
    that is also divisible by 3.
    """

    def trace(
        self,
        index_number: int,
        is_fizz: bool,
        is_buzz: bool,
        contact_radius: int = 5,
    ) -> ContactTracingResult:
        """Trace contacts from an index case."""
        contacts: list[int] = []

        for delta in range(-contact_radius, contact_radius + 1):
            if delta == 0:
                continue
            neighbor = index_number + delta

            if is_fizz and neighbor % 3 == 0:
                contacts.append(neighbor)
            elif is_buzz and neighbor % 5 == 0:
                contacts.append(neighbor)
            elif abs(neighbor - index_number) <= 2:
                contacts.append(neighbor)

        secondary = len([c for c in contacts if c % 3 == 0 or c % 5 == 0])

        return ContactTracingResult(
            index_case=index_number,
            contacts=contacts,
            secondary_cases=secondary,
            generation_time=1.0 / DEFAULT_GAMMA if DEFAULT_GAMMA > 0 else 10.0,
            trace_depth=1,
        )


# ---------------------------------------------------------------------------
# Vaccination Strategy Optimizer
# ---------------------------------------------------------------------------


class VaccinationOptimizer:
    """Optimizes vaccination strategies for FizzBuzz epidemics."""

    def evaluate_strategy(
        self,
        strategy: VaccinationStrategy,
        r0: float,
        population: int,
        efficacy: float = 0.95,
    ) -> VaccinationResult:
        """Evaluate a vaccination strategy."""
        if efficacy <= 0 or efficacy > 1.0:
            from enterprise_fizzbuzz.domain.exceptions.fizzepidemiology import (
                VaccinationStrategyError,
            )
            raise VaccinationStrategyError(
                strategy.name, f"efficacy must be in (0, 1], got {efficacy}"
            )

        if r0 <= 1.0:
            return VaccinationResult(
                strategy=strategy,
                coverage=0.0,
                efficacy=efficacy,
                doses_required=0,
                herd_immunity_achieved=True,
                final_infected_fraction=0.0,
            )

        hit = 1.0 - 1.0 / r0
        required_coverage = hit / efficacy

        coverage_multiplier = {
            VaccinationStrategy.NONE: 0.0,
            VaccinationStrategy.RANDOM: 0.6,
            VaccinationStrategy.RING: 0.8,
            VaccinationStrategy.TARGETED: 0.9,
            VaccinationStrategy.MASS: 1.0,
        }

        achieved_coverage = coverage_multiplier.get(strategy, 0.0) * required_coverage
        achieved_coverage = min(achieved_coverage, 1.0)

        doses = int(math.ceil(achieved_coverage * population))
        herd_achieved = achieved_coverage * efficacy >= hit

        final_infected = 0.0 if herd_achieved else (1.0 - achieved_coverage * efficacy) * 0.5

        return VaccinationResult(
            strategy=strategy,
            coverage=achieved_coverage,
            efficacy=efficacy,
            doses_required=doses,
            herd_immunity_achieved=herd_achieved,
            final_infected_fraction=final_infected,
        )


# ---------------------------------------------------------------------------
# Epidemiology Engine
# ---------------------------------------------------------------------------


class EpidemiologyEngine:
    """Integrates all epidemiological analysis components.

    Performs R0 estimation, SIR/SEIR simulation, contact tracing,
    and vaccination strategy evaluation for each FizzBuzz number.
    """

    def __init__(self) -> None:
        self.r0_calc = R0Calculator()
        self.solver = CompartmentalSolver()
        self.tracer = ContactTracingEngine()
        self.vax_optimizer = VaccinationOptimizer()
        self._analysis_count = 0

    def analyze_number(
        self, number: int, is_fizz: bool, is_buzz: bool
    ) -> EpidemiologyAnalysis:
        """Perform complete epidemiological analysis."""
        self._analysis_count += 1

        # Derive epidemic parameters from number
        beta = DEFAULT_BETA * (1.0 + 0.01 * (abs(number) % 20))
        gamma = DEFAULT_GAMMA * (1.0 + 0.005 * (abs(number) % 10))

        if is_fizz and is_buzz:
            beta *= 2.0  # FizzBuzz is highly transmissible
        elif is_fizz:
            beta *= 1.5
        elif is_buzz:
            beta *= 1.3

        # R0 analysis
        r0_result = self.r0_calc.compute(beta, gamma)

        # Run SIR simulation
        population = float(DEFAULT_POPULATION)
        initial_infected = max(1.0, float(abs(number) % 10))
        trajectory = self.solver.solve_sir(
            population, initial_infected, beta, gamma,
            time_steps=DEFAULT_TIME_STEPS, dt=DEFAULT_DT,
        )

        # Peak analysis
        peak_infected = 0.0
        peak_time = 0.0
        for state in trajectory:
            if state.infected > peak_infected:
                peak_infected = state.infected
                peak_time = state.time

        final_size = trajectory[-1].recovered / population if trajectory else 0.0

        # Contact tracing
        tracing = self.tracer.trace(number, is_fizz, is_buzz)

        # Vaccination
        strategy = VaccinationStrategy.TARGETED if is_fizz or is_buzz else VaccinationStrategy.RANDOM
        vaccination = self.vax_optimizer.evaluate_strategy(
            strategy, r0_result.r0, DEFAULT_POPULATION
        )

        return EpidemiologyAnalysis(
            model_type=ModelType.SIR,
            r0=r0_result,
            trajectory=trajectory,
            peak_infected=peak_infected,
            peak_time=peak_time,
            final_size=final_size,
            contact_tracing=tracing,
            vaccination=vaccination,
        )

    @property
    def analysis_count(self) -> int:
        return self._analysis_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class EpidemiologyMiddleware(IMiddleware):
    """Middleware that performs epidemiological analysis for each evaluation.

    Each number is modeled as a potential index case for a FizzBuzz
    epidemic. The R0, epidemic trajectory, contact network, and
    optimal vaccination strategy are computed and attached to the
    processing context.

    Priority 296 positions this in the physical sciences tier.
    """

    def __init__(self) -> None:
        self._engine = EpidemiologyEngine()
        self._evaluations = 0

    def get_name(self) -> str:
        return "fizzepidemiology"

    def get_priority(self) -> int:
        return 296

    @property
    def engine(self) -> EpidemiologyEngine:
        return self._engine

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            analysis = self._engine.analyze_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["epidemiology"] = {
                "r0": round(analysis.r0.r0, 4),
                "epidemic_possible": analysis.r0.epidemic_possible,
                "herd_immunity_threshold": round(analysis.r0.herd_immunity_threshold, 4),
                "peak_infected": round(analysis.peak_infected, 2),
                "peak_time": round(analysis.peak_time, 2),
                "final_size_fraction": round(analysis.final_size, 4),
                "contacts_traced": len(analysis.contact_tracing.contacts),
                "secondary_cases": analysis.contact_tracing.secondary_cases,
                "vaccination_strategy": analysis.vaccination.strategy.name,
                "herd_immunity_achieved": analysis.vaccination.herd_immunity_achieved,
            }

            logger.debug(
                "FizzEpidemiology: number=%d R0=%.2f peak=%.1f",
                number,
                analysis.r0.r0,
                analysis.peak_infected,
            )

        except Exception:
            logger.exception(
                "FizzEpidemiology: analysis failed for number %d", number
            )

        return result
