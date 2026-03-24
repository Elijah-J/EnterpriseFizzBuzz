"""
Enterprise FizzBuzz Platform - Smart Contract Exceptions (EFP-SC*)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SmartContractError(FizzBuzzError):
    """Base exception for all smart contract subsystem errors.

    The FizzContract VM requires a dedicated exception hierarchy to
    distinguish between compilation failures, deployment issues,
    execution errors, gas exhaustion, and governance violations.
    Each failure mode demands a different recovery strategy.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SC00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SmartContractCompilationError(SmartContractError):
    """Raised when the FizzSolidity compiler encounters a syntax or semantic error.

    Compilation errors prevent contract deployment and must be resolved
    before the FizzBuzz classification logic can be executed on-chain.
    The error includes the offending line number and a description of
    the issue to facilitate rapid debugging.
    """

    def __init__(self, reason: str, line: int) -> None:
        super().__init__(
            f"Compilation error at line {line}: {reason}",
            error_code="EFP-SC01",
            context={"reason": reason, "line": line},
        )
        self.reason = reason
        self.line = line


class SmartContractDeploymentError(SmartContractError):
    """Raised when contract deployment fails.

    Deployment failures can occur due to address collisions (statistically
    improbable with SHA-256), invalid bytecode, or insufficient deployer
    permissions. The contract address is included for diagnostic purposes.
    """

    def __init__(self, reason: str, address: str) -> None:
        super().__init__(
            f"Deployment failed at {address}: {reason}",
            error_code="EFP-SC02",
            context={"reason": reason, "address": address},
        )
        self.reason = reason
        self.address = address


class SmartContractExecutionError(SmartContractError):
    """Raised when contract execution encounters a runtime error.

    Runtime errors include invalid opcodes, missing contracts, and
    self-destructed contract access attempts. Unlike out-of-gas errors,
    execution errors indicate a defect in the contract logic itself.
    """

    def __init__(self, reason: str, address: str = "") -> None:
        super().__init__(
            f"Execution error{' at ' + address if address else ''}: {reason}",
            error_code="EFP-SC03",
            context={"reason": reason, "address": address},
        )
        self.reason = reason
        self.address = address


class SmartContractOutOfGasError(SmartContractError):
    """Raised when contract execution exhausts its gas allocation.

    Gas exhaustion triggers an automatic revert of all state changes
    made during the transaction, preserving storage consistency. The
    error includes the gas limit, gas consumed, and the opcode that
    caused the exhaustion, enabling precise gas estimation for future
    transactions.
    """

    def __init__(
        self, gas_limit: int, gas_used: int, opcode_name: str, gas_cost: int,
    ) -> None:
        super().__init__(
            f"Out of gas: {opcode_name} costs {gas_cost} gas, "
            f"but only {gas_limit - gas_used} remaining "
            f"(limit: {gas_limit}, used: {gas_used})",
            error_code="EFP-SC04",
            context={
                "gas_limit": gas_limit,
                "gas_used": gas_used,
                "opcode_name": opcode_name,
                "gas_cost": gas_cost,
            },
        )
        self.gas_limit = gas_limit
        self.gas_used = gas_used
        self.opcode_name = opcode_name
        self.gas_cost = gas_cost


class SmartContractStackOverflowError(SmartContractError):
    """Raised when the execution stack exceeds the 1024-depth limit.

    The stack depth limit prevents unbounded memory consumption during
    deeply nested computations. In practice, FizzBuzz classification
    should never approach this limit, but enterprise software must
    guard against all conceivable failure modes.
    """

    def __init__(self, depth: int) -> None:
        super().__init__(
            f"Stack overflow: maximum depth of {depth} exceeded",
            error_code="EFP-SC05",
            context={"depth": depth},
        )
        self.depth = depth


class SmartContractStackUnderflowError(SmartContractError):
    """Raised when an opcode attempts to pop from an empty stack.

    Stack underflow indicates a bytecode generation defect where an
    opcode expects more operands than are available. This is always
    a compiler bug or a hand-assembled bytecode error.
    """

    def __init__(self) -> None:
        super().__init__(
            "Stack underflow: attempted to pop from empty stack",
            error_code="EFP-SC06",
        )


class SmartContractInvalidJumpError(SmartContractError):
    """Raised when a JUMP or JUMPI targets a non-JUMPDEST instruction.

    The EVM requires all jump targets to be explicitly marked with
    JUMPDEST opcodes. This prevents arbitrary code execution by
    ensuring that control flow can only transfer to sanctioned
    program points.
    """

    def __init__(self, pc: int, destination: int) -> None:
        super().__init__(
            f"Invalid jump from PC={pc} to {destination}: "
            f"target is not a JUMPDEST",
            error_code="EFP-SC07",
            context={"pc": pc, "destination": destination},
        )
        self.pc = pc
        self.destination = destination


class SmartContractRevertError(SmartContractError):
    """Raised when a contract explicitly reverts execution.

    The REVERT opcode allows contracts to abort execution with an
    optional reason string, triggering a full state rollback. This
    is the contract's way of saying the transaction is invalid.
    """

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            f"Contract reverted{': ' + reason if reason else ''}",
            error_code="EFP-SC08",
            context={"reason": reason},
        )
        self.reason = reason


class SmartContractStorageError(SmartContractError):
    """Raised when a storage operation fails.

    Storage errors occur when accessing storage for a non-existent
    contract address or when storage quota limits are exceeded.
    """

    def __init__(self, reason: str, address: str = "") -> None:
        super().__init__(
            f"Storage error{' at ' + address if address else ''}: {reason}",
            error_code="EFP-SC09",
            context={"reason": reason, "address": address},
        )
        self.reason = reason
        self.address = address


class SmartContractGovernanceError(SmartContractError):
    """Raised when a governance operation violates protocol rules.

    Governance errors include unauthorized voting, double voting,
    attempting to execute non-passed proposals, and cancellation
    by non-proposers. The governance protocol is strict to prevent
    illegitimate modifications to the FizzBuzz rule set.
    """

    def __init__(self, reason: str, proposal_id: int) -> None:
        super().__init__(
            f"Governance error on proposal #{proposal_id}: {reason}",
            error_code="EFP-SC0A",
            context={"reason": reason, "proposal_id": proposal_id},
        )
        self.reason = reason
        self.proposal_id = proposal_id

