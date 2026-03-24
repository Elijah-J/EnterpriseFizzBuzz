"""Feature descriptor for the Secrets Management Vault subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SecretsVaultFeature(FeatureDescriptor):
    name = "secrets_vault"
    description = "Shamir's Secret Sharing vault with encryption, rotation, scanning, and audit logging"
    middleware_priority = 88
    cli_flags = [
        ("--vault", {"action": "store_true", "default": False,
                     "help": "Enable the Secrets Management Vault with Shamir's Secret Sharing (the number 3 deserves better security)"}),
        ("--vault-unseal", {"action": "store_true", "default": False,
                            "help": "Automatically unseal the vault using generated shares (because manual key ceremonies are tedious)"}),
        ("--vault-status", {"action": "store_true", "default": False,
                            "help": "Display the vault status and seal state after execution"}),
        ("--vault-scan", {"action": "store_true", "default": False,
                          "help": "Run the AST-based secret scanner on the codebase (flags ALL integer literals)"}),
        ("--vault-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the comprehensive vault ASCII dashboard after execution"}),
        ("--vault-rotate", {"action": "store_true", "default": False,
                            "help": "Force an immediate rotation of all rotatable secrets"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "vault", False),
            getattr(args, "vault_unseal", False),
            getattr(args, "vault_status", False),
            getattr(args, "vault_scan", False),
            getattr(args, "vault_dashboard", False),
            getattr(args, "vault_rotate", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.secrets_vault import (
            DynamicSecretEngine,
            SecretRotationScheduler,
            SecretScanner,
            SecretStore,
            ShamirSecretSharing,
            VaultAccessPolicy,
            VaultAuditLog,
            VaultDashboard,
            VaultMiddleware,
            VaultSealManager,
        )

        shamir = ShamirSecretSharing(
            threshold=config.vault_shamir_threshold,
            num_shares=config.vault_shamir_num_shares,
        )
        vault_seal_manager = VaultSealManager(
            shamir=shamir,
            event_bus=event_bus,
        )
        vault_audit_log = VaultAuditLog()
        vault_access_policy = VaultAccessPolicy(config.vault_access_policies)

        unseal_shares = vault_seal_manager.initialize()

        if getattr(args, "vault_unseal", False) or getattr(args, "vault", False):
            for share in unseal_shares[:config.vault_shamir_threshold]:
                vault_seal_manager.submit_unseal_share(share)

        vault_middleware = None
        vault_secret_store = None
        vault_rotation_scheduler = None

        if not vault_seal_manager.is_sealed:
            master_key_bytes = vault_seal_manager.get_master_key_bytes()
            vault_secret_store = SecretStore(master_key_bytes)

            vault_secret_store.put(
                "fizzbuzz/rules/fizz_divisor", "3",
                metadata={"description": "The sacred Fizz divisor"},
            )
            vault_secret_store.put(
                "fizzbuzz/rules/buzz_divisor", "5",
                metadata={"description": "The venerable Buzz divisor"},
            )
            vault_secret_store.put(
                "fizzbuzz/blockchain/difficulty",
                str(getattr(args, "mining_difficulty", 2)),
                metadata={"description": "Proof-of-work mining difficulty"},
            )
            vault_secret_store.put(
                "fizzbuzz/ml/learning_rate", "0.1",
                metadata={"description": "Neural network learning rate"},
            )
            vault_secret_store.put(
                "fizzbuzz/cache/ttl_seconds", str(config.cache_ttl_seconds),
                metadata={"description": "Cache TTL in seconds"},
            )
            vault_secret_store.put(
                "fizzbuzz/sla/latency_threshold_ms",
                str(config.sla_latency_threshold_ms),
                metadata={"description": "SLA latency threshold"},
            )
            vault_secret_store.put(
                "fizzbuzz/infrastructure/token_secret",
                config.rbac_token_secret,
                metadata={"description": "RBAC token signing secret"},
            )

            if config.vault_rotation_enabled:
                import random as _vault_random
                vault_rotation_scheduler = SecretRotationScheduler(
                    secret_store=vault_secret_store,
                    rotatable_paths=config.vault_rotatable_secrets,
                    interval_evaluations=config.vault_rotation_interval,
                    event_bus=event_bus,
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/blockchain/difficulty",
                    lambda: str(_vault_random.randint(1, 5)),
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/ml/learning_rate",
                    lambda: str(round(_vault_random.uniform(0.001, 0.5), 4)),
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/cache/ttl_seconds",
                    lambda: str(_vault_random.randint(60, 7200)),
                )
                vault_rotation_scheduler.register_generator(
                    "fizzbuzz/sla/latency_threshold_ms",
                    lambda: str(round(_vault_random.uniform(10.0, 500.0), 1)),
                )

            vault_middleware = VaultMiddleware(
                seal_manager=vault_seal_manager,
                secret_store=vault_secret_store,
                audit_log=vault_audit_log,
                rotation_scheduler=vault_rotation_scheduler,
                event_bus=event_bus,
            )

        service = {
            "seal_manager": vault_seal_manager,
            "secret_store": vault_secret_store,
            "audit_log": vault_audit_log,
            "rotation_scheduler": vault_rotation_scheduler,
        }

        return service, vault_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "vault_dashboard", False) or getattr(args, "vault_status", False):
                return "\n  Vault not enabled. Use --vault to enable.\n"
            return None

        from enterprise_fizzbuzz.infrastructure.secrets_vault import VaultDashboard

        parts = []

        if getattr(args, "vault_dashboard", False):
            parts.append(VaultDashboard.render(
                seal_manager=middleware._seal_manager if hasattr(middleware, "_seal_manager") else None,
                secret_store=middleware._secret_store if hasattr(middleware, "_secret_store") else None,
                audit_log=middleware._audit_log if hasattr(middleware, "_audit_log") else None,
                rotation_scheduler=middleware._rotation_scheduler if hasattr(middleware, "_rotation_scheduler") else None,
                scan_findings=None,
                width=60,
            ))

        if getattr(args, "vault_status", False) and hasattr(middleware, "_seal_manager"):
            sm = middleware._seal_manager
            seal_status = "SEALED" if sm.is_sealed else "UNSEALED"
            init_status = "YES" if sm.is_initialized else "NO"
            parts.append(
                "  +---------------------------------------------------------+\n"
                "  | VAULT STATUS                                            |\n"
                "  +---------------------------------------------------------+\n"
                f"  | Status:     {seal_status:<44}|\n"
                f"  | Initialized: {init_status:<43}|\n"
                f"  | Shares:     {f'{sm.shares_submitted}/{sm.shares_required}':<44}|\n"
                "  +---------------------------------------------------------+"
            )

        return "\n".join(parts) if parts else None
