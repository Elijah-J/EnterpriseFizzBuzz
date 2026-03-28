"""
Enterprise FizzBuzz Platform - FizzLinguistics Natural Language Processing Engine

Provides tokenization, part-of-speech tagging, dependency parsing, named
entity recognition, sentiment analysis, and language model perplexity
computation for the linguistic analysis of FizzBuzz output text.

The FizzBuzz output stream constitutes a natural language corpus with
highly predictable lexical properties: the vocabulary consists of
exactly four token classes ("Fizz", "Buzz", "FizzBuzz", and numeric
literals). Despite this constrained vocabulary, the sequence exhibits
rich syntactic structure when viewed as a context-free language over
the alphabet {F, B, FB, N} with production rules governed by modular
arithmetic.

The POS tagger uses a rule-based approach optimized for the FizzBuzz
domain. The dependency parser constructs projective trees using the
arc-eager transition system. Sentiment analysis applies a lexicon-based
approach where "Fizz" carries positive valence (divisibility is desirable)
and plain numbers carry neutral valence.

All NLP computations use pure Python. No external NLP libraries are
required.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzlinguistics import (
    DependencyParseError,
    LinguisticsMiddlewareError,
    NERError,
    POSTaggingError,
    PerplexityError,
    SentimentAnalysisError,
    TokenizationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Maximum sequence length for tokenization
MAX_SEQUENCE_LENGTH = 100000


# ============================================================
# Enums
# ============================================================


class POSTag(Enum):
    """Part-of-speech tags for FizzBuzz linguistic analysis."""

    NOUN = auto()       # "Fizz", "Buzz", "FizzBuzz"
    NUMERAL = auto()    # numeric values
    PUNCT = auto()      # punctuation
    CONJ = auto()       # conjunction
    DET = auto()        # determiner
    VERB = auto()       # action words
    ADJ = auto()        # adjectives
    ADV = auto()        # adverbs
    UNKNOWN = auto()


class EntityType(Enum):
    """Named entity types recognized in FizzBuzz output."""

    FIZZ_LABEL = auto()
    BUZZ_LABEL = auto()
    FIZZBUZZ_LABEL = auto()
    NUMBER = auto()
    RANGE = auto()
    UNKNOWN = auto()


class DependencyRelation(Enum):
    """Syntactic dependency relations."""

    ROOT = auto()
    SUBJECT = auto()
    OBJECT = auto()
    MODIFIER = auto()
    COMPOUND = auto()
    NUMMOD = auto()
    PUNCT = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass
class Token:
    """A linguistic token with surface form and metadata."""

    text: str
    start: int
    end: int
    pos: POSTag = POSTag.UNKNOWN
    entity_type: EntityType = EntityType.UNKNOWN


@dataclass
class DependencyArc:
    """A directed arc in a dependency tree."""

    head: int  # index of head token
    dependent: int  # index of dependent token
    relation: DependencyRelation


@dataclass
class DependencyTree:
    """A projective dependency tree over a token sequence."""

    tokens: list[Token]
    arcs: list[DependencyArc]
    root_index: int

    def get_dependents(self, head_idx: int) -> list[int]:
        """Get all direct dependents of a token."""
        return [arc.dependent for arc in self.arcs if arc.head == head_idx]

    def get_head(self, dep_idx: int) -> Optional[int]:
        """Get the head of a dependent token."""
        for arc in self.arcs:
            if arc.dependent == dep_idx:
                return arc.head
        return None


@dataclass
class NamedEntity:
    """A recognized named entity in text."""

    text: str
    entity_type: EntityType
    start: int
    end: int
    confidence: float


@dataclass
class SentimentResult:
    """Sentiment analysis result for a text span."""

    text: str
    score: float  # [-1.0, 1.0]
    label: str  # "positive", "negative", "neutral"
    confidence: float


@dataclass
class PerplexityResult:
    """Language model perplexity measurement."""

    perplexity: float
    cross_entropy: float
    sequence_length: int
    vocabulary_size: int


# ============================================================
# Tokenizer
# ============================================================


class Tokenizer:
    """Rule-based tokenizer optimized for FizzBuzz output.

    Segments input text into tokens using whitespace and punctuation
    boundaries. Recognizes the core FizzBuzz vocabulary (Fizz, Buzz,
    FizzBuzz) and numeric literals as distinct token types.
    """

    # Patterns for tokenization
    _TOKEN_PATTERN = re.compile(r"FizzBuzz|Fizz|Buzz|\d+|[^\s\d]+|\s+")

    def tokenize(self, text: str) -> list[Token]:
        """Tokenize input text into a list of tokens."""
        if len(text) > MAX_SEQUENCE_LENGTH:
            raise TokenizationError(
                text[:50], f"Sequence length {len(text)} exceeds maximum {MAX_SEQUENCE_LENGTH}"
            )

        if "\x00" in text:
            raise TokenizationError(text[:50], "Input contains null bytes")

        tokens: list[Token] = []
        for match in self._TOKEN_PATTERN.finditer(text):
            t = match.group()
            if t.strip():  # Skip pure whitespace
                tokens.append(Token(
                    text=t,
                    start=match.start(),
                    end=match.end(),
                ))

        return tokens


# ============================================================
# POS Tagger
# ============================================================


class POSTagger:
    """Rule-based part-of-speech tagger for FizzBuzz domain text.

    Uses a lexicon of known FizzBuzz terms combined with pattern
    rules for numeric literals and punctuation. The tagger achieves
    100% accuracy on well-formed FizzBuzz output, which is the only
    corpus that matters.
    """

    _LEXICON = {
        "Fizz": POSTag.NOUN,
        "Buzz": POSTag.NOUN,
        "FizzBuzz": POSTag.NOUN,
        "is": POSTag.VERB,
        "the": POSTag.DET,
        "and": POSTag.CONJ,
        "or": POSTag.CONJ,
        "not": POSTag.ADV,
        "divisible": POSTag.ADJ,
        "by": POSTag.ADV,
    }

    def tag(self, tokens: list[Token]) -> list[Token]:
        """Assign POS tags to each token in the sequence."""
        tagged = []
        for token in tokens:
            t = Token(
                text=token.text,
                start=token.start,
                end=token.end,
                pos=self._classify(token.text),
                entity_type=token.entity_type,
            )
            tagged.append(t)
        return tagged

    def _classify(self, text: str) -> POSTag:
        """Classify a single token's part of speech."""
        if text in self._LEXICON:
            return self._LEXICON[text]
        if text.isdigit():
            return POSTag.NUMERAL
        if all(c in ".,;:!?-()[]{}\"'" for c in text):
            return POSTag.PUNCT
        return POSTag.NOUN  # Default to noun for unknown tokens


# ============================================================
# Dependency Parser
# ============================================================


class DependencyParser:
    """Arc-eager transition-based dependency parser.

    Constructs projective dependency trees from POS-tagged token
    sequences. Uses a deterministic oracle that prioritizes NOUN
    tokens as heads and assigns NUMERAL and ADJ tokens as dependents.
    The resulting tree captures the syntactic structure of FizzBuzz
    output for downstream semantic analysis.
    """

    def parse(self, tokens: list[Token]) -> DependencyTree:
        """Parse a token sequence into a dependency tree."""
        if not tokens:
            raise DependencyParseError("", "Empty token sequence")

        arcs: list[DependencyArc] = []

        # Find root: first NOUN or first token
        root_idx = 0
        for i, t in enumerate(tokens):
            if t.pos == POSTag.NOUN:
                root_idx = i
                break

        # Build arcs: all other tokens depend on the root or nearest noun
        current_head = root_idx
        for i in range(len(tokens)):
            if i == root_idx:
                continue

            # Determine relation based on POS
            if tokens[i].pos == POSTag.NUMERAL:
                relation = DependencyRelation.NUMMOD
            elif tokens[i].pos == POSTag.ADJ:
                relation = DependencyRelation.MODIFIER
            elif tokens[i].pos == POSTag.PUNCT:
                relation = DependencyRelation.PUNCT
            elif tokens[i].pos == POSTag.NOUN:
                relation = DependencyRelation.COMPOUND
            else:
                relation = DependencyRelation.OBJECT

            arcs.append(DependencyArc(
                head=current_head,
                dependent=i,
                relation=relation,
            ))

        return DependencyTree(
            tokens=tokens,
            arcs=arcs,
            root_index=root_idx,
        )


# ============================================================
# Named Entity Recognizer
# ============================================================


class NamedEntityRecognizer:
    """Rule-based NER for FizzBuzz output text.

    Recognizes FizzBuzz-specific entity types: FIZZ_LABEL, BUZZ_LABEL,
    FIZZBUZZ_LABEL, and NUMBER entities. Recognition confidence is
    based on exact match (1.0) or pattern match (0.8).
    """

    _ENTITY_MAP = {
        "FizzBuzz": EntityType.FIZZBUZZ_LABEL,
        "Fizz": EntityType.FIZZ_LABEL,
        "Buzz": EntityType.BUZZ_LABEL,
    }

    def recognize(self, tokens: list[Token]) -> list[NamedEntity]:
        """Recognize named entities in a token sequence."""
        entities: list[NamedEntity] = []

        for token in tokens:
            if token.text in self._ENTITY_MAP:
                entities.append(NamedEntity(
                    text=token.text,
                    entity_type=self._ENTITY_MAP[token.text],
                    start=token.start,
                    end=token.end,
                    confidence=1.0,
                ))
            elif token.text.isdigit():
                entities.append(NamedEntity(
                    text=token.text,
                    entity_type=EntityType.NUMBER,
                    start=token.start,
                    end=token.end,
                    confidence=1.0,
                ))

        return entities


# ============================================================
# Sentiment Analyzer
# ============================================================


class SentimentAnalyzer:
    """Lexicon-based sentiment analyzer for FizzBuzz output.

    Assigns sentiment scores based on the FizzBuzz domain lexicon:
    - "FizzBuzz" is the most positive outcome (dual divisibility)
    - "Fizz" and "Buzz" carry moderate positive sentiment
    - Plain numbers are neutral
    - Errors carry negative sentiment

    The composite sentiment of a sequence is the weighted average
    of individual token sentiments.
    """

    _LEXICON = {
        "FizzBuzz": 1.0,
        "Fizz": 0.6,
        "Buzz": 0.5,
        "error": -0.8,
        "fail": -0.9,
        "invalid": -0.7,
    }

    def analyze(self, tokens: list[Token]) -> SentimentResult:
        """Compute aggregate sentiment for a token sequence."""
        if not tokens:
            return SentimentResult(
                text="", score=0.0, label="neutral", confidence=0.0
            )

        total_score = 0.0
        scored_count = 0
        text_parts = []

        for token in tokens:
            text_parts.append(token.text)
            if token.text in self._LEXICON:
                total_score += self._LEXICON[token.text]
                scored_count += 1
            elif token.text.isdigit():
                total_score += 0.0  # Neutral
                scored_count += 1

        avg_score = total_score / max(scored_count, 1)
        # Clamp to [-1, 1]
        avg_score = max(-1.0, min(1.0, avg_score))

        if avg_score > 0.1:
            label = "positive"
        elif avg_score < -0.1:
            label = "negative"
        else:
            label = "neutral"

        confidence = scored_count / max(len(tokens), 1)

        return SentimentResult(
            text=" ".join(text_parts),
            score=avg_score,
            label=label,
            confidence=confidence,
        )


# ============================================================
# Perplexity Calculator
# ============================================================


class PerplexityCalculator:
    """Language model perplexity estimator for FizzBuzz sequences.

    Computes the perplexity of a FizzBuzz output sequence under a
    unigram language model. Perplexity measures how "surprised" the
    model is by the sequence — lower perplexity indicates more
    predictable output, which is expected for well-formed FizzBuzz.
    """

    def __init__(self) -> None:
        # Unigram probabilities for FizzBuzz tokens
        # In a standard 1-100 FizzBuzz: 27 Fizz, 14 Buzz, 6 FizzBuzz, 53 numeric
        self._probs: dict[str, float] = {
            "Fizz": 27.0 / 100.0,
            "Buzz": 14.0 / 100.0,
            "FizzBuzz": 6.0 / 100.0,
            "_NUMERIC": 53.0 / 100.0,
        }

    def compute(self, tokens: list[Token]) -> PerplexityResult:
        """Compute perplexity of the token sequence."""
        if not tokens:
            raise PerplexityError(0, "Empty token sequence")

        log_prob_sum = 0.0
        n = len(tokens)

        for token in tokens:
            if token.text in self._probs:
                p = self._probs[token.text]
            elif token.text.isdigit():
                p = self._probs["_NUMERIC"]
            else:
                p = 1.0 / 1000.0  # Smoothed probability for unknown tokens

            if p <= 0:
                raise PerplexityError(n, f"Non-positive probability for token '{token.text}'")

            log_prob_sum += math.log(p)

        cross_entropy = -log_prob_sum / n
        perplexity = math.exp(cross_entropy)

        vocab_size = len(self._probs)

        return PerplexityResult(
            perplexity=perplexity,
            cross_entropy=cross_entropy,
            sequence_length=n,
            vocabulary_size=vocab_size,
        )


# ============================================================
# FizzLinguistics Pipeline
# ============================================================


class LinguisticsPipeline:
    """Complete NLP pipeline for FizzBuzz output analysis.

    Chains tokenization, POS tagging, dependency parsing, NER,
    sentiment analysis, and perplexity computation into a single
    pipeline that produces a comprehensive linguistic profile of
    FizzBuzz output.
    """

    def __init__(self) -> None:
        self.tokenizer = Tokenizer()
        self.pos_tagger = POSTagger()
        self.parser = DependencyParser()
        self.ner = NamedEntityRecognizer()
        self.sentiment = SentimentAnalyzer()
        self.perplexity = PerplexityCalculator()

    def analyze(self, text: str) -> dict[str, Any]:
        """Run the complete NLP pipeline on input text."""
        tokens = self.tokenizer.tokenize(text)
        tagged = self.pos_tagger.tag(tokens)
        tree = self.parser.parse(tagged)
        entities = self.ner.recognize(tagged)
        sentiment = self.sentiment.analyze(tagged)
        perplexity = self.perplexity.compute(tagged)

        return {
            "tokens": tagged,
            "dependency_tree": tree,
            "entities": entities,
            "sentiment": sentiment,
            "perplexity": perplexity,
        }


# ============================================================
# FizzLinguistics Middleware
# ============================================================


class LinguisticsMiddleware(IMiddleware):
    """Injects NLP analysis into the FizzBuzz pipeline.

    For each number evaluated, the middleware runs the linguistics
    pipeline on the FizzBuzz output text and injects sentiment,
    entity, and perplexity data into the processing context.
    """

    def __init__(self, pipeline: Optional[LinguisticsPipeline] = None) -> None:
        self._pipeline = pipeline or LinguisticsPipeline()

    def get_name(self) -> str:
        return "fizzlinguistics"

    def get_priority(self) -> int:
        return 278

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Inject linguistic context and delegate to next handler."""
        try:
            output = ""
            if context.results:
                output = context.results[-1].output

            if output:
                analysis = self._pipeline.analyze(output)
                sentiment = analysis["sentiment"]
                perplexity = analysis["perplexity"]
                entities = analysis["entities"]

                context.metadata["linguistics_sentiment_score"] = sentiment.score
                context.metadata["linguistics_sentiment_label"] = sentiment.label
                context.metadata["linguistics_perplexity"] = perplexity.perplexity
                context.metadata["linguistics_entity_count"] = len(entities)
                context.metadata["linguistics_token_count"] = len(analysis["tokens"])

        except Exception as exc:
            logger.error("FizzLinguistics middleware error: %s", exc)
            context.metadata["linguistics_error"] = str(exc)

        return next_handler(context)
