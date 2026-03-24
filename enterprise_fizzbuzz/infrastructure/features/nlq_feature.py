"""Feature descriptor for the Natural Language Query Interface subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class NLQFeature(FeatureDescriptor):
    name = "nlq"
    description = "Natural Language Query interface for conversational FizzBuzz queries with intent parsing"
    middleware_priority = 200
    cli_flags = [
        ("--nlq", {"type": str, "metavar": "QUERY", "default": None,
                   "help": 'Execute a natural language FizzBuzz query (e.g. --nlq "Is 15 FizzBuzz?")'}),
        ("--nlq-interactive", {"action": "store_true", "default": False,
                               "help": "Start the NLQ interactive REPL for conversational FizzBuzz queries"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return bool(getattr(args, "nlq", None)) or getattr(args, "nlq_interactive", False)

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.compliance_chatbot import NLQEngine
        from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule

        nlq_rules = [ConcreteRule(rd) for rd in config.rules]

        nlq_engine = NLQEngine(
            rules=nlq_rules,
            max_results=config.nlq_max_results,
            max_query_length=config.nlq_max_query_length,
            history_size=config.nlq_history_size,
        )

        if getattr(args, "nlq_interactive", False):
            nlq_engine.interactive_repl()
            return 0

        if args.nlq:
            try:
                response = nlq_engine.process_query(args.nlq)
                print()
                print(f"  [{response.intent.name}] (executed in {response.execution_time_ms:.2f}ms)")
                print(response.result_text)
                print()
            except Exception as e:
                print(f"\n  NLQ Error: {e}\n")
                return 1
            return 0

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None
