"""
Enterprise FizzBuzz Platform - FizzLinguistics NLP Test Suite

Comprehensive verification of the natural language processing engine,
including tokenization, POS tagging, dependency parsing, named entity
recognition, sentiment analysis, and perplexity computation. These tests
ensure that the linguistic analysis of FizzBuzz output is grammatically
and semantically correct.

Linguistic accuracy is non-negotiable: an incorrect sentiment score
could misrepresent the emotional valence of a FizzBuzz classification,
constituting a violation of the Enterprise FizzBuzz Linguistic
Compliance Standard (EFLCS).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzlinguistics import (
    DependencyParser,
    DependencyRelation,
    DependencyTree,
    EntityType,
    LinguisticsMiddleware,
    LinguisticsPipeline,
    NamedEntityRecognizer,
    POSTag,
    POSTagger,
    PerplexityCalculator,
    SentimentAnalyzer,
    Token,
    Tokenizer,
)
from enterprise_fizzbuzz.domain.exceptions.fizzlinguistics import (
    DependencyParseError,
    PerplexityError,
    TokenizationError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Tokenizer Tests
# ============================================================


class TestTokenizer:
    def test_fizzbuzz_tokens(self):
        tok = Tokenizer()
        tokens = tok.tokenize("Fizz Buzz FizzBuzz 15")
        texts = [t.text for t in tokens]
        assert "Fizz" in texts
        assert "Buzz" in texts
        assert "FizzBuzz" in texts
        assert "15" in texts

    def test_fizzbuzz_recognized_as_single_token(self):
        tok = Tokenizer()
        tokens = tok.tokenize("FizzBuzz")
        assert len(tokens) == 1
        assert tokens[0].text == "FizzBuzz"

    def test_empty_string(self):
        tok = Tokenizer()
        tokens = tok.tokenize("")
        assert len(tokens) == 0

    def test_null_byte_raises(self):
        tok = Tokenizer()
        with pytest.raises(TokenizationError):
            tok.tokenize("Fizz\x00Buzz")

    def test_token_positions(self):
        tok = Tokenizer()
        tokens = tok.tokenize("Fizz Buzz")
        assert tokens[0].start == 0
        assert tokens[0].end == 4


# ============================================================
# POS Tagger Tests
# ============================================================


class TestPOSTagger:
    def test_fizz_tagged_as_noun(self):
        tagger = POSTagger()
        tokens = [Token(text="Fizz", start=0, end=4)]
        tagged = tagger.tag(tokens)
        assert tagged[0].pos == POSTag.NOUN

    def test_number_tagged_as_numeral(self):
        tagger = POSTagger()
        tokens = [Token(text="42", start=0, end=2)]
        tagged = tagger.tag(tokens)
        assert tagged[0].pos == POSTag.NUMERAL

    def test_punctuation_tagged(self):
        tagger = POSTagger()
        tokens = [Token(text=".", start=0, end=1)]
        tagged = tagger.tag(tokens)
        assert tagged[0].pos == POSTag.PUNCT

    def test_known_verb_tagged(self):
        tagger = POSTagger()
        tokens = [Token(text="is", start=0, end=2)]
        tagged = tagger.tag(tokens)
        assert tagged[0].pos == POSTag.VERB


# ============================================================
# Dependency Parser Tests
# ============================================================


class TestDependencyParser:
    def test_single_noun_is_root(self):
        parser = DependencyParser()
        tokens = [Token(text="Fizz", start=0, end=4, pos=POSTag.NOUN)]
        tree = parser.parse(tokens)
        assert tree.root_index == 0

    def test_numeral_depends_on_noun(self):
        parser = DependencyParser()
        tokens = [
            Token(text="Fizz", start=0, end=4, pos=POSTag.NOUN),
            Token(text="3", start=5, end=6, pos=POSTag.NUMERAL),
        ]
        tree = parser.parse(tokens)
        deps = tree.get_dependents(0)
        assert 1 in deps

    def test_empty_tokens_raises(self):
        parser = DependencyParser()
        with pytest.raises(DependencyParseError):
            parser.parse([])

    def test_tree_has_arcs(self):
        parser = DependencyParser()
        tokens = [
            Token(text="Fizz", start=0, end=4, pos=POSTag.NOUN),
            Token(text="Buzz", start=5, end=9, pos=POSTag.NOUN),
            Token(text="15", start=10, end=12, pos=POSTag.NUMERAL),
        ]
        tree = parser.parse(tokens)
        assert len(tree.arcs) == 2


# ============================================================
# Named Entity Recognition Tests
# ============================================================


class TestNER:
    def test_fizz_recognized(self):
        ner = NamedEntityRecognizer()
        tokens = [Token(text="Fizz", start=0, end=4)]
        entities = ner.recognize(tokens)
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.FIZZ_LABEL

    def test_number_recognized(self):
        ner = NamedEntityRecognizer()
        tokens = [Token(text="42", start=0, end=2)]
        entities = ner.recognize(tokens)
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.NUMBER

    def test_fizzbuzz_recognized(self):
        ner = NamedEntityRecognizer()
        tokens = [Token(text="FizzBuzz", start=0, end=8)]
        entities = ner.recognize(tokens)
        assert entities[0].entity_type == EntityType.FIZZBUZZ_LABEL

    def test_confidence_is_one(self):
        ner = NamedEntityRecognizer()
        tokens = [Token(text="Buzz", start=0, end=4)]
        entities = ner.recognize(tokens)
        assert entities[0].confidence == 1.0


# ============================================================
# Sentiment Analysis Tests
# ============================================================


class TestSentimentAnalyzer:
    def test_fizzbuzz_positive(self):
        sa = SentimentAnalyzer()
        tokens = [Token(text="FizzBuzz", start=0, end=8)]
        result = sa.analyze(tokens)
        assert result.score > 0
        assert result.label == "positive"

    def test_number_neutral(self):
        sa = SentimentAnalyzer()
        tokens = [Token(text="7", start=0, end=1)]
        result = sa.analyze(tokens)
        assert result.label == "neutral"

    def test_error_negative(self):
        sa = SentimentAnalyzer()
        tokens = [Token(text="error", start=0, end=5)]
        result = sa.analyze(tokens)
        assert result.score < 0
        assert result.label == "negative"

    def test_empty_tokens_neutral(self):
        sa = SentimentAnalyzer()
        result = sa.analyze([])
        assert result.label == "neutral"


# ============================================================
# Perplexity Tests
# ============================================================


class TestPerplexityCalculator:
    def test_fizzbuzz_sequence_perplexity(self):
        calc = PerplexityCalculator()
        tokens = [
            Token(text="Fizz", start=0, end=4),
            Token(text="Buzz", start=5, end=9),
            Token(text="FizzBuzz", start=10, end=18),
        ]
        result = calc.compute(tokens)
        assert result.perplexity > 0
        assert result.sequence_length == 3

    def test_empty_sequence_raises(self):
        calc = PerplexityCalculator()
        with pytest.raises(PerplexityError):
            calc.compute([])

    def test_numeric_tokens_use_numeric_probability(self):
        calc = PerplexityCalculator()
        tokens = [Token(text="42", start=0, end=2)]
        result = calc.compute(tokens)
        assert result.perplexity > 0


# ============================================================
# Pipeline Tests
# ============================================================


class TestLinguisticsPipeline:
    def test_full_pipeline(self):
        pipeline = LinguisticsPipeline()
        result = pipeline.analyze("Fizz Buzz FizzBuzz 15")
        assert "tokens" in result
        assert "sentiment" in result
        assert "perplexity" in result
        assert "entities" in result


# ============================================================
# Middleware Tests
# ============================================================


class TestLinguisticsMiddleware:
    def test_middleware_injects_sentiment(self):
        mw = LinguisticsMiddleware()
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert "linguistics_sentiment_score" in result.metadata
        assert "linguistics_sentiment_label" in result.metadata

    def test_middleware_injects_perplexity(self):
        mw = LinguisticsMiddleware()
        ctx = _make_context(15, "FizzBuzz")
        result = mw.process(ctx, _identity_handler)
        assert "linguistics_perplexity" in result.metadata

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = LinguisticsMiddleware()
        assert isinstance(mw, IMiddleware)
