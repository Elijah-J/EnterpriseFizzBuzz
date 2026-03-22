"""
Enterprise FizzBuzz Platform - Cross-Compiler Tests

Tests for the FizzBuzz Cross-Compiler: IR generation, C/Rust/WAT
code generation, round-trip verification, dashboard rendering,
and the CrossCompiler facade.

Because transpiling modulo arithmetic into three different
languages requires at least 40 tests to prove it works.
"""

import unittest

from enterprise_fizzbuzz.domain.exceptions import (
    CodeGenerationError,
    CrossCompilerError,
    IRGenerationError,
    RoundTripVerificationError,
    UnsupportedTargetError,
)
from enterprise_fizzbuzz.domain.models import EventType, RuleDefinition
from enterprise_fizzbuzz.infrastructure.cross_compiler import (
    BasicBlock,
    CCodeGenerator,
    CompilationResult,
    CompilerDashboard,
    CompilerIR,
    CrossCompiler,
    IRBuilder,
    IRInstruction,
    IROpCode,
    RoundTripVerifier,
    RustCodeGenerator,
    VerificationReport,
    WasmTextGenerator,
)


# Standard FizzBuzz rules used across most tests
STANDARD_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
]

# Single rule for edge case testing
SINGLE_RULE = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
]

# Three rules for extended testing
TRIPLE_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
    RuleDefinition(name="WuzzRule", divisor=7, label="Wuzz", priority=3),
]


class TestIROpCode(unittest.TestCase):
    """Tests for the IR opcode enumeration."""

    def test_all_opcodes_exist(self) -> None:
        """All seven IR opcodes must be defined."""
        expected = {"LOAD", "MOD", "CMP_ZERO", "BRANCH", "EMIT", "JUMP", "RET"}
        actual = {op.name for op in IROpCode}
        self.assertEqual(expected, actual)

    def test_opcode_count(self) -> None:
        """There must be exactly seven opcodes."""
        self.assertEqual(len(IROpCode), 7)


class TestIRInstruction(unittest.TestCase):
    """Tests for individual IR instructions."""

    def test_instruction_creation(self) -> None:
        """IR instructions should store opcode and operands."""
        instr = IRInstruction(IROpCode.MOD, ("n", 3), "test comment")
        self.assertEqual(instr.opcode, IROpCode.MOD)
        self.assertEqual(instr.operands, ("n", 3))
        self.assertEqual(instr.comment, "test comment")

    def test_instruction_str_with_comment(self) -> None:
        """String representation should include operands and comment."""
        instr = IRInstruction(IROpCode.MOD, ("n", 3), "compute modulo")
        result = str(instr)
        self.assertIn("MOD", result)
        self.assertIn("n, 3", result)
        self.assertIn("compute modulo", result)

    def test_instruction_str_no_operands(self) -> None:
        """Instructions without operands should still format correctly."""
        instr = IRInstruction(IROpCode.RET)
        result = str(instr)
        self.assertIn("RET", result)

    def test_instruction_frozen(self) -> None:
        """IR instructions should be immutable (frozen dataclass)."""
        instr = IRInstruction(IROpCode.LOAD, ("n",))
        with self.assertRaises(AttributeError):
            instr.opcode = IROpCode.MOD  # type: ignore[misc]


class TestBasicBlock(unittest.TestCase):
    """Tests for basic blocks."""

    def test_block_creation(self) -> None:
        """Basic blocks should have a label and empty instruction list."""
        block = BasicBlock("entry")
        self.assertEqual(block.label, "entry")
        self.assertEqual(len(block.instructions), 0)

    def test_add_instruction(self) -> None:
        """Adding instructions should grow the instruction list."""
        block = BasicBlock("test")
        block.add(IRInstruction(IROpCode.LOAD, ("n",)))
        block.add(IRInstruction(IROpCode.RET))
        self.assertEqual(len(block.instructions), 2)


class TestCompilerIR(unittest.TestCase):
    """Tests for the CompilerIR container."""

    def test_total_instructions(self) -> None:
        """Total instruction count should sum across all blocks."""
        ir = CompilerIR()
        b1 = BasicBlock("b1")
        b1.add(IRInstruction(IROpCode.LOAD, ("n",)))
        b1.add(IRInstruction(IROpCode.MOD, ("n", 3)))
        b2 = BasicBlock("b2")
        b2.add(IRInstruction(IROpCode.RET))
        ir.blocks = [b1, b2]
        self.assertEqual(ir.total_instructions, 3)

    def test_dump_format(self) -> None:
        """IR dump should contain header comments and block labels."""
        ir = CompilerIR(rule_count=2, generation_time_ms=1.234)
        block = BasicBlock("entry")
        block.add(IRInstruction(IROpCode.LOAD, ("n",), "load input"))
        ir.blocks = [block]
        dump = ir.dump()
        self.assertIn("; FizzBuzz Cross-Compiler IR", dump)
        self.assertIn("Rules: 2", dump)
        self.assertIn("entry:", dump)
        self.assertIn("LOAD", dump)

    def test_empty_ir(self) -> None:
        """Empty IR should have zero instructions."""
        ir = CompilerIR()
        self.assertEqual(ir.total_instructions, 0)
        self.assertEqual(len(ir.blocks), 0)


class TestIRBuilder(unittest.TestCase):
    """Tests for the IR builder."""

    def test_build_standard_rules(self) -> None:
        """Building IR from standard FizzBuzz rules should produce valid IR."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        self.assertGreater(len(ir.blocks), 0)
        self.assertEqual(ir.rule_count, 2)
        self.assertGreater(ir.total_instructions, 0)

    def test_build_single_rule(self) -> None:
        """Building IR from a single rule should work."""
        builder = IRBuilder()
        ir = builder.build(SINGLE_RULE)
        self.assertEqual(ir.rule_count, 1)
        self.assertGreater(len(ir.blocks), 0)

    def test_build_triple_rules(self) -> None:
        """Building IR from three rules should produce more blocks."""
        builder = IRBuilder()
        ir = builder.build(TRIPLE_RULES)
        self.assertEqual(ir.rule_count, 3)

    def test_build_empty_rules_raises(self) -> None:
        """Building IR from empty rules should raise IRGenerationError."""
        builder = IRBuilder()
        with self.assertRaises(IRGenerationError):
            builder.build([])

    def test_entry_block_has_load(self) -> None:
        """The entry block should start with a LOAD instruction."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        entry = ir.blocks[0]
        self.assertEqual(entry.label, "entry")
        self.assertEqual(entry.instructions[0].opcode, IROpCode.LOAD)

    def test_exit_block_has_ret(self) -> None:
        """The exit block should contain a RET instruction."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        exit_block = ir.blocks[-1]
        self.assertEqual(exit_block.label, "exit")
        self.assertEqual(exit_block.instructions[0].opcode, IROpCode.RET)

    def test_generation_time_recorded(self) -> None:
        """IR generation time should be recorded."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        self.assertGreaterEqual(ir.generation_time_ms, 0.0)


class TestCCodeGenerator(unittest.TestCase):
    """Tests for C code generation."""

    def test_generates_valid_c(self) -> None:
        """Generated C code should contain key ANSI C constructs."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = CCodeGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("#include <stdio.h>", code)
        self.assertIn("int main(void)", code)
        self.assertIn("void fizzbuzz(int n", code)
        self.assertIn("return 0;", code)

    def test_label_buffer(self) -> None:
        """Generated C should define a label buffer constant."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = CCodeGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("FIZZBUZZ_LABEL_MAX", code)

    def test_modulo_checks(self) -> None:
        """Generated C should contain modulo checks for each rule."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = CCodeGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("n % 3 == 0", code)
        self.assertIn("n % 5 == 0", code)

    def test_no_comments_mode(self) -> None:
        """With emit_comments=False, comments should be suppressed."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = CCodeGenerator(emit_comments=False)
        code = gen.generate(STANDARD_RULES, ir)
        self.assertNotIn("/*", code)
        self.assertNotIn("AUTO-GENERATED", code)

    def test_single_rule_c(self) -> None:
        """Single-rule C generation should work."""
        builder = IRBuilder()
        ir = builder.build(SINGLE_RULE)
        gen = CCodeGenerator()
        code = gen.generate(SINGLE_RULE, ir)
        self.assertIn("n % 3 == 0", code)
        self.assertIn("#include <stdio.h>", code)


class TestRustCodeGenerator(unittest.TestCase):
    """Tests for Rust code generation."""

    def test_generates_valid_rust(self) -> None:
        """Generated Rust code should contain key Rust constructs."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = RustCodeGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("fn main()", code)
        self.assertIn("fn fizzbuzz(n: i64) -> String", code)

    def test_string_concatenation(self) -> None:
        """Generated Rust should build labels via string concatenation."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = RustCodeGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("let mut label = String::new()", code)
        self.assertIn('push_str("Fizz")', code)
        self.assertIn('push_str("Buzz")', code)

    def test_number_fallback(self) -> None:
        """Generated Rust should fall back to number when no rules match."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = RustCodeGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("n.to_string()", code)

    def test_no_comments_mode(self) -> None:
        """With emit_comments=False, doc comments should be suppressed."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = RustCodeGenerator(emit_comments=False)
        code = gen.generate(STANDARD_RULES, ir)
        self.assertNotIn("//!", code)
        self.assertNotIn("///", code)

    def test_single_rule_rust(self) -> None:
        """Single-rule Rust generation should work."""
        builder = IRBuilder()
        ir = builder.build(SINGLE_RULE)
        gen = RustCodeGenerator()
        code = gen.generate(SINGLE_RULE, ir)
        self.assertIn("fn fizzbuzz", code)
        self.assertIn("n % 3", code)


class TestWasmTextGenerator(unittest.TestCase):
    """Tests for WebAssembly Text code generation."""

    def test_generates_valid_wat(self) -> None:
        """Generated WAT should contain module and function structure."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = WasmTextGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("(module", code)
        self.assertIn("(func $fizzbuzz", code)
        self.assertIn("(param $n i32)", code)
        self.assertIn("(result i32)", code)
        self.assertIn('(export "fizzbuzz"', code)

    def test_modulo_operations(self) -> None:
        """Generated WAT should contain i32.rem_s operations."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = WasmTextGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("i32.rem_s", code)
        self.assertIn("i32.eqz", code)
        self.assertIn("(i32.const 3)", code)
        self.assertIn("(i32.const 5)", code)

    def test_bitmask_approach_in_comments(self) -> None:
        """WAT should document the bitmask classification in comments."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = WasmTextGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn(";; Classification bitmask:", code)
        self.assertIn("bit 0", code)
        self.assertIn("bit 1", code)

    def test_uses_bitmask_or(self) -> None:
        """WAT should use i32.or for bitmask accumulation."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = WasmTextGenerator()
        code = gen.generate(STANDARD_RULES, ir)
        self.assertIn("i32.or", code)
        self.assertIn("local $mask", code)

    def test_no_comments_mode(self) -> None:
        """With emit_comments=False, WAT comments should be suppressed."""
        builder = IRBuilder()
        ir = builder.build(STANDARD_RULES)
        gen = WasmTextGenerator(emit_comments=False)
        code = gen.generate(STANDARD_RULES, ir)
        self.assertNotIn(";; Enterprise", code)
        self.assertNotIn(";; AUTO-GENERATED", code)

    def test_single_rule_wat(self) -> None:
        """Single-rule WAT generation should work."""
        builder = IRBuilder()
        ir = builder.build(SINGLE_RULE)
        gen = WasmTextGenerator()
        code = gen.generate(SINGLE_RULE, ir)
        self.assertIn("(module", code)
        self.assertIn("(i32.const 3)", code)


class TestRoundTripVerifier(unittest.TestCase):
    """Tests for round-trip verification."""

    def test_standard_rules_pass(self) -> None:
        """Standard FizzBuzz rules should pass verification."""
        verifier = RoundTripVerifier(STANDARD_RULES, range_end=100)
        report = verifier.verify("test", "fake code\n" * 50)
        self.assertTrue(report.passed)
        self.assertEqual(report.numbers_verified, 100)
        self.assertEqual(report.mismatches, 0)

    def test_single_rule_passes(self) -> None:
        """Single rule should pass verification."""
        verifier = RoundTripVerifier(SINGLE_RULE, range_end=30)
        report = verifier.verify("test", "code\n" * 10)
        self.assertTrue(report.passed)

    def test_triple_rules_pass(self) -> None:
        """Triple rules should pass verification."""
        verifier = RoundTripVerifier(TRIPLE_RULES, range_end=105)
        report = verifier.verify("test", "code\n" * 20)
        self.assertTrue(report.passed)

    def test_verification_time_recorded(self) -> None:
        """Verification time should be non-negative."""
        verifier = RoundTripVerifier(STANDARD_RULES, range_end=10)
        report = verifier.verify("test", "code")
        self.assertGreaterEqual(report.verification_time_ms, 0.0)

    def test_generated_line_count(self) -> None:
        """Verification report should track generated line count."""
        verifier = RoundTripVerifier(STANDARD_RULES, range_end=10)
        report = verifier.verify("test", "line1\nline2\nline3")
        self.assertEqual(report.generated_line_count, 3)


class TestCompilerDashboard(unittest.TestCase):
    """Tests for the compiler dashboard."""

    def test_dashboard_renders(self) -> None:
        """Dashboard should render without errors."""
        ir = CompilerIR(rule_count=2, generation_time_ms=1.5)
        block = BasicBlock("entry")
        block.add(IRInstruction(IROpCode.LOAD, ("n",)))
        ir.blocks = [block]
        code = "line\n" * 47
        dashboard = CompilerDashboard.render(ir, code, "c")
        self.assertIn("ENTERPRISE FIZZBUZZ CROSS-COMPILER", dashboard)
        self.assertIn("Target: C", dashboard)

    def test_dashboard_with_verification(self) -> None:
        """Dashboard should include verification section when provided."""
        ir = CompilerIR(rule_count=2)
        ir.blocks = [BasicBlock("b")]
        verification = VerificationReport(
            target="c",
            numbers_verified=100,
            mismatches=0,
            verification_time_ms=5.0,
            passed=True,
            generated_line_count=50,
        )
        dashboard = CompilerDashboard.render(
            ir, "code\n" * 50, "c", verification=verification
        )
        self.assertIn("Round-Trip Verification", dashboard)
        self.assertIn("PASSED", dashboard)

    def test_dashboard_overhead_factor(self) -> None:
        """Dashboard should display the overhead factor."""
        ir = CompilerIR(rule_count=2)
        ir.blocks = [BasicBlock("b")]
        dashboard = CompilerDashboard.render(
            ir, "line\n" * 49, "c", python_line_count=2
        )
        self.assertIn("Overhead factor:", dashboard)
        self.assertIn("25.0x", dashboard)

    def test_dashboard_enterprise_analysis(self) -> None:
        """Dashboard should include satirical enterprise analysis."""
        ir = CompilerIR(rule_count=2)
        ir.blocks = [BasicBlock("b")]
        dashboard = CompilerDashboard.render(ir, "line\n" * 49, "c")
        self.assertIn("Enterprise Analysis", dashboard)
        self.assertIn("Enterprise readiness:", dashboard)

    def test_dashboard_with_ir_dump(self) -> None:
        """Dashboard should include IR dump when show_ir=True."""
        ir = CompilerIR(rule_count=1)
        block = BasicBlock("entry")
        block.add(IRInstruction(IROpCode.LOAD, ("n",)))
        ir.blocks = [block]
        dashboard = CompilerDashboard.render(
            ir, "code", "c", show_ir=True
        )
        self.assertIn("Intermediate Representation", dashboard)
        self.assertIn("LOAD", dashboard)


class TestCrossCompiler(unittest.TestCase):
    """Tests for the CrossCompiler facade."""

    def test_compile_c(self) -> None:
        """Compiling to C should produce valid output."""
        cc = CrossCompiler(STANDARD_RULES)
        result = cc.compile("c")
        self.assertEqual(result.target, "c")
        self.assertIn("#include <stdio.h>", result.generated_code)
        self.assertIsNotNone(result.ir)
        self.assertIsNotNone(result.verification)
        self.assertTrue(result.verification.passed)

    def test_compile_rust(self) -> None:
        """Compiling to Rust should produce valid output."""
        cc = CrossCompiler(STANDARD_RULES)
        result = cc.compile("rust")
        self.assertEqual(result.target, "rust")
        self.assertIn("fn main()", result.generated_code)
        self.assertTrue(result.verification.passed)

    def test_compile_wat(self) -> None:
        """Compiling to WAT should produce valid output."""
        cc = CrossCompiler(STANDARD_RULES)
        result = cc.compile("wat")
        self.assertEqual(result.target, "wat")
        self.assertIn("(module", result.generated_code)
        self.assertTrue(result.verification.passed)

    def test_unsupported_target_raises(self) -> None:
        """Requesting an unsupported target should raise UnsupportedTargetError."""
        cc = CrossCompiler(STANDARD_RULES)
        with self.assertRaises(UnsupportedTargetError) as ctx:
            cc.compile("cobol")
        self.assertIn("cobol", str(ctx.exception))
        self.assertIn("Q4 2027", str(ctx.exception))

    def test_compile_without_verification(self) -> None:
        """Compiling with verify=False should skip verification."""
        cc = CrossCompiler(STANDARD_RULES, verify=False)
        result = cc.compile("c")
        self.assertIsNone(result.verification)

    def test_compile_ir_only(self) -> None:
        """compile_ir_only should return IR without code generation."""
        cc = CrossCompiler(STANDARD_RULES)
        ir = cc.compile_ir_only()
        self.assertGreater(ir.total_instructions, 0)
        self.assertEqual(ir.rule_count, 2)

    def test_render_dashboard(self) -> None:
        """render_dashboard should produce dashboard text."""
        cc = CrossCompiler(STANDARD_RULES)
        result = cc.compile("c")
        dashboard = cc.render_dashboard(result)
        self.assertIn("ENTERPRISE FIZZBUZZ CROSS-COMPILER", dashboard)

    def test_compilation_time_tracked(self) -> None:
        """Compilation result should track total time."""
        cc = CrossCompiler(STANDARD_RULES)
        result = cc.compile("c")
        self.assertGreater(result.total_time_ms, 0.0)

    def test_event_callback(self) -> None:
        """Events should be emitted during compilation."""
        events: list[tuple[EventType, dict]] = []

        def callback(event_type: EventType, data: dict) -> None:
            events.append((event_type, data))

        cc = CrossCompiler(STANDARD_RULES, event_callback=callback)
        cc.compile("c")
        event_types = [e[0] for e in events]
        self.assertIn(EventType.COMPILER_IR_GENERATED, event_types)
        self.assertIn(EventType.COMPILER_CODE_EMITTED, event_types)
        self.assertIn(EventType.COMPILER_ROUND_TRIP_VERIFIED, event_types)

    def test_compile_all_targets(self) -> None:
        """All supported targets should compile successfully."""
        cc = CrossCompiler(STANDARD_RULES)
        for target in CrossCompiler.SUPPORTED_TARGETS:
            result = cc.compile(target)
            self.assertEqual(result.target, target)
            self.assertGreater(len(result.generated_code), 0)


class TestCrossCompilerExceptions(unittest.TestCase):
    """Tests for the cross-compiler exception hierarchy."""

    def test_cross_compiler_error_base(self) -> None:
        """CrossCompilerError should have error code EFP-CC00."""
        err = CrossCompilerError("test")
        self.assertIn("EFP-CC00", str(err))

    def test_ir_generation_error(self) -> None:
        """IRGenerationError should include rule name."""
        err = IRGenerationError("FizzRule", "too simple")
        self.assertIn("EFP-CC01", str(err))
        self.assertIn("FizzRule", str(err))

    def test_code_generation_error(self) -> None:
        """CodeGenerationError should include target language."""
        err = CodeGenerationError("c", "buffer overflow of enterprise")
        self.assertIn("EFP-CC02", str(err))
        self.assertIn("c", str(err))

    def test_round_trip_verification_error(self) -> None:
        """RoundTripVerificationError should include mismatch details."""
        err = RoundTripVerificationError("rust", 15, "FizzBuzz", "Buzz")
        self.assertIn("EFP-CC03", str(err))
        self.assertIn("rust", str(err))
        self.assertIn("15", str(err))

    def test_unsupported_target_error(self) -> None:
        """UnsupportedTargetError should list supported targets."""
        err = UnsupportedTargetError("brainfuck")
        self.assertIn("EFP-CC04", str(err))
        self.assertIn("brainfuck", str(err))
        self.assertIn("COBOL", str(err))


class TestEventTypes(unittest.TestCase):
    """Tests for cross-compiler event types."""

    def test_compiler_event_types_exist(self) -> None:
        """All cross-compiler EventType entries should exist."""
        expected = [
            EventType.COMPILER_IR_GENERATED,
            EventType.COMPILER_CODE_EMITTED,
            EventType.COMPILER_ROUND_TRIP_VERIFIED,
            EventType.COMPILER_ROUND_TRIP_FAILED,
            EventType.COMPILER_DASHBOARD_RENDERED,
        ]
        for event in expected:
            self.assertIsNotNone(event)


if __name__ == "__main__":
    unittest.main()
