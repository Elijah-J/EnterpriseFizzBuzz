"""Feature descriptor for the FizzContract smart contract VM."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SmartContractsFeature(FeatureDescriptor):
    name = "smart_contracts"
    description = "Gas-metered smart contract VM with FizzSolidity compiler and on-chain governance"
    middleware_priority = 139
    cli_flags = [
        ("--contract", {"action": "store_true", "default": False,
                        "help": "Enable FizzContract Smart Contract VM for gas-metered FizzBuzz evaluation"}),
        ("--contract-deploy", {"type": str, "default": None, "metavar": "SOURCE",
                               "help": "Deploy a FizzSolidity contract from the given source file or inline source"}),
        ("--contract-call", {"type": str, "default": None, "metavar": "ADDRESS",
                             "help": "Call a deployed contract by address for FizzBuzz evaluation"}),
        ("--contract-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzContract ASCII dashboard with deployed contracts, gas usage, and governance"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "contract", False),
            getattr(args, "contract_dashboard", False),
            getattr(args, "contract_deploy", None) is not None,
            getattr(args, "contract_call", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.smart_contracts import (
            ContractCompiler,
            ContractDeployer,
            ContractMiddleware,
            ExecutionContext,
            GovernanceVoting,
            compile_fizzbuzz_contract,
        )

        deployer = ContractDeployer()
        governance = GovernanceVoting()

        deployed_address = None
        if getattr(args, "contract_deploy", None) is not None:
            source = args.contract_deploy
            compiler = ContractCompiler()
            bytecode = compiler.compile(source)
            deployed_address = deployer.deploy(
                bytecode, deployer_addr="0x" + "a" * 40, source=source,
            )
        else:
            bytecode = compile_fizzbuzz_contract()
            deployed_address = deployer.deploy(
                bytecode, deployer_addr="0x" + "a" * 40,
            )

        target_address = getattr(args, "contract_call", None) or deployed_address

        exec_ctx = ExecutionContext(
            msg_sender="0x" + "b" * 40,
            tx_origin="0x" + "b" * 40,
            block_number=1,
        )
        middleware = ContractMiddleware(
            deployer=deployer,
            contract_address=target_address,
            context=exec_ctx,
        )

        return (deployer, governance), middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCONTRACT: SMART CONTRACT VM ENABLED                 |\n"
            "  |   Stack depth: 1024 (256-bit words)                    |\n"
            "  |   Gas metering: EVM-compatible per-opcode costs        |\n"
            "  |   Governance: 2/3 supermajority on-chain voting        |\n"
            "  |   Compiler: FizzSolidity single-pass emit              |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "contract_dashboard", False):
                return "  FizzContract not enabled. Use --contract to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.smart_contracts import (
            ContractDashboard,
            GovernanceVoting,
        )

        parts = []

        if getattr(args, "contract_dashboard", False):
            gas_metrics = getattr(middleware, "gas_metrics", None)
            # The deployer and governance are stored in the service tuple
            parts.append(ContractDashboard.render(
                middleware.deployer,
                GovernanceVoting(),
                gas_metrics=gas_metrics,
            ))

        return "\n".join(parts) if parts else None
