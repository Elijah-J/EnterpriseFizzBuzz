"""Feature descriptor for the Compliance Chatbot subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ComplianceChatbotFeature(FeatureDescriptor):
    name = "compliance_chatbot"
    description = "AI-powered regulatory compliance chatbot for GDPR, SOX, and HIPAA consultations"
    middleware_priority = 0
    cli_flags = [
        ("--chatbot", {"type": str, "metavar": "QUESTION", "default": None,
                       "help": 'Ask the regulatory compliance chatbot a GDPR/SOX/HIPAA question (e.g. --chatbot "Is erasing FizzBuzz results GDPR compliant?")'}),
        ("--chatbot-interactive", {"action": "store_true", "default": False,
                                   "help": "Start an interactive compliance chatbot REPL for ongoing regulatory consultations"}),
        ("--chatbot-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the compliance chatbot session dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            bool(getattr(args, "chatbot", None)),
            getattr(args, "chatbot_interactive", False),
            getattr(args, "chatbot_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.compliance_chatbot import (
            ChatbotDashboard as ComplianceChatbotDashboard,
            ComplianceChatbot,
        )

        chatbot = ComplianceChatbot(
            max_history=config.compliance_chatbot_max_history,
            include_citations=config.compliance_chatbot_include_citations,
            bob_commentary_enabled=config.compliance_chatbot_bob_commentary,
            formality_level=config.compliance_chatbot_formality_level,
            bob_stress_level=config.compliance_officer_stress_level,
        )

        if args.chatbot_interactive:
            chatbot.interactive_repl()
            if args.chatbot_dashboard:
                print(ComplianceChatbotDashboard.render_session(
                    chatbot.session,
                    width=config.compliance_chatbot_dashboard_width,
                ))
            return 0

        if args.chatbot:
            try:
                response = chatbot.ask(args.chatbot)
                print(ComplianceChatbotDashboard.render_response(
                    response,
                    width=config.compliance_chatbot_dashboard_width,
                ))
                print(f"  Bob's stress level: {chatbot.bob_stress_level:.1f}%\n")
                if args.chatbot_dashboard:
                    print(ComplianceChatbotDashboard.render_session(
                        chatbot.session,
                        width=config.compliance_chatbot_dashboard_width,
                    ))
            except Exception as e:
                print(f"\n  Compliance Chatbot Error: {e}\n")
                return 1
            return 0

        if args.chatbot_dashboard:
            print("\n  No chatbot query provided. Use --chatbot or --chatbot-interactive.\n")
            return 0

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
