"""Feature descriptor for the FizzFS in-memory virtual file system."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class VirtualFSFeature(FeatureDescriptor):
    name = "virtual_fs"
    description = "POSIX-like in-memory virtual file system with mount points for platform state"
    middleware_priority = 180
    cli_flags = [
        ("--fizzfs", {"action": "store_true", "default": False,
                      "help": "Enable FizzFS: POSIX-like in-memory virtual file system with mount points for platform state"}),
        ("--fizzfs-shell", {"action": "store_true", "default": False,
                            "help": "Launch the FizzShell interactive REPL for navigating the virtual file system"}),
        ("--fizzfs-cat", {"type": str, "metavar": "PATH", "default": None,
                          "help": "Read and display the contents of a virtual file (e.g. --fizzfs-cat /dev/fizz)"}),
        ("--fizzfs-ls", {"type": str, "metavar": "PATH", "default": None,
                         "help": "List the contents of a virtual directory (e.g. --fizzfs-ls /dev)"}),
        ("--fizzfs-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzFS ASCII dashboard with mount table, inode stats, and directory tree"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzfs", False)

    def has_early_exit(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzfs_shell", False),
            getattr(args, "fizzfs_cat", None) is not None,
            getattr(args, "fizzfs_ls", None) is not None,
            getattr(args, "fizzfs_dashboard", False) and not getattr(args, "fizzfs", False),
        ])

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.virtual_fs import (
            FizzShell,
            FSDashboard,
            create_fizzfs,
        )

        raw_config = config._get_raw_config_copy() if hasattr(config, '_get_raw_config_copy') else config._get_defaults()
        fizzfs, audit_prov = create_fizzfs(
            config_tree=raw_config,
            version=config.app_version,
        )
        audit_prov.append("FizzFS initialized (early exit mode)")

        if getattr(args, "fizzfs_shell", False):
            shell = FizzShell(fizzfs)
            shell.run()
            return 0

        if getattr(args, "fizzfs_cat", None):
            try:
                content = fizzfs.read_file(args.fizzfs_cat)
                print(content, end="")
            except Exception as e:
                print(f"\n  FizzFS Error: {e}\n")
                return 1
            return 0

        if getattr(args, "fizzfs_ls", None):
            try:
                entries = fizzfs.readdir(args.fizzfs_ls)
                for entry in entries:
                    prefix = "d" if entry.file_type.name == "DIRECTORY" else "-"
                    print(f"  {prefix} {entry.name}")
            except Exception as e:
                print(f"\n  FizzFS Error: {e}\n")
                return 1
            return 0

        if getattr(args, "fizzfs_dashboard", False):
            print(FSDashboard.render(fizzfs))
            return 0

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.virtual_fs import (
            FSMiddleware,
            create_fizzfs,
        )

        raw_config = config._get_raw_config_copy() if hasattr(config, '_get_raw_config_copy') else config._get_defaults()
        fizzfs_instance, fizzfs_audit = create_fizzfs(
            config_tree=raw_config,
            version=config.app_version,
        )
        fizzfs_audit.append("FizzFS initialized (pipeline mode)")

        middleware = FSMiddleware(fizzfs_instance)
        return fizzfs_instance, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FizzFS: Virtual File System ENABLED                     |\n"
            "  | Mount points: /proc /cache /sys /dev /audit             |\n"
            "  | Evaluation results stored at /eval/<number>             |\n"
            "  | Because everything is a file. Especially FizzBuzz.      |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "fizzfs_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.virtual_fs import FSDashboard
        fizzfs_instance = middleware.fs if hasattr(middleware, "fs") else None
        if fizzfs_instance is not None:
            return FSDashboard.render(fizzfs_instance)
        return "\n  FizzFS not enabled. Use --fizzfs to enable.\n"
