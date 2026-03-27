"""Feature descriptor for the FizzMail SMTP/IMAP email server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMailFeature(FeatureDescriptor):
    name = "fizzmail"
    description = "SMTP/IMAP email server with DKIM, SPF, DMARC, greylisting, and Maildir storage"
    middleware_priority = 120
    cli_flags = [
        ("--fizzmail", {"action": "store_true", "default": False,
                        "help": "Enable FizzMail: SMTP/IMAP email server with DKIM, SPF, DMARC, and Maildir storage"}),
        ("--fizzmail-smtp-port", {"type": int, "default": 2525,
                                  "help": "SMTP listen port (default: 2525)"}),
        ("--fizzmail-imap-port", {"type": int, "default": 1143,
                                  "help": "IMAP listen port (default: 1143)"}),
        ("--fizzmail-domain", {"type": str, "default": "fizzbuzz.local",
                               "help": "Mail domain (default: fizzbuzz.local)"}),
        ("--fizzmail-tls", {"action": "store_true", "default": True,
                            "help": "Enable STARTTLS support (default: enabled)"}),
        ("--fizzmail-auth", {"action": "store_true", "default": True,
                             "help": "Enable SMTP AUTH (default: enabled)"}),
        ("--fizzmail-dkim-sign", {"action": "store_true", "default": True,
                                  "help": "Enable outbound DKIM signing (default: enabled)"}),
        ("--fizzmail-dkim-verify", {"action": "store_true", "default": True,
                                    "help": "Enable inbound DKIM verification (default: enabled)"}),
        ("--fizzmail-spf", {"action": "store_true", "default": True,
                            "help": "Enable SPF validation (default: enabled)"}),
        ("--fizzmail-dmarc", {"action": "store_true", "default": True,
                              "help": "Enable DMARC evaluation (default: enabled)"}),
        ("--fizzmail-greylist", {"action": "store_true", "default": False,
                                 "help": "Enable greylisting for inbound mail"}),
        ("--fizzmail-rbl", {"action": "store_true", "default": False,
                            "help": "Enable RBL/DNSBL blocklist checking"}),
        ("--fizzmail-quota", {"type": int, "default": 104857600,
                              "help": "Default per-mailbox quota in bytes (default: 100MB)"}),
        ("--fizzmail-retry-max", {"type": int, "default": 5,
                                  "help": "Maximum delivery retry attempts (default: 5)"}),
        ("--fizzmail-relay", {"action": "store_true", "default": False,
                              "help": "Enable outbound relay delivery"}),
        ("--fizzmail-smart-host", {"type": str, "default": None,
                                   "help": "Smart host address for outbound relay"}),
        ("--fizzmail-send", {"type": str, "default": None,
                             "help": "Send a test email (format: from,to,subject,body)"}),
        ("--fizzmail-list-mailboxes", {"action": "store_true", "default": False,
                                       "help": "List all mailboxes and their message counts"}),
        ("--fizzmail-search", {"type": str, "default": None,
                               "help": "Search mailboxes for messages matching a query"}),
        ("--fizzmail-idle", {"action": "store_true", "default": False,
                             "help": "Show IMAP IDLE push notification simulation"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzmail", False),
            getattr(args, "fizzmail_send", None),
            getattr(args, "fizzmail_list_mailboxes", False),
            getattr(args, "fizzmail_search", None),
            getattr(args, "fizzmail_idle", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmail import (
            FizzMailMiddleware,
            create_fizzmail_subsystem,
        )

        smtp_server, imap_server, dashboard, middleware = create_fizzmail_subsystem(
            smtp_port=config.fizzmail_smtp_port,
            imap_port=config.fizzmail_imap_port,
            domain=config.fizzmail_domain,
            hostname=config.fizzmail_hostname,
            enable_tls=config.fizzmail_enable_tls,
            enable_auth=config.fizzmail_enable_auth,
            enable_dkim_sign=config.fizzmail_enable_dkim_sign,
            enable_dkim_verify=config.fizzmail_enable_dkim_verify,
            enable_spf=config.fizzmail_enable_spf,
            enable_dmarc=config.fizzmail_enable_dmarc,
            enable_greylist=config.fizzmail_enable_greylist,
            enable_rbl=config.fizzmail_enable_rbl,
            max_message_size=config.fizzmail_max_message_size,
            quota_default=config.fizzmail_quota_default,
            retry_max_attempts=config.fizzmail_retry_max_attempts,
            dashboard_width=config.fizzmail_dashboard_width,
        )

        return smtp_server, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzmail_list_mailboxes", False):
            parts.append(middleware.render_mailboxes())
        if getattr(args, "fizzmail_send", None):
            parts.append(middleware.render_send_result(args.fizzmail_send))
        if getattr(args, "fizzmail_search", None):
            parts.append(middleware.render_search_result(args.fizzmail_search))
        if getattr(args, "fizzmail_idle", False):
            parts.append(middleware.render_idle_simulation())
        if getattr(args, "fizzmail", False):
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
