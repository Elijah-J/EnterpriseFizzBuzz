"""Feature descriptor for the FizzLinguistics NLP engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzLinguisticsFeature(FeatureDescriptor):
    name = "fizzlinguistics"
    description = "Natural language processing engine with tokenization, POS tagging, dependency parsing, NER, and sentiment analysis"
    middleware_priority = 278
    cli_flags = [
        ("--fizzlinguistics", {"action": "store_true", "default": False,
                               "help": "Enable FizzLinguistics: apply NLP analysis to FizzBuzz output including sentiment and perplexity"}),
        ("--fizzlinguistics-sentiment", {"action": "store_true", "default": False,
                                         "help": "Enable lexicon-based sentiment analysis of FizzBuzz output"}),
        ("--fizzlinguistics-perplexity", {"action": "store_true", "default": False,
                                          "help": "Enable language model perplexity computation for FizzBuzz sequences"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzlinguistics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzlinguistics import (
            LinguisticsMiddleware,
            LinguisticsPipeline,
        )

        pipeline = LinguisticsPipeline()
        middleware = LinguisticsMiddleware(pipeline=pipeline)

        return pipeline, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZLINGUISTICS: NATURAL LANGUAGE PROCESSING ENGINE       |\n"
            "  |   Tokenizer, POS tagger, dependency parser               |\n"
            "  |   Named entity recognition and sentiment analysis         |\n"
            "  |   Language model perplexity computation                    |\n"
            "  +---------------------------------------------------------+"
        )
