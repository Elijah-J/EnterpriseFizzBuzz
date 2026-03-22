"""
Enterprise FizzBuzz Platform - FizzLang DSL Tests

Comprehensive tests for the FizzLang domain-specific programming language:
lexer, parser, type checker, interpreter, standard library, REPL, and
dashboard — because even a Turing-incomplete language deserves 55 tests.

Every test validates that a language designed exclusively for modulo
arithmetic works correctly for modulo arithmetic, which is both the
highest and lowest bar a programming language can clear.
"""

import io
import unittest

from enterprise_fizzbuzz.domain.exceptions import (
    FizzLangError,
    FizzLangLexerError,
    FizzLangParseError,
    FizzLangRuntimeError,
    FizzLangTypeError,
)
from enterprise_fizzbuzz.infrastructure.fizzlang import (
    ASTNode,
    BinaryOpNode,
    CompilationUnit,
    EvalResult,
    EvaluateNode,
    FizzLangDashboard,
    FizzLangREPL,
    FunctionCallNode,
    IdentifierNode,
    Interpreter,
    LetNode,
    Lexer,
    LiteralNode,
    NVarNode,
    Parser,
    ProgramNode,
    RuleNode,
    StdLib,
    Token,
    TokenType,
    TypeChecker,
    UnaryOpNode,
    compile_program,
    format_ast,
    run_program,
)


# ======================================================================
# Lexer Tests
# ======================================================================

class TestLexer(unittest.TestCase):
    """Tests for the FizzLang hand-written character scanner."""

    def test_empty_source(self):
        tokens = Lexer("").tokenize()
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].type, TokenType.EOF)

    def test_integer_literal(self):
        tokens = Lexer("42").tokenize()
        self.assertEqual(tokens[0].type, TokenType.INTEGER)
        self.assertEqual(tokens[0].value, 42)

    def test_string_literal(self):
        tokens = Lexer('"Fizz"').tokenize()
        self.assertEqual(tokens[0].type, TokenType.STRING)
        self.assertEqual(tokens[0].value, "Fizz")

    def test_string_escape_sequences(self):
        tokens = Lexer(r'"hello\nworld"').tokenize()
        self.assertEqual(tokens[0].value, "hello\nworld")

    def test_keywords_case_insensitive(self):
        tokens = Lexer("RULE When emit EVALUATE").tokenize()
        self.assertEqual(tokens[0].type, TokenType.RULE)
        self.assertEqual(tokens[1].type, TokenType.WHEN)
        self.assertEqual(tokens[2].type, TokenType.EMIT)
        self.assertEqual(tokens[3].type, TokenType.EVALUATE)

    def test_n_variable(self):
        tokens = Lexer("n").tokenize()
        self.assertEqual(tokens[0].type, TokenType.N_VAR)

    def test_operators(self):
        tokens = Lexer("+ - * / % == != < > <= >=").tokenize()
        expected = [
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
            TokenType.SLASH, TokenType.PERCENT, TokenType.EQUALS,
            TokenType.NOT_EQUALS, TokenType.LESS_THAN, TokenType.GREATER_THAN,
            TokenType.LESS_EQUAL, TokenType.GREATER_EQUAL,
        ]
        for i, tt in enumerate(expected):
            self.assertEqual(tokens[i].type, tt, f"Token {i} mismatch")

    def test_comments_skipped(self):
        tokens = Lexer("# this is a comment\n42").tokenize()
        # Should have NEWLINE, INTEGER, EOF
        non_eof = [t for t in tokens if t.type != TokenType.EOF]
        int_tokens = [t for t in non_eof if t.type == TokenType.INTEGER]
        self.assertEqual(len(int_tokens), 1)
        self.assertEqual(int_tokens[0].value, 42)

    def test_unknown_character_raises(self):
        with self.assertRaises(FizzLangLexerError) as ctx:
            Lexer("@").tokenize()
        self.assertIn("@", str(ctx.exception))

    def test_unterminated_string_raises(self):
        with self.assertRaises(FizzLangLexerError):
            Lexer('"hello').tokenize()

    def test_identifier(self):
        tokens = Lexer("my_var").tokenize()
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].value, "my_var")

    def test_line_tracking(self):
        tokens = Lexer("a\nb\nc").tokenize()
        ident_tokens = [t for t in tokens if t.type == TokenType.IDENTIFIER]
        self.assertEqual(ident_tokens[0].line, 1)
        self.assertEqual(ident_tokens[1].line, 2)
        self.assertEqual(ident_tokens[2].line, 3)

    def test_boolean_literals(self):
        tokens = Lexer("true false").tokenize()
        self.assertEqual(tokens[0].type, TokenType.TRUE)
        self.assertEqual(tokens[1].type, TokenType.FALSE)

    def test_parentheses_and_comma(self):
        tokens = Lexer("(a, b)").tokenize()
        self.assertEqual(tokens[0].type, TokenType.LPAREN)
        self.assertEqual(tokens[2].type, TokenType.COMMA)
        self.assertEqual(tokens[4].type, TokenType.RPAREN)


# ======================================================================
# Parser Tests
# ======================================================================

class TestParser(unittest.TestCase):
    """Tests for the FizzLang recursive-descent parser."""

    def _parse(self, source: str) -> ProgramNode:
        tokens = Lexer(source).tokenize()
        return Parser(tokens).parse()

    def test_empty_program(self):
        program = self._parse("")
        self.assertIsInstance(program, ProgramNode)
        self.assertEqual(len(program.statements), 0)

    def test_rule_statement(self):
        program = self._parse('rule fizz when n % 3 == 0 emit "Fizz"')
        self.assertEqual(len(program.statements), 1)
        rule = program.statements[0]
        self.assertIsInstance(rule, RuleNode)
        self.assertEqual(rule.name, "fizz")
        self.assertEqual(rule.priority, 0)

    def test_rule_with_priority(self):
        program = self._parse('rule fizz when n % 3 == 0 emit "Fizz" priority 1')
        rule = program.statements[0]
        self.assertIsInstance(rule, RuleNode)
        self.assertEqual(rule.priority, 1)

    def test_let_statement(self):
        program = self._parse("let x = 42")
        self.assertEqual(len(program.statements), 1)
        let = program.statements[0]
        self.assertIsInstance(let, LetNode)
        self.assertEqual(let.name, "x")

    def test_evaluate_statement(self):
        program = self._parse("evaluate 1 to 100")
        self.assertEqual(len(program.statements), 1)
        ev = program.statements[0]
        self.assertIsInstance(ev, EvaluateNode)

    def test_binary_expression(self):
        program = self._parse("let x = 3 + 5")
        let = program.statements[0]
        self.assertIsInstance(let.value, BinaryOpNode)
        self.assertEqual(let.value.op, "+")

    def test_unary_expression(self):
        program = self._parse("let x = -42")
        let = program.statements[0]
        self.assertIsInstance(let.value, UnaryOpNode)
        self.assertEqual(let.value.op, "-")

    def test_function_call(self):
        program = self._parse("let x = is_prime(7)")
        let = program.statements[0]
        self.assertIsInstance(let.value, FunctionCallNode)
        self.assertEqual(let.value.name, "is_prime")
        self.assertEqual(len(let.value.args), 1)

    def test_operator_precedence(self):
        program = self._parse("let x = 2 + 3 * 4")
        let = program.statements[0]
        # Should be (2 + (3 * 4))
        self.assertIsInstance(let.value, BinaryOpNode)
        self.assertEqual(let.value.op, "+")
        self.assertIsInstance(let.value.right, BinaryOpNode)
        self.assertEqual(let.value.right.op, "*")

    def test_parenthesized_expression(self):
        program = self._parse("let x = (2 + 3) * 4")
        let = program.statements[0]
        # Should be ((2 + 3) * 4)
        self.assertIsInstance(let.value, BinaryOpNode)
        self.assertEqual(let.value.op, "*")
        self.assertIsInstance(let.value.left, BinaryOpNode)
        self.assertEqual(let.value.left.op, "+")

    def test_boolean_operators(self):
        program = self._parse('rule fb when n % 3 == 0 and n % 5 == 0 emit "FizzBuzz"')
        rule = program.statements[0]
        self.assertIsInstance(rule.condition, BinaryOpNode)
        self.assertEqual(rule.condition.op, "and")

    def test_not_operator(self):
        program = self._parse('rule notfizz when not n % 3 == 0 emit "NotFizz"')
        rule = program.statements[0]
        self.assertIsInstance(rule.condition, UnaryOpNode)
        self.assertEqual(rule.condition.op, "not")

    def test_parse_error_unexpected_token(self):
        with self.assertRaises(FizzLangParseError):
            self._parse("42 + 42")  # Not a statement

    def test_multiple_statements(self):
        source = 'rule fizz when n % 3 == 0 emit "Fizz"\nrule buzz when n % 5 == 0 emit "Buzz"\nevaluate 1 to 15'
        program = self._parse(source)
        self.assertEqual(len(program.statements), 3)


# ======================================================================
# Type Checker Tests
# ======================================================================

class TestTypeChecker(unittest.TestCase):
    """Tests for the FizzLang AST-level semantic validator."""

    def _check(self, source: str, strict: bool = True) -> list[str]:
        unit = compile_program(source, strict_type_checking=strict)
        return unit.warnings

    def test_valid_program(self):
        warnings = self._check('rule fizz when n % 3 == 0 emit "Fizz"\nevaluate 1 to 10')
        self.assertEqual(warnings, [])

    def test_duplicate_rule_name_raises(self):
        with self.assertRaises(FizzLangTypeError):
            self._check('rule fizz when n % 3 == 0 emit "Fizz"\nrule fizz when n % 5 == 0 emit "Buzz"')

    def test_undefined_variable_raises(self):
        with self.assertRaises(FizzLangTypeError):
            self._check('rule fizz when x % 3 == 0 emit "Fizz"')

    def test_let_binding_resolves(self):
        warnings = self._check('let divisor = 3\nrule fizz when n % divisor == 0 emit "Fizz"')
        self.assertEqual(warnings, [])

    def test_unknown_function_raises(self):
        with self.assertRaises(FizzLangTypeError) as ctx:
            self._check("let x = unknown_fn(42)")
        self.assertIn("unknown_fn", str(ctx.exception))

    def test_wrong_arity_raises(self):
        with self.assertRaises(FizzLangTypeError):
            self._check("let x = is_prime(1, 2)")

    def test_empty_program_warns(self):
        warnings = self._check("")
        self.assertTrue(len(warnings) > 0)

    def test_negative_priority_raises(self):
        with self.assertRaises(FizzLangTypeError):
            self._check('rule fizz when n % 3 == 0 emit "Fizz" priority -1')


# ======================================================================
# Standard Library Tests
# ======================================================================

class TestStdLib(unittest.TestCase):
    """Tests for the FizzLang 3-function standard library."""

    def test_is_prime_basic(self):
        self.assertFalse(StdLib.is_prime(0))
        self.assertFalse(StdLib.is_prime(1))
        self.assertTrue(StdLib.is_prime(2))
        self.assertTrue(StdLib.is_prime(3))
        self.assertFalse(StdLib.is_prime(4))
        self.assertTrue(StdLib.is_prime(5))
        self.assertTrue(StdLib.is_prime(97))

    def test_is_prime_large(self):
        self.assertTrue(StdLib.is_prime(104729))
        self.assertFalse(StdLib.is_prime(104730))

    def test_fizzbuzz_function(self):
        self.assertEqual(StdLib.fizzbuzz(1), "1")
        self.assertEqual(StdLib.fizzbuzz(3), "Fizz")
        self.assertEqual(StdLib.fizzbuzz(5), "Buzz")
        self.assertEqual(StdLib.fizzbuzz(15), "FizzBuzz")
        self.assertEqual(StdLib.fizzbuzz(30), "FizzBuzz")

    def test_range_inclusive(self):
        result = StdLib.range_inclusive(1, 5)
        self.assertEqual(result, [1, 2, 3, 4, 5])

    def test_range_single_element(self):
        result = StdLib.range_inclusive(7, 7)
        self.assertEqual(result, [7])


# ======================================================================
# Interpreter Tests
# ======================================================================

class TestInterpreter(unittest.TestCase):
    """Tests for the FizzLang tree-walking interpreter."""

    def test_standard_fizzbuzz(self):
        source = '''
rule fizz when n % 3 == 0 emit "Fizz"
rule buzz when n % 5 == 0 emit "Buzz"
evaluate 1 to 15
'''
        results = run_program(source)
        self.assertEqual(len(results), 15)
        # Check specific values
        outputs = {r.number: r.output for r in results}
        self.assertEqual(outputs[1], "1")
        self.assertEqual(outputs[3], "Fizz")
        self.assertEqual(outputs[5], "Buzz")
        self.assertEqual(outputs[15], "FizzBuzz")

    def test_fizzbuzz_correctness_full_range(self):
        """The standard FizzBuzz program MUST produce correct results."""
        source = '''
rule fizz when n % 3 == 0 emit "Fizz"
rule buzz when n % 5 == 0 emit "Buzz"
evaluate 1 to 100
'''
        results = run_program(source)
        self.assertEqual(len(results), 100)
        for r in results:
            n = r.number
            expected = ""
            if n % 3 == 0:
                expected += "Fizz"
            if n % 5 == 0:
                expected += "Buzz"
            if not expected:
                expected = str(n)
            self.assertEqual(r.output, expected, f"Failed for n={n}")

    def test_let_binding(self):
        source = '''
let divisor = 3
rule fizz when n % divisor == 0 emit "Fizz"
evaluate 1 to 6
'''
        results = run_program(source)
        outputs = {r.number: r.output for r in results}
        self.assertEqual(outputs[3], "Fizz")
        self.assertEqual(outputs[6], "Fizz")
        self.assertEqual(outputs[4], "4")

    def test_priority_ordering(self):
        """Rules with lower priority numbers should be applied first."""
        source = '''
rule buzz when n % 5 == 0 emit "Buzz" priority 2
rule fizz when n % 3 == 0 emit "Fizz" priority 1
evaluate 15 to 15
'''
        results = run_program(source)
        # Even though buzz was declared first, fizz has lower priority
        self.assertEqual(results[0].output, "FizzBuzz")

    def test_unmatched_numbers(self):
        source = '''
rule fizz when n % 3 == 0 emit "Fizz"
evaluate 1 to 4
'''
        results = run_program(source)
        outputs = {r.number: r.output for r in results}
        self.assertEqual(outputs[1], "1")
        self.assertEqual(outputs[2], "2")
        self.assertEqual(outputs[4], "4")

    def test_stdlib_is_prime_in_rule(self):
        source = '''
rule prime when is_prime(n) emit "Prime"
evaluate 1 to 10
'''
        results = run_program(source)
        outputs = {r.number: r.output for r in results}
        self.assertEqual(outputs[2], "Prime")
        self.assertEqual(outputs[3], "Prime")
        self.assertEqual(outputs[4], "4")
        self.assertEqual(outputs[7], "Prime")

    def test_stdlib_fizzbuzz_function(self):
        source = '''
let result = fizzbuzz(15)
'''
        # Just check it compiles and runs without error
        unit = compile_program(source)
        interp = Interpreter(stdlib_enabled=True)
        interp.interpret(unit.ast)
        self.assertEqual(interp.env["result"], "FizzBuzz")

    def test_arithmetic_expressions(self):
        source = "let x = (2 + 3) * 4"
        unit = compile_program(source)
        interp = Interpreter()
        interp.interpret(unit.ast)
        self.assertEqual(interp.env["x"], 20)

    def test_division_by_zero(self):
        source = "let x = 10 / 0"
        with self.assertRaises(FizzLangRuntimeError):
            run_program(source)

    def test_modulo_by_zero(self):
        source = "let x = 10 % 0"
        with self.assertRaises(FizzLangRuntimeError):
            run_program(source)

    def test_boolean_and_or(self):
        source = '''
rule fb when n % 3 == 0 and n % 5 == 0 emit "FizzBuzz"
evaluate 15 to 15
'''
        results = run_program(source)
        self.assertEqual(results[0].output, "FizzBuzz")

    def test_comparison_operators(self):
        source = '''
rule small when n < 5 emit "Small"
evaluate 1 to 6
'''
        results = run_program(source)
        outputs = {r.number: r.output for r in results}
        self.assertEqual(outputs[1], "Small")
        self.assertEqual(outputs[4], "Small")
        self.assertEqual(outputs[5], "5")
        self.assertEqual(outputs[6], "6")

    def test_stdlib_disabled(self):
        source = "let x = is_prime(7)"
        with self.assertRaises(FizzLangRuntimeError):
            unit = compile_program(source)
            interp = Interpreter(stdlib_enabled=False)
            interp.interpret(unit.ast)

    def test_n_outside_rule_raises(self):
        source = "let x = n"
        with self.assertRaises(FizzLangRuntimeError):
            run_program(source)


# ======================================================================
# Compilation Pipeline Tests
# ======================================================================

class TestCompilationPipeline(unittest.TestCase):
    """Tests for the compile_program and run_program convenience functions."""

    def test_compile_returns_unit(self):
        unit = compile_program('rule fizz when n % 3 == 0 emit "Fizz"')
        self.assertIsInstance(unit, CompilationUnit)
        self.assertIsInstance(unit.ast, ProgramNode)
        self.assertGreater(len(unit.tokens), 0)
        self.assertGreaterEqual(unit.compile_time_ms, 0)

    def test_program_too_long_raises(self):
        source = "a" * 100
        with self.assertRaises(FizzLangError):
            compile_program(source, max_program_length=10)

    def test_run_program_returns_results(self):
        results = run_program('rule fizz when n % 3 == 0 emit "Fizz"\nevaluate 1 to 3')
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 3)


# ======================================================================
# REPL Tests
# ======================================================================

class TestREPL(unittest.TestCase):
    """Tests for the FizzLang interactive REPL."""

    def _run_repl(self, inputs: list[str]) -> str:
        output = io.StringIO()
        input_iter = iter(inputs)

        def mock_input(prompt: str) -> str:
            try:
                return next(input_iter)
            except StopIteration:
                raise EOFError

        repl = FizzLangREPL(
            output_stream=output,
            input_fn=mock_input,
        )
        repl.run()
        return output.getvalue()

    def test_repl_help(self):
        output = self._run_repl([":help", ":quit"])
        self.assertIn("FizzLang REPL Commands", output)

    def test_repl_let_binding(self):
        output = self._run_repl(["let x = 42", ":quit"])
        self.assertIn("x = 42", output)

    def test_repl_rule_registration(self):
        output = self._run_repl(['rule fizz when n % 3 == 0 emit "Fizz"', ":quit"])
        self.assertIn("Rule 'fizz' registered", output)

    def test_repl_evaluate(self):
        output = self._run_repl([
            'rule fizz when n % 3 == 0 emit "Fizz"',
            "evaluate 1 to 3",
            ":quit",
        ])
        self.assertIn("1", output)
        self.assertIn("2", output)
        self.assertIn("Fizz", output)

    def test_repl_toggle_tokens(self):
        output = self._run_repl([":tokens", ":tokens", ":quit"])
        self.assertIn("Token display: ON", output)
        self.assertIn("Token display: OFF", output)

    def test_repl_eof_exit(self):
        output = self._run_repl([])
        self.assertIn("Goodbye", output)

    def test_repl_error_handling(self):
        output = self._run_repl(["@invalid", ":quit"])
        self.assertIn("Error", output)


# ======================================================================
# Dashboard Tests
# ======================================================================

class TestDashboard(unittest.TestCase):
    """Tests for the FizzLang ASCII dashboard."""

    def test_dashboard_renders(self):
        source = 'rule fizz when n % 3 == 0 emit "Fizz"\nevaluate 1 to 10'
        dashboard = FizzLangDashboard.render(source)
        self.assertIn("FizzLang Dashboard", dashboard)
        self.assertIn("Source Statistics", dashboard)

    def test_dashboard_with_results(self):
        source = 'rule fizz when n % 3 == 0 emit "Fizz"\nevaluate 1 to 10'
        results = run_program(source)
        dashboard = FizzLangDashboard.render(source, results=results)
        self.assertIn("Evaluation Results", dashboard)

    def test_complexity_index_below_brainfuck(self):
        source = 'rule fizz when n % 3 == 0 emit "Fizz"\nevaluate 1 to 10'
        dashboard = FizzLangDashboard.render(source)
        self.assertIn("BELOW BRAINFUCK", dashboard)

    def test_dashboard_invalid_source(self):
        dashboard = FizzLangDashboard.render("@@@invalid!!!")
        self.assertIn("Compilation failed", dashboard)


# ======================================================================
# Exception Tests
# ======================================================================

class TestExceptions(unittest.TestCase):
    """Tests for FizzLang exception hierarchy and career advice."""

    def test_lexer_error_has_career_advice(self):
        try:
            Lexer("@").tokenize()
        except FizzLangLexerError as e:
            self.assertIn("Career advice", str(e))
            self.assertEqual(e.error_code, "EFP-FL11")

    def test_parse_error_has_career_advice(self):
        try:
            tokens = Lexer("42").tokenize()
            Parser(tokens).parse()
        except FizzLangParseError as e:
            self.assertIn("Career advice", str(e))
            self.assertEqual(e.error_code, "EFP-FL12")

    def test_type_error_has_career_advice(self):
        try:
            compile_program('rule fizz when x == 0 emit "Fizz"')
        except FizzLangTypeError as e:
            self.assertIn("Career advice", str(e))
            self.assertEqual(e.error_code, "EFP-FL13")

    def test_runtime_error_has_career_advice(self):
        try:
            run_program("let x = 1 / 0")
        except FizzLangRuntimeError as e:
            self.assertIn("Career advice", str(e))
            self.assertEqual(e.error_code, "EFP-FL14")

    def test_base_error_inherits_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        e = FizzLangError("test")
        self.assertIsInstance(e, FizzBuzzError)


# ======================================================================
# AST Pretty-Printer Tests
# ======================================================================

class TestFormatAST(unittest.TestCase):
    """Tests for the AST pretty-printer."""

    def test_format_program(self):
        source = 'rule fizz when n % 3 == 0 emit "Fizz"\nevaluate 1 to 10'
        unit = compile_program(source)
        output = format_ast(unit.ast)
        self.assertIn("Program:", output)
        self.assertIn("Rule 'fizz'", output)
        self.assertIn("Evaluate", output)

    def test_format_literal(self):
        output = format_ast(LiteralNode(value=42))
        self.assertIn("42", output)

    def test_format_function_call(self):
        node = FunctionCallNode(name="is_prime", args=[LiteralNode(value=7)])
        output = format_ast(node)
        self.assertIn("is_prime(7)", output)


if __name__ == "__main__":
    unittest.main()
