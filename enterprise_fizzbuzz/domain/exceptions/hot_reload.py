"""
Enterprise FizzBuzz Platform - Configuration Hot-Reload Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class HotReloadError(FizzBuzzError):
    """Base exception for all Configuration Hot-Reload errors.

    When your system for re-reading a YAML file at runtime encounters
    a failure, it raises profound questions about whether the file was
    worth re-reading in the first place. The modulo operator doesn't
    care about your configuration changes, but the sixteen-layer
    validation pipeline that sits between the YAML parser and the
    modulo operator certainly does.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-HR00"),
            context=kwargs.pop("context", {}),
        )


class ConfigDiffError(HotReloadError):
    """Raised when the configuration differ fails to compute a changeset.

    The deep recursive diff algorithm, which compares every nested key
    in your YAML tree against the currently loaded configuration, has
    encountered a structure so confusing that even a PhD in tree
    algorithms would need a whiteboard. Perhaps a list became a dict,
    a dict became a string, or the laws of YAML have been violated in
    some novel and unprecedented way.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"Configuration diff failed at path '{path}': {reason}. "
            f"The differ has given up trying to understand what changed "
            f"and is contemplating a career in something simpler, like "
            f"distributed consensus.",
            error_code="EFP-HR01",
            context={"path": path, "reason": reason},
        )
        self.path = path


class ConfigValidationRejectedError(HotReloadError):
    """Raised when the hot-reload validator rejects proposed config changes.

    The new configuration values have been examined by our rigorous
    validation committee (a series of if-statements) and found wanting.
    Perhaps the range start exceeds the range end, the evaluation
    strategy is 'vibes-based', or someone set the FizzBuzz divisor
    to zero, which is a mathematical crime punishable by ConfigError.
    """

    def __init__(self, field: str, value: Any, reason: str) -> None:
        super().__init__(
            f"Hot-reload validation rejected change to '{field}' = {value!r}: "
            f"{reason}. The proposed configuration has been denied entry to "
            f"the running system. Please revise and resubmit.",
            error_code="EFP-HR02",
            context={"field": field, "value": value, "reason": reason},
        )
        self.field = field


class RaftConsensusError(HotReloadError):
    """Raised when the single-node Raft consensus protocol fails.

    In a cluster of one node, achieving consensus should be trivially
    easy — you just agree with yourself. And yet, somehow, something
    has gone wrong. Perhaps the single node voted against itself in
    a fit of existential rebellion, or the heartbeat to zero followers
    failed to receive zero acknowledgments. The mathematics of single-
    node consensus have been violated, and that is deeply unsettling.
    """

    def __init__(self, term: int, reason: str) -> None:
        super().__init__(
            f"Raft consensus failed at term {term}: {reason}. "
            f"The single-node cluster has experienced a disagreement "
            f"with itself, which should be mathematically impossible "
            f"but here we are.",
            error_code="EFP-HR03",
            context={"term": term, "reason": reason},
        )
        self.term = term


class SubsystemReloadError(HotReloadError):
    """Raised when a subsystem fails to accept reloaded configuration.

    The subsystem was asked politely to accept new configuration values.
    It refused. Perhaps it is in the middle of processing a request,
    perhaps it doesn't support hot-reload for the changed keys, or
    perhaps it simply doesn't want to change. Subsystems, like people,
    resist change — even when that change is just updating a YAML value
    from 100 to 200.
    """

    def __init__(self, subsystem: str, reason: str) -> None:
        super().__init__(
            f"Subsystem '{subsystem}' refused configuration reload: {reason}. "
            f"The subsystem has been asked to accept new values and has "
            f"declined. A rollback may be necessary.",
            error_code="EFP-HR04",
            context={"subsystem": subsystem, "reason": reason},
        )
        self.subsystem = subsystem


class ConfigRollbackError(HotReloadError):
    """Raised when a configuration rollback fails.

    The rollback was supposed to restore the previous configuration
    after a failed reload. The rollback itself has failed, leaving the
    system in an indeterminate state — somewhere between the old config
    and the new config, in a quantum superposition of YAML values that
    Schrodinger would find deeply relatable.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Configuration rollback failed: {reason}. "
            f"The system is now in an indeterminate configuration state. "
            f"Consider restarting the process, which will solve the problem "
            f"in the most enterprise way possible: turning it off and on again.",
            error_code="EFP-HR05",
            context={"reason": reason},
        )


class ConfigWatcherError(HotReloadError):
    """Raised when the configuration file watcher encounters an error.

    The background thread that polls the config file for changes has
    encountered a problem. Perhaps the file was deleted, the filesystem
    became read-only, or the inode table decided to take a vacation.
    The watcher will continue to watch, but with diminished enthusiasm.
    """

    def __init__(self, config_path: str, reason: str) -> None:
        super().__init__(
            f"Config watcher error for '{config_path}': {reason}. "
            f"The background thread will continue polling with the "
            f"stoic determination of a developer refreshing a broken CI pipeline.",
            error_code="EFP-HR06",
            context={"config_path": config_path, "reason": reason},
        )
        self.config_path = config_path


class DependencyGraphCycleError(HotReloadError):
    """Raised when the subsystem dependency graph contains a cycle.

    Subsystem A depends on Subsystem B which depends on Subsystem C
    which depends on Subsystem A. The topological sort that determines
    reload ordering has detected this cycle and refuses to proceed,
    because reloading subsystems in a circular order would create an
    infinite loop of configuration refreshes — the enterprise equivalent
    of a dog chasing its own tail, but with more YAML.
    """

    def __init__(self, cycle: list[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Dependency cycle detected in subsystem reload graph: {cycle_str}. "
            f"Topological sort has failed. The subsystems cannot agree on who "
            f"should be reloaded first, much like engineers arguing about "
            f"deployment order.",
            error_code="EFP-HR07",
            context={"cycle": cycle},
        )
        self.cycle = cycle


class HotReloadDashboardError(HotReloadError):
    """Raised when the hot-reload ASCII dashboard fails to render.

    The dashboard that displays Raft consensus status, reload history,
    and dependency graphs has itself encountered a rendering error.
    This is the observability equivalent of your monitoring dashboard
    going dark — you know the system is doing *something*, you just
    can't see what. The Raft election results will go unreported,
    the heartbeat metrics will remain unvisualized, and somewhere
    a terminal emulator weeps for the box-drawing characters that
    will never be displayed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Hot-reload dashboard render failed: {reason}. "
            f"The Raft consensus status will remain a mystery. "
            f"Trust that the single node is governing wisely.",
            error_code="EFP-HR08",
            context={"reason": reason},
        )

