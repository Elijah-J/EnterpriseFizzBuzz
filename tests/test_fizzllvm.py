"""
Enterprise FizzBuzz Platform - FizzLLVM Tests

Validates the FizzLLVM intermediate representation compiler, optimization
pass framework, textual IR emission, dashboard rendering, and middleware
integration. A production-grade compiler infrastructure demands rigorous
verification of every stage from IR construction through optimization to
final emission.
"""

import unittest

from enterprise_fizzbuzz.domain.exceptions.fizzllvm import (
    FizzLLVMError,
    FizzLLVMNotFoundError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.fizzllvm import (
    FIZZLLVM_VERSION,
    MIDDLEWARE_PRIORITY,
    BasicBlock,
    FizzLLVMDashboard,
    FizzLLVMMiddleware,
    IRCompiler,
    IRFunction,
    IRInstruction,
    IRModule,
    IROpcode,
    OptimizationPass,
    create_fizzllvm_subsystem,
)


class TestFizzLLVMConstants(unittest.TestCase):
    """Verify module-level constants that downstream consumers depend on."""

    def test_version_string(self) -> None:
        """The module version must be 1.0.0."""
        self.assertEqual(FIZZLLVM_VERSION, "1.0.0")

    def test_middleware_priority(self) -> None:
        """Middleware priority must be 228 per the subsystem registry."""
        self.assertEqual(MIDDLEWARE_PRIORITY, 228)


class TestIROpcode(unittest.TestCase):
    """Tests for the IR opcode enumeration."""

    def test_all_opcodes_present(self) -> None:
        """All thirteen opcodes required by the ISA must be defined."""
        expected = {
            "ADD", "SUB", "MUL", "DIV", "MOD", "CMP",
            "BR", "RET", "LOAD", "STORE", "CALL", "PHI", "ALLOCA",
        }
        actual = {op.name for op in IROpcode}
        self.assertEqual(expected, actual)

    def test_opcode_count(self) -> None:
        """The ISA specifies exactly thirteen opcodes."""
        self.assertEqual(len(IROpcode), 13)


class TestOptimizationPass(unittest.TestCase):
    """Tests for the optimization pass enumeration."""

    def test_all_passes_present(self) -> None:
        """All four optimization passes must be defined."""
        expected = {
            "DEAD_CODE_ELIMINATION",
            "CONSTANT_FOLDING",
            "COMMON_SUBEXPRESSION",
            "INLINE",
        }
        actual = {p.name for p in OptimizationPass}
        self.assertEqual(expected, actual)

    def test_pass_count(self) -> None:
        """Exactly four optimization passes must exist."""
        self.assertEqual(len(OptimizationPass), 4)


class TestIRDataclasses(unittest.TestCase):
    """Tests for the IR data model: instructions, blocks, functions, modules."""

    def test_instruction_fields(self) -> None:
        """IRInstruction stores opcode, destination, operands, and label."""
        instr = IRInstruction(
            opcode=IROpcode.ADD, dest="%0", operands=["%1", "%2"], label=""
        )
        self.assertEqual(instr.opcode, IROpcode.ADD)
        self.assertEqual(instr.dest, "%0")
        self.assertEqual(instr.operands, ["%1", "%2"])
        self.assertEqual(instr.label, "")

    def test_basic_block_holds_instructions(self) -> None:
        """A basic block aggregates a named sequence of instructions."""
        i1 = IRInstruction(opcode=IROpcode.LOAD, dest="%0", operands=["n"])
        i2 = IRInstruction(opcode=IROpcode.RET, dest="%0", operands=["%0"])
        block = BasicBlock(name="entry", instructions=[i1, i2])
        self.assertEqual(block.name, "entry")
        self.assertEqual(len(block.instructions), 2)

    def test_function_holds_blocks_and_params(self) -> None:
        """An IR function stores its name, basic blocks, and parameters."""
        block = BasicBlock(name="entry", instructions=[])
        func = IRFunction(name="fizz_check", blocks=[block], params=["n"])
        self.assertEqual(func.name, "fizz_check")
        self.assertEqual(func.params, ["n"])
        self.assertEqual(len(func.blocks), 1)

    def test_module_holds_functions(self) -> None:
        """An IR module aggregates functions under a named unit."""
        func = IRFunction(name="main", blocks=[], params=[])
        mod = IRModule(module_id="mod-1", name="fizzbuzz", functions=[func])
        self.assertEqual(mod.module_id, "mod-1")
        self.assertEqual(mod.name, "fizzbuzz")
        self.assertEqual(len(mod.functions), 1)


class TestIRCompilerModuleManagement(unittest.TestCase):
    """Tests for creating, retrieving, and listing IR modules."""

    def setUp(self) -> None:
        self.compiler = IRCompiler()

    def test_create_module(self) -> None:
        """create_module returns an IRModule with the given name."""
        mod = self.compiler.create_module("test_mod")
        self.assertIsInstance(mod, IRModule)
        self.assertEqual(mod.name, "test_mod")
        self.assertTrue(len(mod.module_id) > 0)

    def test_get_module(self) -> None:
        """get_module retrieves a previously created module by ID."""
        mod = self.compiler.create_module("retrieval_test")
        retrieved = self.compiler.get_module(mod.module_id)
        self.assertEqual(retrieved.module_id, mod.module_id)
        self.assertEqual(retrieved.name, "retrieval_test")

    def test_get_module_not_found(self) -> None:
        """get_module raises FizzLLVMNotFoundError for unknown IDs."""
        with self.assertRaises(FizzLLVMNotFoundError):
            self.compiler.get_module("nonexistent-id")

    def test_list_modules(self) -> None:
        """list_modules returns all created modules."""
        self.compiler.create_module("alpha")
        self.compiler.create_module("beta")
        modules = self.compiler.list_modules()
        names = {m.name for m in modules}
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertEqual(len(modules), 2)


class TestIRCompilerFunctionAndBlock(unittest.TestCase):
    """Tests for adding functions and basic blocks to modules."""

    def setUp(self) -> None:
        self.compiler = IRCompiler()
        self.mod = self.compiler.create_module("fb_module")

    def test_add_function(self) -> None:
        """add_function attaches a named function with parameters."""
        func = self.compiler.add_function(self.mod.module_id, "is_fizz", ["n"])
        self.assertIsInstance(func, IRFunction)
        self.assertEqual(func.name, "is_fizz")
        self.assertEqual(func.params, ["n"])

    def test_add_block(self) -> None:
        """add_block creates a named basic block inside a function."""
        self.compiler.add_function(self.mod.module_id, "check", ["x"])
        block = self.compiler.add_block(self.mod.module_id, "check", "entry")
        self.assertIsInstance(block, BasicBlock)
        self.assertEqual(block.name, "entry")

    def test_add_instruction(self) -> None:
        """add_instruction appends an instruction to the specified block."""
        self.compiler.add_function(self.mod.module_id, "compute", ["a", "b"])
        self.compiler.add_block(self.mod.module_id, "compute", "body")
        instr = self.compiler.add_instruction(
            self.mod.module_id, "compute", "body",
            IROpcode.ADD, "%result", ["%a", "%b"],
        )
        self.assertIsInstance(instr, IRInstruction)
        self.assertEqual(instr.opcode, IROpcode.ADD)
        self.assertEqual(instr.dest, "%result")


class TestIRCompilerOptimization(unittest.TestCase):
    """Tests for the optimization pass pipeline."""

    def setUp(self) -> None:
        self.compiler = IRCompiler()
        self.mod = self.compiler.create_module("opt_target")
        self.compiler.add_function(self.mod.module_id, "f", ["n"])
        self.compiler.add_block(self.mod.module_id, "f", "entry")
        self.compiler.add_instruction(
            self.mod.module_id, "f", "entry",
            IROpcode.LOAD, "%0", ["n"],
        )
        self.compiler.add_instruction(
            self.mod.module_id, "f", "entry",
            IROpcode.MOD, "%1", ["%0", "3"],
        )
        self.compiler.add_instruction(
            self.mod.module_id, "f", "entry",
            IROpcode.RET, "%1", ["%1"],
        )

    def test_optimize_returns_module(self) -> None:
        """optimize returns the optimized IRModule."""
        result = self.compiler.optimize(
            self.mod.module_id, [OptimizationPass.DEAD_CODE_ELIMINATION]
        )
        self.assertIsInstance(result, IRModule)

    def test_optimize_with_multiple_passes(self) -> None:
        """Multiple optimization passes can be applied in sequence."""
        result = self.compiler.optimize(
            self.mod.module_id,
            [
                OptimizationPass.CONSTANT_FOLDING,
                OptimizationPass.DEAD_CODE_ELIMINATION,
                OptimizationPass.COMMON_SUBEXPRESSION,
            ],
        )
        self.assertIsInstance(result, IRModule)

    def test_optimize_nonexistent_module_raises(self) -> None:
        """Optimizing a nonexistent module raises FizzLLVMNotFoundError."""
        with self.assertRaises(FizzLLVMNotFoundError):
            self.compiler.optimize("ghost-module", [OptimizationPass.INLINE])


class TestIRCompilerEmission(unittest.TestCase):
    """Tests for the textual IR emission backend."""

    def setUp(self) -> None:
        self.compiler = IRCompiler()
        self.mod = self.compiler.create_module("emit_test")
        self.compiler.add_function(self.mod.module_id, "fizz", ["n"])
        self.compiler.add_block(self.mod.module_id, "fizz", "entry")
        self.compiler.add_instruction(
            self.mod.module_id, "fizz", "entry",
            IROpcode.LOAD, "%0", ["n"],
        )
        self.compiler.add_instruction(
            self.mod.module_id, "fizz", "entry",
            IROpcode.RET, "%0", ["%0"],
        )

    def test_emit_ir_returns_string(self) -> None:
        """emit_ir must return a non-empty string representation."""
        ir_text = self.compiler.emit_ir(self.mod.module_id)
        self.assertIsInstance(ir_text, str)
        self.assertTrue(len(ir_text) > 0)

    def test_emit_ir_contains_function_name(self) -> None:
        """The emitted IR must reference the function by name."""
        ir_text = self.compiler.emit_ir(self.mod.module_id)
        self.assertIn("fizz", ir_text)

    def test_emit_ir_nonexistent_module_raises(self) -> None:
        """Emitting IR for a nonexistent module raises FizzLLVMNotFoundError."""
        with self.assertRaises(FizzLLVMNotFoundError):
            self.compiler.emit_ir("no-such-module")


class TestFizzLLVMDashboard(unittest.TestCase):
    """Tests for the operational dashboard rendering."""

    def test_render_returns_string(self) -> None:
        """The dashboard must render to a non-empty string."""
        dashboard = FizzLLVMDashboard()
        output = dashboard.render()
        self.assertIsInstance(output, str)
        self.assertTrue(len(output) > 0)

    def test_render_contains_header(self) -> None:
        """The dashboard output must contain an identifiable header."""
        dashboard = FizzLLVMDashboard()
        output = dashboard.render()
        self.assertTrue(
            "fizzllvm" in output.lower() or "llvm" in output.lower(),
            "Dashboard must reference the FizzLLVM subsystem",
        )


class TestFizzLLVMMiddleware(unittest.TestCase):
    """Tests for the FizzLLVM middleware integration."""

    def setUp(self) -> None:
        self.middleware = FizzLLVMMiddleware()

    def test_implements_imiddleware(self) -> None:
        """FizzLLVMMiddleware must implement the IMiddleware interface."""
        self.assertIsInstance(self.middleware, IMiddleware)

    def test_get_name(self) -> None:
        """Middleware name must be 'fizzllvm'."""
        self.assertEqual(self.middleware.get_name(), "fizzllvm")

    def test_get_priority(self) -> None:
        """Middleware priority must equal the module constant (228)."""
        self.assertEqual(self.middleware.get_priority(), MIDDLEWARE_PRIORITY)
        self.assertEqual(self.middleware.get_priority(), 228)

    def test_process_delegates_to_next(self) -> None:
        """The middleware must invoke the next handler in the pipeline."""
        ctx = ProcessingContext(number=15, session_id="llvm-test")
        called = {"value": False}

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            called["value"] = True
            return c

        result = self.middleware.process(ctx, next_handler)
        self.assertTrue(called["value"], "Middleware must delegate to next handler")
        self.assertIsInstance(result, ProcessingContext)


class TestCreateFizzLLVMSubsystem(unittest.TestCase):
    """Tests for the subsystem factory function."""

    def test_factory_returns_triple(self) -> None:
        """create_fizzllvm_subsystem must return compiler, dashboard, middleware."""
        result = create_fizzllvm_subsystem()
        self.assertEqual(len(result), 3)

    def test_factory_component_types(self) -> None:
        """The factory must return correctly typed components."""
        compiler, dashboard, middleware = create_fizzllvm_subsystem()
        self.assertIsInstance(compiler, IRCompiler)
        self.assertIsInstance(dashboard, FizzLLVMDashboard)
        self.assertIsInstance(middleware, FizzLLVMMiddleware)

    def test_factory_compiler_is_functional(self) -> None:
        """The compiler returned by the factory must be immediately usable."""
        compiler, _, _ = create_fizzllvm_subsystem()
        mod = compiler.create_module("factory_test")
        self.assertEqual(mod.name, "factory_test")


class TestFizzLLVMExceptions(unittest.TestCase):
    """Tests for the FizzLLVM exception hierarchy."""

    def test_fizzllvm_error_message(self) -> None:
        """FizzLLVMError must include the reason in its message."""
        err = FizzLLVMError("compilation failed")
        self.assertIn("compilation failed", str(err))

    def test_not_found_is_subclass(self) -> None:
        """FizzLLVMNotFoundError must be a subclass of FizzLLVMError."""
        self.assertTrue(issubclass(FizzLLVMNotFoundError, FizzLLVMError))

    def test_not_found_error_message(self) -> None:
        """FizzLLVMNotFoundError must identify the missing entity."""
        err = FizzLLVMNotFoundError("module xyz")
        self.assertIn("module xyz", str(err))


if __name__ == "__main__":
    unittest.main()
