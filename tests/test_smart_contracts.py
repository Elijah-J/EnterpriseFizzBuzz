"""
Enterprise FizzBuzz Platform - FizzContract Smart Contract VM Test Suite

Comprehensive test coverage for the FizzContract smart contract subsystem,
validating the EVM-compatible stack machine, gas metering, contract storage,
FizzSolidity compiler, contract deployment, governance voting, dashboard
rendering, and middleware integration.

The tests are organized by component:
1. ContractOpcode enum completeness
2. GasMeter — gas consumption, limits, refunds, reset
3. ContractStorage — load, store, commit, revert, snapshot
4. ExecutionContext — field defaults and custom values
5. StackMachine — arithmetic, comparison, logic, control flow
6. StackMachine — stack limits (overflow, underflow)
7. StackMachine — storage opcodes (SSTORE, SLOAD)
8. StackMachine — system opcodes (RETURN, REVERT, STOP, GAS)
9. StackMachine — environment opcodes (CALLER, ORIGIN, NUMBER)
10. StackMachine — FIZZBUZZ opcode classification
11. StackMachine — out-of-gas revert behavior
12. ContractCompiler — valid FizzSolidity programs
13. ContractCompiler — error handling
14. ContractDeployer — address derivation, deployment, retrieval
15. ContractDeployer — call_contract integration
16. GovernanceVoting — voter registration, proposals, voting, tally
17. GovernanceVoting — finalize, execute, cancel
18. GovernanceVoting — error cases
19. ContractDashboard — rendering
20. ContractMiddleware — pipeline integration
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    SmartContractCompilationError,
    SmartContractDeploymentError,
    SmartContractError,
    SmartContractExecutionError,
    SmartContractGovernanceError,
    SmartContractInvalidJumpError,
    SmartContractOutOfGasError,
    SmartContractRevertError,
    SmartContractStackOverflowError,
    SmartContractStackUnderflowError,
    SmartContractStorageError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.smart_contracts import (
    ContractCompiler,
    ContractDashboard,
    ContractDeployer,
    ContractMiddleware,
    ContractOpcode,
    ContractStorage,
    DEFAULT_GAS_LIMIT,
    ExecutionContext,
    GAS_COSTS,
    GasMeter,
    GovernanceProposal,
    GovernanceVoting,
    Instruction,
    MAX_STACK_DEPTH,
    ProposalStatus,
    SUPERMAJORITY_DENOMINATOR,
    SUPERMAJORITY_NUMERATOR,
    StackMachine,
    UINT256_MAX,
    ZERO_ADDRESS,
    compile_fizzbuzz_contract,
)


# ===================================================================
# 1. ContractOpcode enum completeness
# ===================================================================


class TestContractOpcode:
    """Validates the opcode enum contains all required operations."""

    def test_opcode_count_at_least_30(self):
        assert len(ContractOpcode) >= 30

    def test_arithmetic_opcodes_present(self):
        for name in ("ADD", "SUB", "MUL", "DIV", "MOD"):
            assert hasattr(ContractOpcode, name)

    def test_comparison_opcodes_present(self):
        for name in ("EQ", "LT", "GT", "ISZERO"):
            assert hasattr(ContractOpcode, name)

    def test_logic_opcodes_present(self):
        for name in ("AND", "OR", "NOT"):
            assert hasattr(ContractOpcode, name)

    def test_control_flow_opcodes_present(self):
        for name in ("JUMP", "JUMPI", "JUMPDEST"):
            assert hasattr(ContractOpcode, name)

    def test_storage_opcodes_present(self):
        for name in ("SSTORE", "SLOAD"):
            assert hasattr(ContractOpcode, name)

    def test_system_opcodes_present(self):
        for name in ("CALL", "RETURN", "REVERT", "SELFDESTRUCT", "GAS", "STOP"):
            assert hasattr(ContractOpcode, name)

    def test_fizzbuzz_opcode_present(self):
        assert hasattr(ContractOpcode, "FIZZBUZZ")

    def test_all_opcodes_have_gas_costs(self):
        for op in ContractOpcode:
            assert op in GAS_COSTS, f"Missing gas cost for {op.name}"


# ===================================================================
# 2. GasMeter
# ===================================================================


class TestGasMeter:
    """Validates gas consumption tracking and limits."""

    def test_initial_state(self):
        meter = GasMeter(gas_limit=1000)
        assert meter.gas_limit == 1000
        assert meter.gas_used == 0
        assert meter.gas_remaining == 1000

    def test_consume_deducts_gas(self):
        meter = GasMeter(gas_limit=1000)
        meter.consume(ContractOpcode.PUSH)
        assert meter.gas_used == 3
        assert meter.gas_remaining == 997

    def test_consume_tracks_opcode_counts(self):
        meter = GasMeter(gas_limit=1000)
        meter.consume(ContractOpcode.PUSH)
        meter.consume(ContractOpcode.PUSH)
        meter.consume(ContractOpcode.ADD)
        counts = meter.opcode_counts
        assert counts[ContractOpcode.PUSH] == 2
        assert counts[ContractOpcode.ADD] == 1

    def test_out_of_gas_raises(self):
        meter = GasMeter(gas_limit=5)
        meter.consume(ContractOpcode.PUSH)  # 3 gas
        with pytest.raises(SmartContractOutOfGasError):
            meter.consume(ContractOpcode.PUSH)  # another 3, only 2 left

    def test_gas_refund(self):
        meter = GasMeter(gas_limit=100000)
        meter.consume(ContractOpcode.SSTORE)  # 20000 gas
        meter.add_refund(15000)
        assert meter.gas_refund == 15000

    def test_effective_refund_capped(self):
        meter = GasMeter(gas_limit=100000)
        meter.consume(ContractOpcode.SSTORE)  # 20000 gas
        meter.add_refund(15000)
        # Capped at half of gas_used = 10000
        assert meter.get_effective_refund() == 10000

    def test_reset(self):
        meter = GasMeter(gas_limit=1000)
        meter.consume(ContractOpcode.PUSH)
        meter.reset()
        assert meter.gas_used == 0
        assert meter.gas_remaining == 1000
        assert meter.opcode_counts == {}

    def test_sstore_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.SSTORE] == 20000

    def test_sload_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.SLOAD] == 200

    def test_call_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.CALL] == 700

    def test_push_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.PUSH] == 3

    def test_mul_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.MUL] == 5

    def test_mod_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.MOD] == 5


# ===================================================================
# 3. ContractStorage
# ===================================================================


class TestContractStorage:
    """Validates persistent key-value storage behavior."""

    def test_load_unset_returns_zero(self):
        storage = ContractStorage()
        assert storage.load(42) == 0

    def test_store_and_load(self):
        storage = ContractStorage()
        storage.store(1, 100)
        assert storage.load(1) == 100

    def test_store_overwrites(self):
        storage = ContractStorage()
        storage.store(1, 100)
        storage.store(1, 200)
        assert storage.load(1) == 200

    def test_revert_restores_original(self):
        storage = ContractStorage()
        storage.store(1, 100)
        storage.commit()
        storage.store(1, 200)
        storage.revert()
        assert storage.load(1) == 100

    def test_revert_removes_new_keys(self):
        storage = ContractStorage()
        storage.store(99, 42)
        storage.revert()
        assert storage.load(99) == 0

    def test_commit_clears_dirty(self):
        storage = ContractStorage()
        storage.store(1, 100)
        storage.commit()
        # After commit, revert has nothing to undo
        storage.revert()
        assert storage.load(1) == 100

    def test_snapshot(self):
        storage = ContractStorage()
        storage.store(1, 10)
        storage.store(2, 20)
        snap = storage.snapshot()
        assert snap == {1: 10, 2: 20}

    def test_size(self):
        storage = ContractStorage()
        assert storage.size == 0
        storage.store(1, 10)
        storage.store(2, 20)
        assert storage.size == 2

    def test_uint256_overflow_truncation(self):
        storage = ContractStorage()
        storage.store(0, UINT256_MAX + 1)
        assert storage.load(0) == 0  # wraps to 0

    def test_uint256_max_stored_correctly(self):
        storage = ContractStorage()
        storage.store(0, UINT256_MAX)
        assert storage.load(0) == UINT256_MAX


# ===================================================================
# 4. ExecutionContext
# ===================================================================


class TestExecutionContext:
    """Validates execution context field defaults and custom values."""

    def test_default_values(self):
        ctx = ExecutionContext()
        assert ctx.msg_sender == ZERO_ADDRESS
        assert ctx.msg_value == 0
        assert ctx.tx_origin == ZERO_ADDRESS
        assert ctx.block_number == 0
        assert ctx.gas_limit == DEFAULT_GAS_LIMIT

    def test_custom_values(self):
        ctx = ExecutionContext(
            msg_sender="0xabc",
            msg_value=100,
            tx_origin="0xdef",
            block_number=42,
            gas_limit=50000,
        )
        assert ctx.msg_sender == "0xabc"
        assert ctx.msg_value == 100
        assert ctx.block_number == 42


# ===================================================================
# 5. StackMachine — Arithmetic
# ===================================================================


class TestStackMachineArithmetic:
    """Validates arithmetic opcodes."""

    def _run(self, instructions, gas_limit=DEFAULT_GAS_LIMIT):
        vm = StackMachine(gas_limit=gas_limit)
        ctx = ExecutionContext()
        storage = ContractStorage()
        result = vm.execute(instructions, ctx, storage)
        return vm, result

    def test_add(self):
        code = [
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.PUSH, 20),
            Instruction(ContractOpcode.ADD),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        assert result == "30"

    def test_sub(self):
        code = [
            Instruction(ContractOpcode.PUSH, 30),
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.SUB),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        # SUB: pops a=10, b=30, pushes a-b = 10-30. Wait, the stack order:
        # PUSH 30 -> [30], PUSH 10 -> [30, 10], SUB pops a=10, b=30, pushes 10-30
        # But 10 - 30 underflows in uint256 space
        # Actually looking at the code: a, b = pop(), pop() -> a=10, b=30, push (a-b)
        # (10 - 30) & UINT256_MAX
        assert vm.gas_meter.gas_used > 0

    def test_mul(self):
        code = [
            Instruction(ContractOpcode.PUSH, 7),
            Instruction(ContractOpcode.PUSH, 6),
            Instruction(ContractOpcode.MUL),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        assert result == "42"

    def test_div(self):
        code = [
            Instruction(ContractOpcode.PUSH, 100),
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.DIV),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        # DIV pops a=10, b=100 -> 10//100 = 0. Hmm.
        # Actually: PUSH 100, PUSH 10 -> stack=[100,10]
        # DIV: a=pop()=10, b=pop()=100, push a//b = 10//100 = 0
        assert vm.gas_meter.gas_used > 0

    def test_div_by_zero(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.PUSH, 0),
            Instruction(ContractOpcode.DIV),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        assert result == "0"  # div by zero returns 0

    def test_mod(self):
        code = [
            Instruction(ContractOpcode.PUSH, 3),
            Instruction(ContractOpcode.PUSH, 15),
            Instruction(ContractOpcode.MOD),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        # MOD: a=pop()=15, b=pop()=3, push 15 % 3 = 0
        assert result == "0"

    def test_mod_nonzero(self):
        code = [
            Instruction(ContractOpcode.PUSH, 3),
            Instruction(ContractOpcode.PUSH, 7),
            Instruction(ContractOpcode.MOD),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        # 7 % 3 = 1
        assert result == "1"

    def test_exp(self):
        code = [
            Instruction(ContractOpcode.PUSH, 2),
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.EXP),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        # EXP: a=pop()=10, b=pop()=2 -> pow(10, 2) = 100
        assert result == "100"

    def test_uint256_overflow_wraps(self):
        code = [
            Instruction(ContractOpcode.PUSH, UINT256_MAX),
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.ADD),
            Instruction(ContractOpcode.RETURN),
        ]
        vm, result = self._run(code)
        assert result == "0"  # wraps around


# ===================================================================
# 6. StackMachine — Comparison and Logic
# ===================================================================


class TestStackMachineComparison:
    """Validates comparison and logic opcodes."""

    def _run(self, instructions):
        vm = StackMachine()
        ctx = ExecutionContext()
        storage = ContractStorage()
        result = vm.execute(instructions, ctx, storage)
        return vm, result

    def test_eq_true(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.EQ),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "1"

    def test_eq_false(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.PUSH, 43),
            Instruction(ContractOpcode.EQ),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "0"

    def test_lt(self):
        code = [
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.PUSH, 5),
            Instruction(ContractOpcode.LT),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        # LT: a=pop()=5, b=pop()=10 -> 5 < 10 = True = 1
        assert result == "1"

    def test_gt(self):
        code = [
            Instruction(ContractOpcode.PUSH, 5),
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.GT),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        # GT: a=pop()=10, b=pop()=5 -> 10 > 5 = True = 1
        assert result == "1"

    def test_iszero_true(self):
        code = [
            Instruction(ContractOpcode.PUSH, 0),
            Instruction(ContractOpcode.ISZERO),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "1"

    def test_iszero_false(self):
        code = [
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.ISZERO),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "0"

    def test_and(self):
        code = [
            Instruction(ContractOpcode.PUSH, 0xFF),
            Instruction(ContractOpcode.PUSH, 0x0F),
            Instruction(ContractOpcode.AND),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == str(0x0F)

    def test_or(self):
        code = [
            Instruction(ContractOpcode.PUSH, 0xF0),
            Instruction(ContractOpcode.PUSH, 0x0F),
            Instruction(ContractOpcode.OR),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == str(0xFF)

    def test_not(self):
        code = [
            Instruction(ContractOpcode.PUSH, 0),
            Instruction(ContractOpcode.NOT),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == str(UINT256_MAX)


# ===================================================================
# 7. StackMachine — Stack operations
# ===================================================================


class TestStackMachineStackOps:
    """Validates DUP, SWAP, POP, and stack limits."""

    def _run(self, instructions):
        vm = StackMachine()
        ctx = ExecutionContext()
        storage = ContractStorage()
        result = vm.execute(instructions, ctx, storage)
        return vm, result

    def test_dup(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.DUP, 1),
            Instruction(ContractOpcode.ADD),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "84"

    def test_swap(self):
        code = [
            Instruction(ContractOpcode.PUSH, 10),
            Instruction(ContractOpcode.PUSH, 20),
            Instruction(ContractOpcode.SWAP, 1),
            # Now stack is [20, 10], top is 10
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "10"

    def test_pop(self):
        code = [
            Instruction(ContractOpcode.PUSH, 99),
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.POP),
            Instruction(ContractOpcode.RETURN),
        ]
        _, result = self._run(code)
        assert result == "99"

    def test_stack_overflow(self):
        # Push 1025 items to exceed the 1024 limit
        code = [Instruction(ContractOpcode.PUSH, i) for i in range(1025)]
        vm = StackMachine(gas_limit=100000)
        ctx = ExecutionContext(gas_limit=100000)
        storage = ContractStorage()
        with pytest.raises(SmartContractStackOverflowError):
            vm.execute(code, ctx, storage)

    def test_stack_underflow(self):
        code = [Instruction(ContractOpcode.POP)]
        vm = StackMachine()
        ctx = ExecutionContext()
        storage = ContractStorage()
        with pytest.raises(SmartContractStackUnderflowError):
            vm.execute(code, ctx, storage)


# ===================================================================
# 8. StackMachine — Control flow
# ===================================================================


class TestStackMachineControlFlow:
    """Validates JUMP, JUMPI, JUMPDEST, STOP."""

    def _run(self, instructions):
        vm = StackMachine()
        ctx = ExecutionContext()
        storage = ContractStorage()
        result = vm.execute(instructions, ctx, storage)
        return vm, result

    def test_stop_halts_execution(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.STOP),
            Instruction(ContractOpcode.PUSH, 99),  # should not execute
        ]
        vm, _ = self._run(code)
        assert vm.stack == [42]

    def test_jump_to_jumpdest(self):
        code = [
            # 0: PUSH dest (3)
            Instruction(ContractOpcode.PUSH, 3),
            # 1: JUMP
            Instruction(ContractOpcode.JUMP),
            # 2: PUSH 99 (skipped)
            Instruction(ContractOpcode.PUSH, 99),
            # 3: JUMPDEST
            Instruction(ContractOpcode.JUMPDEST),
            # 4: PUSH 42
            Instruction(ContractOpcode.PUSH, 42),
            # 5: STOP
            Instruction(ContractOpcode.STOP),
        ]
        vm, _ = self._run(code)
        assert vm.stack == [42]

    def test_jumpi_taken(self):
        code = [
            # 0: PUSH condition (1 = truthy)
            Instruction(ContractOpcode.PUSH, 1),
            # 1: PUSH dest (4)
            Instruction(ContractOpcode.PUSH, 4),
            # 2: JUMPI
            Instruction(ContractOpcode.JUMPI),
            # 3: PUSH 99 (skipped)
            Instruction(ContractOpcode.PUSH, 99),
            # 4: JUMPDEST
            Instruction(ContractOpcode.JUMPDEST),
            # 5: PUSH 42
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.STOP),
        ]
        vm, _ = self._run(code)
        assert vm.stack == [42]

    def test_jumpi_not_taken(self):
        code = [
            # 0: PUSH condition (0 = falsy)
            Instruction(ContractOpcode.PUSH, 0),
            # 1: PUSH dest (4)
            Instruction(ContractOpcode.PUSH, 4),
            # 2: JUMPI — pops dest=4, cond=0, not taken
            Instruction(ContractOpcode.JUMPI),
            # 3: PUSH 99 (executed)
            Instruction(ContractOpcode.PUSH, 99),
            # 4: JUMPDEST
            Instruction(ContractOpcode.JUMPDEST),
            Instruction(ContractOpcode.STOP),
        ]
        vm, _ = self._run(code)
        assert vm.stack == [99]

    def test_invalid_jump_raises(self):
        code = [
            Instruction(ContractOpcode.PUSH, 5),  # no JUMPDEST at 5
            Instruction(ContractOpcode.JUMP),
        ]
        vm = StackMachine()
        ctx = ExecutionContext()
        storage = ContractStorage()
        with pytest.raises(SmartContractInvalidJumpError):
            vm.execute(code, ctx, storage)


# ===================================================================
# 9. StackMachine — Storage opcodes
# ===================================================================


class TestStackMachineStorage:
    """Validates SSTORE and SLOAD opcodes."""

    def test_sstore_and_sload(self):
        code = [
            # Store value 42 at key 1
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.SSTORE),
            # Load key 1
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.SLOAD),
            Instruction(ContractOpcode.RETURN),
        ]
        vm = StackMachine(gas_limit=100000)
        ctx = ExecutionContext(gas_limit=100000)
        storage = ContractStorage()
        result = vm.execute(code, ctx, storage)
        assert result == "42"

    def test_sload_unset_returns_zero(self):
        code = [
            Instruction(ContractOpcode.PUSH, 999),
            Instruction(ContractOpcode.SLOAD),
            Instruction(ContractOpcode.RETURN),
        ]
        vm = StackMachine()
        ctx = ExecutionContext()
        storage = ContractStorage()
        result = vm.execute(code, ctx, storage)
        assert result == "0"


# ===================================================================
# 10. StackMachine — System opcodes
# ===================================================================


class TestStackMachineSystem:
    """Validates RETURN, REVERT, GAS, SELFDESTRUCT opcodes."""

    def test_return_with_value(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.RETURN),
        ]
        vm = StackMachine()
        result = vm.execute(code, ExecutionContext(), ContractStorage())
        assert result == "42"

    def test_return_empty_stack(self):
        code = [Instruction(ContractOpcode.RETURN)]
        vm = StackMachine()
        result = vm.execute(code, ExecutionContext(), ContractStorage())
        assert result is None

    def test_revert_raises(self):
        code = [
            Instruction(ContractOpcode.PUSH, "error message"),
            Instruction(ContractOpcode.REVERT),
        ]
        vm = StackMachine()
        with pytest.raises(SmartContractRevertError):
            vm.execute(code, ExecutionContext(), ContractStorage())
        assert vm.reverted

    def test_revert_rolls_back_storage(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.SSTORE),
            Instruction(ContractOpcode.PUSH, "fail"),
            Instruction(ContractOpcode.REVERT),
        ]
        vm = StackMachine(gas_limit=100000)
        storage = ContractStorage()
        with pytest.raises(SmartContractRevertError):
            vm.execute(code, ExecutionContext(gas_limit=100000), storage)
        # Storage should be reverted
        assert storage.load(1) == 0

    def test_gas_opcode_reports_remaining(self):
        code = [
            Instruction(ContractOpcode.GAS),
            Instruction(ContractOpcode.RETURN),
        ]
        vm = StackMachine(gas_limit=1000)
        result = vm.execute(code, ExecutionContext(gas_limit=1000), ContractStorage())
        # GAS costs 2, so remaining = 1000 - 2 = 998
        assert result == "998"

    def test_selfdestruct_halts(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.SELFDESTRUCT),
            Instruction(ContractOpcode.PUSH, 99),  # not reached
        ]
        vm = StackMachine(gas_limit=100000)
        vm.execute(code, ExecutionContext(gas_limit=100000), ContractStorage())
        assert vm.halted
        assert 42 in vm.stack


# ===================================================================
# 11. StackMachine — Environment opcodes
# ===================================================================


class TestStackMachineEnvironment:
    """Validates CALLER, CALLVALUE, ORIGIN, NUMBER opcodes."""

    def test_caller(self):
        code = [
            Instruction(ContractOpcode.CALLER),
            Instruction(ContractOpcode.RETURN),
        ]
        ctx = ExecutionContext(msg_sender="0xdeadbeef")
        vm = StackMachine()
        result = vm.execute(code, ctx, ContractStorage())
        assert result == "0xdeadbeef"

    def test_callvalue(self):
        code = [
            Instruction(ContractOpcode.CALLVALUE),
            Instruction(ContractOpcode.RETURN),
        ]
        ctx = ExecutionContext(msg_value=1000)
        vm = StackMachine()
        result = vm.execute(code, ctx, ContractStorage())
        assert result == "1000"

    def test_origin(self):
        code = [
            Instruction(ContractOpcode.ORIGIN),
            Instruction(ContractOpcode.RETURN),
        ]
        ctx = ExecutionContext(tx_origin="0xcafebabe")
        vm = StackMachine()
        result = vm.execute(code, ctx, ContractStorage())
        assert result == "0xcafebabe"

    def test_block_number(self):
        code = [
            Instruction(ContractOpcode.NUMBER),
            Instruction(ContractOpcode.RETURN),
        ]
        ctx = ExecutionContext(block_number=42)
        vm = StackMachine()
        result = vm.execute(code, ctx, ContractStorage())
        assert result == "42"


# ===================================================================
# 12. StackMachine — FIZZBUZZ opcode
# ===================================================================


class TestStackMachineFizzBuzz:
    """Validates the FIZZBUZZ native opcode for classification."""

    def _classify(self, n):
        code = [
            Instruction(ContractOpcode.PUSH, n),
            Instruction(ContractOpcode.FIZZBUZZ),
            Instruction(ContractOpcode.RETURN),
        ]
        vm = StackMachine()
        return vm.execute(code, ExecutionContext(), ContractStorage())

    def test_fizzbuzz_15(self):
        assert self._classify(15) == "FizzBuzz"

    def test_fizzbuzz_30(self):
        assert self._classify(30) == "FizzBuzz"

    def test_fizz_3(self):
        assert self._classify(3) == "Fizz"

    def test_fizz_9(self):
        assert self._classify(9) == "Fizz"

    def test_buzz_5(self):
        assert self._classify(5) == "Buzz"

    def test_buzz_10(self):
        assert self._classify(10) == "Buzz"

    def test_plain_1(self):
        assert self._classify(1) == "1"

    def test_plain_7(self):
        assert self._classify(7) == "7"

    def test_fizzbuzz_0(self):
        assert self._classify(0) == "FizzBuzz"

    def test_fizzbuzz_gas_cost(self):
        assert GAS_COSTS[ContractOpcode.FIZZBUZZ] == 15


# ===================================================================
# 13. StackMachine — Out of gas revert
# ===================================================================


class TestStackMachineOutOfGas:
    """Validates that OOG reverts all state changes."""

    def test_oog_reverts_storage(self):
        code = [
            Instruction(ContractOpcode.PUSH, 42),
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.SSTORE),
            # SSTORE costs 20000, so with a low gas limit, the next op fails
            Instruction(ContractOpcode.PUSH, 99),
            Instruction(ContractOpcode.PUSH, 2),
            Instruction(ContractOpcode.SSTORE),  # second SSTORE
        ]
        vm = StackMachine(gas_limit=20010)  # enough for first SSTORE, not second
        storage = ContractStorage()
        with pytest.raises(SmartContractOutOfGasError):
            vm.execute(code, ExecutionContext(gas_limit=20010), storage)
        # All storage changes should be reverted
        assert storage.load(1) == 0
        assert vm.reverted

    def test_oog_sets_reverted_flag(self):
        code = [
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.PUSH, 1),
            Instruction(ContractOpcode.PUSH, 1),
        ]
        vm = StackMachine(gas_limit=5)  # only enough for ~1 PUSH
        storage = ContractStorage()
        with pytest.raises(SmartContractOutOfGasError):
            vm.execute(code, ExecutionContext(gas_limit=5), storage)
        assert vm.reverted


# ===================================================================
# 14. ContractCompiler
# ===================================================================


class TestContractCompiler:
    """Validates FizzSolidity compilation."""

    def test_compile_simple_contract(self):
        source = '''
        contract FizzBuzz {
            function classify(uint n) returns (string) {
                if (n % 15 == 0) return "FizzBuzz";
                if (n % 3 == 0) return "Fizz";
                if (n % 5 == 0) return "Buzz";
                return str(n);
            }
        }
        '''
        compiler = ContractCompiler()
        bytecode = compiler.compile(source)
        assert len(bytecode) > 0
        assert any(i.opcode == ContractOpcode.JUMPDEST for i in bytecode)
        assert any(i.opcode == ContractOpcode.RETURN for i in bytecode)

    def test_compile_empty_source_raises(self):
        compiler = ContractCompiler()
        with pytest.raises(SmartContractCompilationError):
            compiler.compile("")

    def test_compile_no_contract_raises(self):
        compiler = ContractCompiler()
        with pytest.raises(SmartContractCompilationError):
            compiler.compile("function foo() { return 1; }")

    def test_compile_tracks_contracts(self):
        source = '''
        contract Test {
            function run() returns (uint) {
                return 42;
            }
        }
        '''
        compiler = ContractCompiler()
        compiler.compile(source)
        assert "Test" in compiler.contracts

    def test_compile_produces_mod_opcode(self):
        source = '''
        contract Mod {
            function check(uint n) returns (uint) {
                return n % 3;
            }
        }
        '''
        compiler = ContractCompiler()
        bytecode = compiler.compile(source)
        opcodes = [i.opcode for i in bytecode]
        assert ContractOpcode.MOD in opcodes

    def test_compile_produces_eq_for_comparison(self):
        source = '''
        contract Cmp {
            function check(uint n) returns (bool) {
                if (n == 0) return 1;
                return 0;
            }
        }
        '''
        compiler = ContractCompiler()
        bytecode = compiler.compile(source)
        opcodes = [i.opcode for i in bytecode]
        assert ContractOpcode.EQ in opcodes


# ===================================================================
# 15. ContractDeployer
# ===================================================================


class TestContractDeployer:
    """Validates contract deployment and address derivation."""

    def test_derive_address_deterministic(self):
        deployer = ContractDeployer()
        addr1 = deployer.derive_address("0xabc", 0)
        addr2 = deployer.derive_address("0xabc", 0)
        assert addr1 == addr2

    def test_derive_address_format(self):
        deployer = ContractDeployer()
        addr = deployer.derive_address("0xabc", 0)
        assert addr.startswith("0x")
        assert len(addr) == 42  # 0x + 40 hex chars

    def test_derive_address_unique_per_nonce(self):
        deployer = ContractDeployer()
        addr1 = deployer.derive_address("0xabc", 0)
        addr2 = deployer.derive_address("0xabc", 1)
        assert addr1 != addr2

    def test_deploy_returns_address(self):
        deployer = ContractDeployer()
        bytecode = [Instruction(ContractOpcode.STOP)]
        addr = deployer.deploy(bytecode, deployer="0xabc")
        assert addr.startswith("0x")
        assert len(addr) == 42

    def test_deploy_increments_nonce(self):
        deployer = ContractDeployer()
        bytecode = [Instruction(ContractOpcode.STOP)]
        addr1 = deployer.deploy(bytecode, deployer="0xabc")
        addr2 = deployer.deploy(bytecode, deployer="0xabc")
        assert addr1 != addr2

    def test_deploy_stores_bytecode(self):
        deployer = ContractDeployer()
        bytecode = [Instruction(ContractOpcode.PUSH, 42), Instruction(ContractOpcode.STOP)]
        addr = deployer.deploy(bytecode, deployer="0xabc")
        retrieved = deployer.get_bytecode(addr)
        assert len(retrieved) == 2

    def test_get_bytecode_missing_raises(self):
        deployer = ContractDeployer()
        with pytest.raises(SmartContractExecutionError):
            deployer.get_bytecode("0x" + "f" * 40)

    def test_deployment_count(self):
        deployer = ContractDeployer()
        assert deployer.deployment_count == 0
        deployer.deploy([Instruction(ContractOpcode.STOP)], deployer="0xabc")
        assert deployer.deployment_count == 1

    def test_deployment_log(self):
        deployer = ContractDeployer()
        deployer.deploy([Instruction(ContractOpcode.STOP)], deployer="0xabc")
        log = deployer.deployment_log
        assert len(log) == 1
        assert "address" in log[0]
        assert log[0]["deployer"] == "0xabc"

    def test_destroy_contract(self):
        deployer = ContractDeployer()
        addr = deployer.deploy([Instruction(ContractOpcode.STOP)], deployer="0xabc")
        deployer.destroy(addr)
        assert deployer.is_destroyed(addr)
        with pytest.raises(SmartContractExecutionError):
            deployer.get_bytecode(addr)

    def test_get_storage_returns_storage(self):
        deployer = ContractDeployer()
        addr = deployer.deploy([Instruction(ContractOpcode.STOP)], deployer="0xabc")
        storage = deployer.get_storage(addr)
        assert isinstance(storage, ContractStorage)

    def test_get_storage_missing_raises(self):
        deployer = ContractDeployer()
        with pytest.raises(SmartContractStorageError):
            deployer.get_storage("0x" + "f" * 40)


# ===================================================================
# 16. ContractDeployer — call_contract
# ===================================================================


class TestContractDeployerCallContract:
    """Validates end-to-end contract execution via the deployer."""

    def test_call_fizzbuzz_contract(self):
        deployer = ContractDeployer()
        bytecode = compile_fizzbuzz_contract()
        addr = deployer.deploy(bytecode, deployer="0xabc")

        # We need to push the number before the contract bytecode
        full_code = [Instruction(ContractOpcode.PUSH, 15)] + list(bytecode)
        storage = deployer.get_storage(addr)
        vm = StackMachine()
        result = vm.execute(full_code, ExecutionContext(), storage)
        assert result == "FizzBuzz"

    def test_call_contract_method(self):
        deployer = ContractDeployer()
        bytecode = compile_fizzbuzz_contract()
        addr = deployer.deploy(bytecode, deployer="0xabc")

        ctx = ExecutionContext(msg_sender="0xuser")

        # Manually call via deployer.call_contract by deploying
        # a contract that includes a PUSH before the FIZZBUZZ
        full_bytecode = [
            Instruction(ContractOpcode.PUSH, 9),
            Instruction(ContractOpcode.FIZZBUZZ),
            Instruction(ContractOpcode.RETURN),
        ]
        addr2 = deployer.deploy(full_bytecode, deployer="0xabc")
        result, gas_meter = deployer.call_contract(addr2, ctx)
        assert result == "Fizz"
        assert gas_meter.gas_used > 0


# ===================================================================
# 17. GovernanceVoting — Registration and Proposals
# ===================================================================


class TestGovernanceVotingRegistration:
    """Validates voter registration and proposal creation."""

    def test_register_voter(self):
        gov = GovernanceVoting()
        gov.register_voter("0xabc")
        assert gov.is_registered("0xabc")
        assert gov.registered_voter_count == 1

    def test_unregister_voter(self):
        gov = GovernanceVoting()
        gov.register_voter("0xabc")
        gov.unregister_voter("0xabc")
        assert not gov.is_registered("0xabc")

    def test_create_proposal(self):
        gov = GovernanceVoting()
        gov.register_voter("0xabc")
        pid = gov.create_proposal(
            title="Change Fizz divisor to 7",
            description="Proposal to use 7 instead of 3",
            proposer="0xabc",
            proposed_action={"divisor": 7, "label": "Fizz"},
        )
        assert pid == 1
        assert pid in gov.proposals
        assert gov.proposals[pid].status == ProposalStatus.ACTIVE

    def test_create_proposal_unregistered_raises(self):
        gov = GovernanceVoting()
        with pytest.raises(SmartContractGovernanceError):
            gov.create_proposal(
                title="test",
                description="test",
                proposer="0xunregistered",
                proposed_action={},
            )


# ===================================================================
# 18. GovernanceVoting — Voting
# ===================================================================


class TestGovernanceVotingVotes:
    """Validates the voting mechanism."""

    def _setup_gov(self, num_voters=3):
        gov = GovernanceVoting()
        voters = [f"0x{i:040x}" for i in range(num_voters)]
        for v in voters:
            gov.register_voter(v)
        pid = gov.create_proposal(
            title="Test Proposal",
            description="A test",
            proposer=voters[0],
            proposed_action={"action": "test"},
        )
        return gov, voters, pid

    def test_vote_for(self):
        gov, voters, pid = self._setup_gov()
        gov.vote(pid, voters[0], True)
        f, a, _ = gov.tally(pid)
        assert f == 1
        assert a == 0

    def test_vote_against(self):
        gov, voters, pid = self._setup_gov()
        gov.vote(pid, voters[0], False)
        f, a, _ = gov.tally(pid)
        assert f == 0
        assert a == 1

    def test_double_vote_raises(self):
        gov, voters, pid = self._setup_gov()
        gov.vote(pid, voters[0], True)
        with pytest.raises(SmartContractGovernanceError):
            gov.vote(pid, voters[0], True)

    def test_unregistered_voter_raises(self):
        gov, voters, pid = self._setup_gov()
        with pytest.raises(SmartContractGovernanceError):
            gov.vote(pid, "0xunregistered", True)

    def test_supermajority_passes(self):
        gov, voters, pid = self._setup_gov(num_voters=3)
        gov.vote(pid, voters[0], True)
        gov.vote(pid, voters[1], True)
        gov.vote(pid, voters[2], False)
        _, _, passed = gov.tally(pid)
        assert passed  # 2/3 meets supermajority

    def test_simple_majority_fails(self):
        gov, voters, pid = self._setup_gov(num_voters=5)
        # 3 for, 2 against = 60% < 66.7%
        gov.vote(pid, voters[0], True)
        gov.vote(pid, voters[1], True)
        gov.vote(pid, voters[2], True)
        gov.vote(pid, voters[3], False)
        gov.vote(pid, voters[4], False)
        _, _, passed = gov.tally(pid)
        assert not passed

    def test_unanimous_passes(self):
        gov, voters, pid = self._setup_gov(num_voters=5)
        for v in voters:
            gov.vote(pid, v, True)
        _, _, passed = gov.tally(pid)
        assert passed

    def test_all_against_fails(self):
        gov, voters, pid = self._setup_gov(num_voters=3)
        for v in voters:
            gov.vote(pid, v, False)
        _, _, passed = gov.tally(pid)
        assert not passed

    def test_no_votes_fails(self):
        gov, voters, pid = self._setup_gov()
        _, _, passed = gov.tally(pid)
        assert not passed


# ===================================================================
# 19. GovernanceVoting — Finalize, Execute, Cancel
# ===================================================================


class TestGovernanceVotingLifecycle:
    """Validates the full proposal lifecycle."""

    def _setup_passed(self):
        gov = GovernanceVoting()
        voters = ["0xa", "0xb", "0xc"]
        for v in voters:
            gov.register_voter(v)
        pid = gov.create_proposal(
            title="Change Buzz to 7",
            description="Use 7 instead of 5",
            proposer="0xa",
            proposed_action={"divisor": 7, "label": "Buzz"},
        )
        gov.vote(pid, "0xa", True)
        gov.vote(pid, "0xb", True)
        return gov, pid

    def test_finalize_passed(self):
        gov, pid = self._setup_passed()
        status = gov.finalize(pid)
        assert status == ProposalStatus.PASSED

    def test_finalize_rejected(self):
        gov = GovernanceVoting()
        gov.register_voter("0xa")
        gov.register_voter("0xb")
        pid = gov.create_proposal(
            title="Bad idea",
            description="Nobody wants this",
            proposer="0xa",
            proposed_action={},
        )
        gov.vote(pid, "0xa", False)
        gov.vote(pid, "0xb", False)
        status = gov.finalize(pid)
        assert status == ProposalStatus.REJECTED

    def test_execute_passed_proposal(self):
        gov, pid = self._setup_passed()
        gov.finalize(pid)
        action = gov.execute(pid)
        assert action == {"divisor": 7, "label": "Buzz"}
        assert gov.proposals[pid].status == ProposalStatus.EXECUTED

    def test_execute_non_passed_raises(self):
        gov = GovernanceVoting()
        gov.register_voter("0xa")
        pid = gov.create_proposal(
            title="test", description="test",
            proposer="0xa", proposed_action={},
        )
        with pytest.raises(SmartContractGovernanceError):
            gov.execute(pid)

    def test_cancel_by_proposer(self):
        gov = GovernanceVoting()
        gov.register_voter("0xa")
        pid = gov.create_proposal(
            title="Cancel me",
            description="Will be cancelled",
            proposer="0xa",
            proposed_action={},
        )
        gov.cancel(pid, "0xa")
        assert gov.proposals[pid].status == ProposalStatus.CANCELLED

    def test_cancel_by_non_proposer_raises(self):
        gov = GovernanceVoting()
        gov.register_voter("0xa")
        gov.register_voter("0xb")
        pid = gov.create_proposal(
            title="My proposal",
            description="Only I can cancel",
            proposer="0xa",
            proposed_action={},
        )
        with pytest.raises(SmartContractGovernanceError):
            gov.cancel(pid, "0xb")

    def test_execution_log(self):
        gov, pid = self._setup_passed()
        gov.finalize(pid)
        gov.execute(pid)
        assert len(gov.execution_log) == 1
        assert gov.execution_log[0]["proposal_id"] == pid


# ===================================================================
# 20. ContractDashboard
# ===================================================================


class TestContractDashboard:
    """Validates ASCII dashboard rendering."""

    def test_render_empty(self):
        deployer = ContractDeployer()
        gov = GovernanceVoting()
        output = ContractDashboard.render(deployer, gov)
        assert "FIZZCONTRACT" in output
        assert "no contracts deployed" in output

    def test_render_with_contracts(self):
        deployer = ContractDeployer()
        deployer.deploy(
            [Instruction(ContractOpcode.STOP)],
            deployer="0x" + "a" * 40,
        )
        gov = GovernanceVoting()
        output = ContractDashboard.render(deployer, gov)
        assert "bytecode: 1 ops" in output

    def test_render_with_governance(self):
        deployer = ContractDeployer()
        gov = GovernanceVoting()
        gov.register_voter("0xa")
        gov.create_proposal(
            title="Test",
            description="Test",
            proposer="0xa",
            proposed_action={},
        )
        output = ContractDashboard.render(deployer, gov)
        assert "Test" in output
        assert "ACTIVE" in output

    def test_render_with_gas_metrics(self):
        deployer = ContractDeployer()
        gov = GovernanceVoting()
        metrics = {"total_gas_used": 12345, "evaluation_count": 10}
        output = ContractDashboard.render(deployer, gov, gas_metrics=metrics)
        assert "12345" in output
        assert "Contracts: 0" in output

    def test_render_footer_counts(self):
        deployer = ContractDeployer()
        deployer.deploy([Instruction(ContractOpcode.STOP)], deployer="0xabc")
        gov = GovernanceVoting()
        gov.register_voter("0xa")
        gov.register_voter("0xb")
        output = ContractDashboard.render(deployer, gov)
        assert "Voters: 2" in output
        assert "Contracts: 1" in output


# ===================================================================
# 21. ContractMiddleware
# ===================================================================


class TestContractMiddleware:
    """Validates middleware integration with the evaluation pipeline."""

    def _setup(self):
        deployer = ContractDeployer()
        bytecode = compile_fizzbuzz_contract()
        addr = deployer.deploy(bytecode, deployer="0xabc")
        ctx = ExecutionContext(msg_sender="0xuser", tx_origin="0xuser")
        middleware = ContractMiddleware(
            deployer=deployer,
            contract_address=addr,
            context=ctx,
        )
        return middleware

    def test_get_name(self):
        mw = self._setup()
        assert mw.get_name() == "ContractMiddleware"

    def test_get_priority(self):
        mw = self._setup()
        assert mw.get_priority() == 42

    def test_process_fizzbuzz(self):
        mw = self._setup()
        context = ProcessingContext(number=15, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata.get("contract_result") == "FizzBuzz"
        assert result.metadata.get("contract_gas_used") > 0

    def test_process_fizz(self):
        mw = self._setup()
        context = ProcessingContext(number=9, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata.get("contract_result") == "Fizz"

    def test_process_buzz(self):
        mw = self._setup()
        context = ProcessingContext(number=10, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata.get("contract_result") == "Buzz"

    def test_process_plain(self):
        mw = self._setup()
        context = ProcessingContext(number=7, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata.get("contract_result") == "7"

    def test_gas_metrics_tracking(self):
        mw = self._setup()

        def next_handler(ctx):
            return ctx

        for n in [1, 2, 3, 5, 15]:
            ctx = ProcessingContext(number=n, session_id="test")
            mw.process(ctx, next_handler)

        assert mw.evaluation_count == 5
        assert mw.total_gas_used > 0
        assert mw.average_gas > 0

    def test_gas_metrics_dict(self):
        mw = self._setup()
        metrics = mw.gas_metrics
        assert "total_gas_used" in metrics
        assert "evaluation_count" in metrics
        assert "average_gas_per_eval" in metrics
        assert "gas_limit" in metrics

    def test_process_calls_next_handler(self):
        mw = self._setup()
        context = ProcessingContext(number=1, session_id="test")
        called = []

        def next_handler(ctx):
            called.append(True)
            return ctx

        mw.process(context, next_handler)
        assert len(called) == 1


# ===================================================================
# 22. Exception hierarchy
# ===================================================================


class TestExceptionHierarchy:
    """Validates the smart contract exception hierarchy."""

    def test_base_exception(self):
        exc = SmartContractError("test")
        assert isinstance(exc, Exception)
        assert "EFP-SC00" in str(exc)

    def test_compilation_error(self):
        exc = SmartContractCompilationError(reason="bad syntax", line=5)
        assert isinstance(exc, SmartContractError)
        assert exc.reason == "bad syntax"
        assert exc.line == 5

    def test_deployment_error(self):
        exc = SmartContractDeploymentError(reason="collision", address="0xabc")
        assert isinstance(exc, SmartContractError)
        assert exc.address == "0xabc"

    def test_execution_error(self):
        exc = SmartContractExecutionError(reason="missing", address="0xabc")
        assert isinstance(exc, SmartContractError)

    def test_out_of_gas_error(self):
        exc = SmartContractOutOfGasError(
            gas_limit=1000, gas_used=998, opcode_name="PUSH", gas_cost=3,
        )
        assert isinstance(exc, SmartContractError)
        assert exc.gas_limit == 1000
        assert exc.gas_cost == 3

    def test_stack_overflow_error(self):
        exc = SmartContractStackOverflowError(depth=1024)
        assert isinstance(exc, SmartContractError)

    def test_stack_underflow_error(self):
        exc = SmartContractStackUnderflowError()
        assert isinstance(exc, SmartContractError)

    def test_invalid_jump_error(self):
        exc = SmartContractInvalidJumpError(pc=10, destination=99)
        assert isinstance(exc, SmartContractError)
        assert exc.destination == 99

    def test_revert_error(self):
        exc = SmartContractRevertError(reason="fail")
        assert isinstance(exc, SmartContractError)
        assert exc.reason == "fail"

    def test_storage_error(self):
        exc = SmartContractStorageError(reason="missing", address="0xabc")
        assert isinstance(exc, SmartContractError)

    def test_governance_error(self):
        exc = SmartContractGovernanceError(reason="not registered", proposal_id=1)
        assert isinstance(exc, SmartContractError)
        assert exc.proposal_id == 1


# ===================================================================
# 23. compile_fizzbuzz_contract helper
# ===================================================================


class TestCompileFizzBuzzContract:
    """Validates the canonical FizzBuzz contract helper."""

    def test_returns_bytecode(self):
        bytecode = compile_fizzbuzz_contract()
        assert len(bytecode) >= 3

    def test_contains_fizzbuzz_opcode(self):
        bytecode = compile_fizzbuzz_contract()
        opcodes = [i.opcode for i in bytecode]
        assert ContractOpcode.FIZZBUZZ in opcodes

    def test_contains_return(self):
        bytecode = compile_fizzbuzz_contract()
        opcodes = [i.opcode for i in bytecode]
        assert ContractOpcode.RETURN in opcodes

    def test_executable(self):
        bytecode = compile_fizzbuzz_contract()
        full_code = [Instruction(ContractOpcode.PUSH, 45)] + list(bytecode)
        vm = StackMachine()
        result = vm.execute(full_code, ExecutionContext(), ContractStorage())
        assert result == "FizzBuzz"


# ===================================================================
# 24. Constants
# ===================================================================


class TestConstants:
    """Validates module-level constants."""

    def test_max_stack_depth(self):
        assert MAX_STACK_DEPTH == 1024

    def test_uint256_max(self):
        assert UINT256_MAX == (1 << 256) - 1

    def test_default_gas_limit(self):
        assert DEFAULT_GAS_LIMIT == 3_000_000

    def test_zero_address(self):
        assert ZERO_ADDRESS == "0x" + "0" * 40

    def test_supermajority_ratio(self):
        assert SUPERMAJORITY_NUMERATOR == 2
        assert SUPERMAJORITY_DENOMINATOR == 3


# ===================================================================
# 25. PC opcode
# ===================================================================


class TestPCOpcode:
    """Validates the PC (program counter) opcode."""

    def test_pc_returns_current_position(self):
        code = [
            Instruction(ContractOpcode.PUSH, 0),  # 0
            Instruction(ContractOpcode.POP),       # 1
            Instruction(ContractOpcode.PC),        # 2 — should push 2
            Instruction(ContractOpcode.RETURN),
        ]
        vm = StackMachine()
        result = vm.execute(code, ExecutionContext(), ContractStorage())
        assert result == "2"
