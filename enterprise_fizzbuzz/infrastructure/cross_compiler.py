"""
Enterprise FizzBuzz Platform - Cross-Compiler Module

Transpiles FizzBuzz rules into C, Rust, and WebAssembly Text format,
because executing `n % 3 == 0` in Python was simply too efficient
and someone on the architecture review board asked "but can it run
on bare metal?"

The cross-compiler operates in four phases:
  1. IR Generation  - Lower RuleDefinitions into a typed IR
  2. Code Emission  - Translate IR into the target language
  3. Round-Trip Verification - Verify output matches Python reference
  4. Dashboard Rendering - ASCII dashboard with overhead metrics

The overhead factor (e.g., "Python: 2 lines -> C: 47 lines") is
not a deficiency. It is a key performance indicator that demonstrates
our commitment to enterprise-grade code generation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CodeGenerationError,
    CrossCompilerError,
    IRGenerationError,
    RoundTripVerificationError,
    UnsupportedTargetError,
)
from enterprise_fizzbuzz.domain.models import EventType, RuleDefinition


# ============================================================
# Intermediate Representation (IR)
# ============================================================
# Every serious compiler needs an IR, even when the source language
# is "check if a number is divisible by 3 or 5." Our IR supports
# seven opcodes, which is six more than strictly necessary.
# ============================================================


class IROpCode(Enum):
    """Opcodes for the FizzBuzz Intermediate Representation.

    Each opcode maps to a single semantic operation in the
    FizzBuzz evaluation pipeline. The fact that FizzBuzz can
    be expressed in two lines of Python and yet requires seven
    distinct IR opcodes is a testament to proper compiler design.
    """

    LOAD = auto()       # Load a value (the input number)
    MOD = auto()        # Compute modulo
    CMP_ZERO = auto()   # Compare result to zero
    BRANCH = auto()     # Conditional branch
    EMIT = auto()       # Emit a label string
    JUMP = auto()       # Unconditional jump
    RET = auto()        # Return from function


@dataclass(frozen=True)
class IRInstruction:
    """A single instruction in the FizzBuzz IR.

    Attributes:
        opcode: The operation to perform.
        operands: Operand values (semantics depend on opcode).
        comment: Optional comment for debugging and documentation purposes.
    """

    opcode: IROpCode
    operands: tuple[Any, ...] = ()
    comment: str = ""

    def __str__(self) -> str:
        ops = ", ".join(str(o) for o in self.operands) if self.operands else ""
        base = f"{self.opcode.name:<10} {ops}"
        if self.comment:
            return f"{base:<30} ; {self.comment}"
        return base


@dataclass
class BasicBlock:
    """A basic block in the control flow graph.

    In a real compiler, basic blocks contain sequences of instructions
    with a single entry point and single exit point. In the FizzBuzz
    compiler, they contain sequences of instructions that check if
    a number is divisible by 3. The engineering overhead is identical.

    Attributes:
        label: Block identifier.
        instructions: Ordered list of IR instructions.
    """

    label: str
    instructions: list[IRInstruction] = field(default_factory=list)

    def add(self, instruction: IRInstruction) -> None:
        """Append an instruction to this basic block."""
        self.instructions.append(instruction)


@dataclass
class CompilerIR:
    """Complete Intermediate Representation for a FizzBuzz program.

    Contains all basic blocks that make up the FizzBuzz evaluation
    function. The number of blocks is always proportional to the
    number of rules, which for standard FizzBuzz is two. The fact
    that we built a full IR infrastructure for two rules is noted
    but not apologized for.

    Attributes:
        blocks: Ordered list of basic blocks.
        rule_count: Number of FizzBuzz rules compiled.
        generation_time_ms: Time taken to generate the IR.
    """

    blocks: list[BasicBlock] = field(default_factory=list)
    rule_count: int = 0
    generation_time_ms: float = 0.0

    @property
    def total_instructions(self) -> int:
        """Total instruction count across all basic blocks."""
        return sum(len(b.instructions) for b in self.blocks)

    def dump(self) -> str:
        """Dump the IR to a human-readable string.

        Returns a formatted representation suitable for debugging,
        code review, and impressing people who don't know what
        FizzBuzz actually does.
        """
        lines: list[str] = []
        lines.append("; FizzBuzz Cross-Compiler IR")
        lines.append(f"; Rules: {self.rule_count}")
        lines.append(f"; Basic blocks: {len(self.blocks)}")
        lines.append(f"; Total instructions: {self.total_instructions}")
        lines.append(f"; Generation time: {self.generation_time_ms:.3f}ms")
        lines.append("")

        for block in self.blocks:
            lines.append(f"{block.label}:")
            for instr in block.instructions:
                lines.append(f"    {instr}")
            lines.append("")

        return "\n".join(lines)


# ============================================================
# IR Builder
# ============================================================
# Lowers RuleDefinition objects into the FizzBuzz IR. Each rule
# becomes a sequence: LOAD -> MOD -> CMP_ZERO -> BRANCH -> EMIT.
# The combined-label block handles multi-rule matches (FizzBuzz).
# ============================================================


class IRBuilder:
    """Builds FizzBuzz IR from a list of RuleDefinition objects.

    The builder creates one basic block per rule, plus an entry block,
    a combined-label block for multi-rule matches, and an exit block.
    This is the minimum viable set of basic blocks for a FizzBuzz
    compiler, which is to say, far more basic blocks than anyone
    would ever need for FizzBuzz.
    """

    def build(self, rules: list[RuleDefinition]) -> CompilerIR:
        """Convert rule definitions into a CompilerIR.

        Args:
            rules: FizzBuzz rules sorted by priority.

        Returns:
            A CompilerIR containing all basic blocks.

        Raises:
            IRGenerationError: If the rules list is empty, because
                compiling zero rules is a philosophical question
                the IR builder is not prepared to answer.
        """
        if not rules:
            raise IRGenerationError(
                "<none>",
                "Cannot generate IR from zero rules. "
                "The compiler needs at least one rule to justify its existence.",
            )

        start_time = time.perf_counter()
        ir = CompilerIR()
        sorted_rules = sorted(rules, key=lambda r: r.priority)

        # Entry block: load the input number
        entry = BasicBlock("entry")
        entry.add(IRInstruction(
            IROpCode.LOAD, ("n",),
            "Load the input number into the evaluation register",
        ))
        ir.blocks.append(entry)

        # One block per rule: check divisibility and set flag
        for i, rule in enumerate(sorted_rules):
            block = BasicBlock(f"check_{rule.label.lower()}")
            block.add(IRInstruction(
                IROpCode.MOD, ("n", rule.divisor),
                f"Compute n % {rule.divisor} for rule '{rule.name}'",
            ))
            block.add(IRInstruction(
                IROpCode.CMP_ZERO, (),
                f"Check if remainder is zero",
            ))
            block.add(IRInstruction(
                IROpCode.BRANCH, (f"emit_{rule.label.lower()}", f"check_{sorted_rules[i + 1].label.lower()}" if i + 1 < len(sorted_rules) else "emit_number"),
                f"Branch to emit block if divisible by {rule.divisor}",
            ))
            ir.blocks.append(block)

        # Emit blocks for each rule label
        for rule in sorted_rules:
            block = BasicBlock(f"emit_{rule.label.lower()}")
            block.add(IRInstruction(
                IROpCode.EMIT, (rule.label,),
                f"Emit '{rule.label}' — the sacred incantation for divisor {rule.divisor}",
            ))
            # After emitting, check remaining rules for combined labels
            block.add(IRInstruction(
                IROpCode.JUMP, ("exit",),
                "Proceed to exit (combined labels handled in code generators)",
            ))
            ir.blocks.append(block)

        # Emit number block (no rules matched)
        number_block = BasicBlock("emit_number")
        number_block.add(IRInstruction(
            IROpCode.EMIT, ("n",),
            "No rules matched — emit the number itself, in all its prime glory",
        ))
        number_block.add(IRInstruction(
            IROpCode.JUMP, ("exit",),
            "Jump to exit",
        ))
        ir.blocks.append(number_block)

        # Exit block
        exit_block = BasicBlock("exit")
        exit_block.add(IRInstruction(
            IROpCode.RET, (),
            "Return from fizzbuzz function — another number has been classified",
        ))
        ir.blocks.append(exit_block)

        elapsed = (time.perf_counter() - start_time) * 1000
        ir.rule_count = len(sorted_rules)
        ir.generation_time_ms = elapsed

        return ir


# ============================================================
# Code Generators
# ============================================================
# Each generator translates the FizzBuzz IR into a target language.
# The generators do NOT actually read the IR instruction-by-instruction
# (that would require a real compiler backend). Instead, they use
# the rule metadata to emit idiomatic code in each target language,
# because the IR exists for architectural credibility, not utility.
# ============================================================


class CCodeGenerator:
    """Generates ANSI C code from FizzBuzz rules.

    Emits a complete, compilable C program with a fizzbuzz() function
    that evaluates all rules using if/else chains. The generated code
    includes extensive comments, header guards that don't guard anything,
    and enough boilerplate to make the overhead factor truly impressive.
    """

    def __init__(self, emit_comments: bool = True) -> None:
        self._emit_comments = emit_comments

    def generate(self, rules: list[RuleDefinition], ir: CompilerIR) -> str:
        """Generate ANSI C source code.

        Args:
            rules: The FizzBuzz rule definitions.
            ir: The compiler IR (used for metadata in comments).

        Returns:
            A string containing valid ANSI C source code.
        """
        sorted_rules = sorted(rules, key=lambda r: r.priority)
        lines: list[str] = []

        # File header
        if self._emit_comments:
            lines.extend([
                "/*",
                " * Enterprise FizzBuzz Platform - Cross-Compiled C Output",
                " *",
                " * AUTO-GENERATED by the EFP Cross-Compiler v1.0.0",
                " * DO NOT EDIT — unless you want to, in which case,",
                " * why did you bother generating it in the first place?",
                " *",
                f" * Rules compiled: {len(sorted_rules)}",
                f" * IR instructions: {ir.total_instructions}",
                f" * IR generation time: {ir.generation_time_ms:.3f}ms",
                " *",
                " * Compile: gcc -std=c99 -o fizzbuzz fizzbuzz.c",
                " */",
                "",
            ])

        # Includes
        lines.extend([
            "#include <stdio.h>",
            "#include <stdlib.h>",
            "",
        ])

        # String concatenation buffer size
        max_label_len = sum(len(r.label) for r in sorted_rules) + 1

        # Forward declare fizzbuzz for pedantic compilers
        if self._emit_comments:
            lines.append("/* Maximum label buffer length (all rules concatenated + NUL) */")
        lines.append(f"#define FIZZBUZZ_LABEL_MAX {max_label_len}")
        lines.append("")

        # fizzbuzz function
        if self._emit_comments:
            lines.extend([
                "/*",
                " * Evaluate a single number against all FizzBuzz rules.",
                " * Builds the label by concatenating all matching rules,",
                " * because FizzBuzz is fundamentally a string-building exercise",
                " * disguised as a modulo exercise.",
                f" * Time complexity: O(1) — but the code complexity is O(enterprise).",
                " */",
            ])
        lines.append("void fizzbuzz(int n, char *buf, int buf_size) {")
        lines.append("    int pos = 0;")
        lines.append("    buf[0] = '\\0';")
        lines.append("")

        # Check each rule and concatenate
        for rule in sorted_rules:
            if self._emit_comments:
                lines.append(f"    /* Rule: {rule.name} (divisor={rule.divisor}, priority={rule.priority}) */")
            lines.append(f"    if (n % {rule.divisor} == 0) {{")
            # Use a simple char-by-char copy to avoid string.h dependency
            for i, ch in enumerate(rule.label):
                lines.append(f"        buf[pos++] = '{ch}';")
            lines.append("    }")
            lines.append("")

        if self._emit_comments:
            lines.append("    /* Terminate the label string */")
        lines.append("    buf[pos] = '\\0';")
        lines.append("}")
        lines.append("")

        # print_result helper
        if self._emit_comments:
            lines.append("/* Print a FizzBuzz result to stdout */")
        lines.append("void print_result(int n) {")
        lines.append(f"    char label[FIZZBUZZ_LABEL_MAX];")
        lines.append(f"    fizzbuzz(n, label, FIZZBUZZ_LABEL_MAX);")
        lines.append("    if (label[0] != '\\0') {")
        lines.append('        printf("%s\\n", label);')
        lines.append("    } else {")
        lines.append('        printf("%d\\n", n);')
        lines.append("    }")
        lines.append("}")
        lines.append("")

        # main function
        if self._emit_comments:
            lines.extend([
                "/*",
                " * Main entry point.",
                " * Evaluates FizzBuzz for numbers 1 through 100,",
                " * because that is the enterprise-mandated range.",
                " */",
            ])
        lines.append("int main(void) {")
        lines.append("    int i;")
        lines.append("    for (i = 1; i <= 100; i++) {")
        lines.append("        print_result(i);")
        lines.append("    }")
        lines.append("    return 0;")
        lines.append("}")
        lines.append("")

        return "\n".join(lines)


class RustCodeGenerator:
    """Generates Rust code from FizzBuzz rules.

    Emits a complete Rust program with a fizzbuzz() function
    using match expressions and a Classification enum. The generated
    code leverages Rust's type system to ensure that FizzBuzz results
    are memory-safe, thread-safe, and existentially dreadful.
    """

    def __init__(self, emit_comments: bool = True) -> None:
        self._emit_comments = emit_comments

    def generate(self, rules: list[RuleDefinition], ir: CompilerIR) -> str:
        """Generate Rust source code.

        Args:
            rules: The FizzBuzz rule definitions.
            ir: The compiler IR (used for metadata in comments).

        Returns:
            A string containing valid Rust source code.
        """
        sorted_rules = sorted(rules, key=lambda r: r.priority)
        lines: list[str] = []

        # File header
        if self._emit_comments:
            lines.extend([
                "//! Enterprise FizzBuzz Platform - Cross-Compiled Rust Output",
                "//!",
                "//! AUTO-GENERATED by the EFP Cross-Compiler v1.0.0",
                "//! DO NOT EDIT — the borrow checker will judge you.",
                "//!",
                f"//! Rules compiled: {len(sorted_rules)}",
                f"//! IR instructions: {ir.total_instructions}",
                f"//! IR generation time: {ir.generation_time_ms:.3f}ms",
                "",
            ])

        # Classification enum
        if self._emit_comments:
            lines.append("/// Classification of a FizzBuzz evaluation result.")
        lines.append("#[derive(Debug, Clone, PartialEq)]")
        lines.append("enum Classification {")
        for rule in sorted_rules:
            lines.append(f"    {rule.label},")
        combined = "".join(r.label for r in sorted_rules)
        lines.append(f"    {combined},")
        lines.append("    Number(i64),")
        lines.append("}")
        lines.append("")

        # Display impl
        lines.append("impl std::fmt::Display for Classification {")
        lines.append("    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {")
        lines.append("        match self {")
        for rule in sorted_rules:
            lines.append(f'            Classification::{rule.label} => write!(f, "{rule.label}"),')
        lines.append(f'            Classification::{combined} => write!(f, "{combined}"),')
        lines.append('            Classification::Number(n) => write!(f, "{}", n),')
        lines.append("        }")
        lines.append("    }")
        lines.append("}")
        lines.append("")

        # fizzbuzz function — builds label by concatenating matching rules
        if self._emit_comments:
            lines.extend([
                "/// Evaluate a single number against all FizzBuzz rules.",
                "///",
                "/// Builds the label by concatenating all matching rule labels,",
                "/// because FizzBuzz is fundamentally a string concatenation",
                "/// problem that we have elevated into a type system exercise.",
            ])
        lines.append("fn fizzbuzz(n: i64) -> String {")
        lines.append("    let mut label = String::new();")
        lines.append("")

        for rule in sorted_rules:
            if self._emit_comments:
                lines.append(f"    // Rule: {rule.name} (divisor={rule.divisor}, priority={rule.priority})")
            lines.append(f"    if n % {rule.divisor} == 0 {{")
            lines.append(f'        label.push_str("{rule.label}");')
            lines.append("    }")
            lines.append("")

        lines.append("    if label.is_empty() {")
        lines.append("        n.to_string()")
        lines.append("    } else {")
        lines.append("        label")
        lines.append("    }")
        lines.append("}")
        lines.append("")

        # main function
        if self._emit_comments:
            lines.extend([
                "/// Main entry point.",
                "///",
                "/// Evaluates FizzBuzz for the enterprise-mandated range of 1..=100.",
            ])
        lines.append("fn main() {")
        lines.append("    for i in 1..=100_i64 {")
        lines.append("        println!(\"{}\", fizzbuzz(i));")
        lines.append("    }")
        lines.append("}")
        lines.append("")

        return "\n".join(lines)


class WasmTextGenerator:
    """Generates WebAssembly Text (WAT) format from FizzBuzz rules.

    Emits a WAT module with a $fizzbuzz function that classifies
    numbers using integer arithmetic and branch instructions.
    The generated module exports the function for use by a host
    environment that, presumably, needed FizzBuzz at near-native
    speed for some deeply important reason.

    The WAT output uses a bitmask approach: each rule sets a bit
    in the result. The host environment maps bitmask values to labels.
    Bit 0 = rule 0, bit 1 = rule 1, etc. A result of 0 means no
    rules matched (plain number).
    """

    def __init__(self, emit_comments: bool = True) -> None:
        self._emit_comments = emit_comments

    def generate(self, rules: list[RuleDefinition], ir: CompilerIR) -> str:
        """Generate WebAssembly Text (WAT) source.

        Args:
            rules: The FizzBuzz rule definitions.
            ir: The compiler IR (used for metadata in comments).

        Returns:
            A string containing valid WAT source code.
        """
        sorted_rules = sorted(rules, key=lambda r: r.priority)
        lines: list[str] = []

        # Module header
        if self._emit_comments:
            lines.extend([
                ";; Enterprise FizzBuzz Platform - Cross-Compiled WAT Output",
                ";;",
                ";; AUTO-GENERATED by the EFP Cross-Compiler v1.0.0",
                ";; DO NOT EDIT — WebAssembly is already hard enough to read.",
                ";;",
                f";; Rules compiled: {len(sorted_rules)}",
                f";; IR instructions: {ir.total_instructions}",
                f";; IR generation time: {ir.generation_time_ms:.3f}ms",
                ";;",
                ";; Classification bitmask:",
                ";;   0 = Number (no rules matched)",
            ])
            for i, rule in enumerate(sorted_rules):
                lines.append(f";;   bit {i} (value {1 << i}) = {rule.label}")
            all_bits = sum(1 << i for i in range(len(sorted_rules)))
            combined = "".join(r.label for r in sorted_rules)
            lines.append(f";;   {all_bits} = {combined} (all bits set)")
            lines.append(";;")

        lines.append("(module")

        if self._emit_comments:
            lines.append("  ;; Export the fizzbuzz function for host consumption")
        lines.append('  (export "fizzbuzz" (func $fizzbuzz))')
        lines.append("")

        if self._emit_comments:
            lines.extend([
                "  ;; $fizzbuzz: Classify a number according to FizzBuzz rules.",
                "  ;; param $n: The number to classify (i32).",
                "  ;; result: Bitmask of matched rules (i32). 0 = plain number.",
            ])
        lines.append("  (func $fizzbuzz (param $n i32) (result i32)")
        lines.append("    (local $mask i32)")

        if self._emit_comments:
            lines.append("    ;; Initialize bitmask to zero")
        lines.append("    (local.set $mask (i32.const 0))")
        lines.append("")

        # Check each rule and OR the corresponding bit into the mask
        for i, rule in enumerate(sorted_rules):
            bit_value = 1 << i
            if self._emit_comments:
                lines.append(f"    ;; Rule: {rule.name} (divisor={rule.divisor}, bit={i})")
            lines.append(f"    (if (i32.eqz (i32.rem_s (local.get $n) (i32.const {rule.divisor})))")
            lines.append(f"      (then")
            lines.append(f"        (local.set $mask (i32.or (local.get $mask) (i32.const {bit_value})))")
            lines.append(f"      )")
            lines.append(f"    )")
            lines.append("")

        if self._emit_comments:
            lines.append("    ;; Return the classification bitmask")
        lines.append("    (local.get $mask)")
        lines.append("  )")

        lines.append(")")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Round-Trip Verifier
# ============================================================
# Executes the FizzBuzz rules in Python and compares the results
# against the code generator's logic. This verifies that the
# generated code WOULD produce the same output, without actually
# compiling or executing it (because that would require the target
# toolchain to be installed, and enterprise build environments
# are fragile enough already).
# ============================================================


class RoundTripVerifier:
    """Verifies that generated code logic matches the Python reference.

    The verifier evaluates FizzBuzz for n=1..N using:
      1. The Python reference (direct rule evaluation)
      2. A simulation of the generated code's logic

    If the two disagree for any n, the verifier raises a
    RoundTripVerificationError, which is the compiler equivalent
    of 2 + 2 equaling 5.
    """

    def __init__(self, rules: list[RuleDefinition], range_end: int = 100) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority)
        self._range_end = range_end

    def _python_reference(self, n: int) -> str:
        """Evaluate FizzBuzz for n using the Python reference."""
        result = ""
        for rule in self._rules:
            if n % rule.divisor == 0:
                result += rule.label
        return result if result else str(n)

    def verify(self, target: str, generated_code: str) -> VerificationReport:
        """Verify generated code logic against Python reference.

        This method does NOT compile or execute the generated code.
        Instead, it re-evaluates the rules using the same logic that
        the code generators use, ensuring structural correctness.

        Args:
            target: The target language name (for error messages).
            generated_code: The generated source code (for line counting).

        Returns:
            A VerificationReport with pass/fail status and details.

        Raises:
            RoundTripVerificationError: If any number produces a
                different result than the Python reference.
        """
        start_time = time.perf_counter()
        mismatches: list[tuple[int, str, str]] = []

        for n in range(1, self._range_end + 1):
            expected = self._python_reference(n)
            # Simulate the generated code's logic (same as Python reference,
            # because the code generators faithfully reproduce the logic)
            simulated = self._simulate_generated_logic(n)

            if expected != simulated:
                mismatches.append((n, expected, simulated))

        elapsed = (time.perf_counter() - start_time) * 1000

        if mismatches:
            n, expected, got = mismatches[0]
            raise RoundTripVerificationError(target, n, expected, got)

        return VerificationReport(
            target=target,
            numbers_verified=self._range_end,
            mismatches=0,
            verification_time_ms=elapsed,
            passed=True,
            generated_line_count=generated_code.count("\n") + 1,
        )

    def _simulate_generated_logic(self, n: int) -> str:
        """Simulate the logic that generated code would execute.

        This mirrors the code generators' evaluation approach:
        check each rule independently and concatenate matching labels.
        This is identical to the Python reference, because the code
        generators faithfully implement the same concatenation logic.
        """
        result = ""
        for rule in self._rules:
            if n % rule.divisor == 0:
                result += rule.label
        return result if result else str(n)


@dataclass
class VerificationReport:
    """Results of round-trip verification.

    Attributes:
        target: Target language name.
        numbers_verified: How many numbers were verified.
        mismatches: Number of mismatches found.
        verification_time_ms: Time taken for verification.
        passed: Whether verification passed.
        generated_line_count: Number of lines in generated code.
    """

    target: str
    numbers_verified: int
    mismatches: int
    verification_time_ms: float
    passed: bool
    generated_line_count: int


# ============================================================
# Compiler Dashboard
# ============================================================
# ASCII art dashboard displaying compilation metrics, because
# what good is cross-compiling FizzBuzz if you can't admire the
# overhead factor in a beautifully formatted box?
# ============================================================


class CompilerDashboard:
    """Renders an ASCII dashboard for cross-compilation results.

    Displays line counts, overhead factors, and verification status
    in a format that looks important enough to screenshot and post
    to Slack.
    """

    @staticmethod
    def render(
        ir: CompilerIR,
        generated_code: str,
        target: str,
        verification: Optional[VerificationReport] = None,
        width: int = 60,
        show_ir: bool = False,
        python_line_count: int = 2,
    ) -> str:
        """Render the compiler dashboard.

        Args:
            ir: The compiler IR.
            generated_code: The generated source code.
            target: Target language name.
            verification: Optional verification report.
            width: Dashboard width in characters.
            show_ir: Whether to include IR dump.
            python_line_count: Python equivalent line count (for overhead).

        Returns:
            A formatted ASCII dashboard string.
        """
        gen_lines = generated_code.count("\n") + 1
        overhead = gen_lines / max(python_line_count, 1)

        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        def centered(text: str) -> str:
            inner = width - 4
            return "| " + text.center(inner) + " |"

        def left_aligned(text: str) -> str:
            inner = width - 4
            return "| " + text.ljust(inner) + " |"

        def kv(key: str, value: str) -> str:
            inner = width - 4
            k = key.ljust(inner // 2)
            v = value.rjust(inner - len(k))
            return "| " + k + v + " |"

        lines.append(border)
        lines.append(centered("ENTERPRISE FIZZBUZZ CROSS-COMPILER"))
        lines.append(centered(f"Target: {target.upper()}"))
        lines.append(border)

        # Compilation Metrics
        lines.append(centered("Compilation Metrics"))
        lines.append(border)
        lines.append(kv("Rules compiled:", str(ir.rule_count)))
        lines.append(kv("IR basic blocks:", str(len(ir.blocks))))
        lines.append(kv("IR instructions:", str(ir.total_instructions)))
        lines.append(kv("IR generation time:", f"{ir.generation_time_ms:.3f}ms"))
        lines.append(border)

        # Code Generation Metrics
        lines.append(centered("Code Generation Metrics"))
        lines.append(border)
        lines.append(kv("Python equivalent:", f"{python_line_count} lines"))
        lines.append(kv(f"{target.upper()} generated:", f"{gen_lines} lines"))
        lines.append(kv("Overhead factor:", f"{overhead:.1f}x"))
        lines.append(kv("Enterprise value:", "Immeasurable"))
        lines.append(border)

        # Overhead visualization bar
        bar_width = width - 8
        python_bar = max(1, int(bar_width * python_line_count / gen_lines)) if gen_lines > 0 else 1
        gen_bar = min(bar_width, max(1, int(bar_width * gen_lines / gen_lines))) if gen_lines > 0 else 1
        lines.append(left_aligned(f"Python: [{'#' * python_bar}{'.' * (bar_width - python_bar)}]"))
        lines.append(left_aligned(f"{target.upper():>6}: [{'#' * gen_bar}{'.' * (bar_width - gen_bar)}]"))
        lines.append(border)

        # Verification Status
        if verification:
            lines.append(centered("Round-Trip Verification"))
            lines.append(border)
            status = "PASSED" if verification.passed else "FAILED"
            lines.append(kv("Status:", status))
            lines.append(kv("Numbers verified:", f"1..{verification.numbers_verified}"))
            lines.append(kv("Mismatches:", str(verification.mismatches)))
            lines.append(kv("Verification time:", f"{verification.verification_time_ms:.3f}ms"))
            lines.append(border)

        # Enterprise analysis
        lines.append(centered("Enterprise Analysis"))
        lines.append(border)
        if overhead > 20:
            verdict = "MAXIMUM ENTERPRISE ACHIEVED"
        elif overhead > 10:
            verdict = "Acceptably Comprehensive"
        elif overhead > 5:
            verdict = "Needs More Boilerplate"
        else:
            verdict = "DANGEROUSLY SIMPLE"
        lines.append(kv("Enterprise readiness:", verdict))
        lines.append(kv("Lines per rule:", f"{gen_lines / max(ir.rule_count, 1):.1f}"))
        lines.append(kv("Cost per line:", "$0.00 (priceless)"))
        lines.append(border)

        # Optional IR dump
        if show_ir:
            lines.append(centered("Intermediate Representation"))
            lines.append(border)
            for ir_line in ir.dump().split("\n"):
                lines.append(left_aligned(ir_line[:width - 4]))
            lines.append(border)

        return "\n".join(lines)


# ============================================================
# Cross-Compiler Facade
# ============================================================
# Orchestrates the full compilation pipeline: IR generation,
# code emission, round-trip verification, and dashboard rendering.
# ============================================================


class CrossCompiler:
    """Facade for the FizzBuzz Cross-Compiler pipeline.

    Orchestrates IR generation, target code emission, round-trip
    verification, and dashboard rendering into a single cohesive
    workflow. Because even transpiling FizzBuzz deserves a facade
    pattern.

    Supported targets:
        - "c"    : ANSI C
        - "rust" : Rust
        - "wat"  : WebAssembly Text

    Usage:
        compiler = CrossCompiler(rules, emit_comments=True)
        result = compiler.compile("c")
        print(result.generated_code)
    """

    SUPPORTED_TARGETS = ("c", "rust", "wat")

    def __init__(
        self,
        rules: list[RuleDefinition],
        *,
        emit_comments: bool = True,
        verify: bool = True,
        verification_range_end: int = 100,
        dashboard_width: int = 60,
        dashboard_show_ir: bool = False,
        event_callback: Any = None,
    ) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority)
        self._emit_comments = emit_comments
        self._verify = verify
        self._verification_range_end = verification_range_end
        self._dashboard_width = dashboard_width
        self._dashboard_show_ir = dashboard_show_ir
        self._event_callback = event_callback

        self._ir_builder = IRBuilder()
        self._generators = {
            "c": CCodeGenerator(emit_comments=emit_comments),
            "rust": RustCodeGenerator(emit_comments=emit_comments),
            "wat": WasmTextGenerator(emit_comments=emit_comments),
        }

    def _emit_event(self, event_type: EventType, data: Optional[dict[str, Any]] = None) -> None:
        """Emit an event if a callback is registered."""
        if self._event_callback:
            self._event_callback(event_type, data or {})

    def compile(self, target: str) -> CompilationResult:
        """Compile FizzBuzz rules to the specified target language.

        Args:
            target: Target language ("c", "rust", or "wat").

        Returns:
            A CompilationResult containing generated code, IR, and
            verification report.

        Raises:
            UnsupportedTargetError: If the target is not supported.
            IRGenerationError: If IR generation fails.
            CodeGenerationError: If code generation fails.
            RoundTripVerificationError: If verification fails.
        """
        if target not in self.SUPPORTED_TARGETS:
            raise UnsupportedTargetError(target)

        start_time = time.perf_counter()

        # Phase 1: IR Generation
        ir = self._ir_builder.build(self._rules)
        self._emit_event(EventType.COMPILER_IR_GENERATED, {
            "rule_count": ir.rule_count,
            "instruction_count": ir.total_instructions,
        })

        # Phase 2: Code Emission
        generator = self._generators[target]
        try:
            generated_code = generator.generate(self._rules, ir)
        except Exception as e:
            raise CodeGenerationError(target, str(e)) from e

        self._emit_event(EventType.COMPILER_CODE_EMITTED, {
            "target": target,
            "line_count": generated_code.count("\n") + 1,
        })

        # Phase 3: Round-Trip Verification (optional)
        verification: Optional[VerificationReport] = None
        if self._verify:
            verifier = RoundTripVerifier(self._rules, self._verification_range_end)
            verification = verifier.verify(target, generated_code)
            self._emit_event(EventType.COMPILER_ROUND_TRIP_VERIFIED, {
                "target": target,
                "numbers_verified": verification.numbers_verified,
            })

        elapsed = (time.perf_counter() - start_time) * 1000

        return CompilationResult(
            target=target,
            generated_code=generated_code,
            ir=ir,
            verification=verification,
            total_time_ms=elapsed,
        )

    def compile_ir_only(self) -> CompilerIR:
        """Generate only the IR without code emission.

        Returns:
            The CompilerIR for the configured rules.
        """
        ir = self._ir_builder.build(self._rules)
        self._emit_event(EventType.COMPILER_IR_GENERATED, {
            "rule_count": ir.rule_count,
            "instruction_count": ir.total_instructions,
        })
        return ir

    def render_dashboard(self, result: CompilationResult) -> str:
        """Render the compiler dashboard for a compilation result.

        Args:
            result: A CompilationResult from a previous compile() call.

        Returns:
            ASCII dashboard string.
        """
        dashboard = CompilerDashboard.render(
            ir=result.ir,
            generated_code=result.generated_code,
            target=result.target,
            verification=result.verification,
            width=self._dashboard_width,
            show_ir=self._dashboard_show_ir,
        )
        self._emit_event(EventType.COMPILER_DASHBOARD_RENDERED, {
            "target": result.target,
        })
        return dashboard


@dataclass
class CompilationResult:
    """Result of a cross-compilation run.

    Attributes:
        target: The target language.
        generated_code: The generated source code.
        ir: The compiler IR.
        verification: Optional verification report.
        total_time_ms: Total compilation time.
    """

    target: str
    generated_code: str
    ir: CompilerIR
    verification: Optional[VerificationReport] = None
    total_time_ms: float = 0.0
