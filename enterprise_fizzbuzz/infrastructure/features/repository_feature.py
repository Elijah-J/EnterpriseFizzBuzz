"""Feature descriptor for the Repository Pattern + Unit of Work subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class RepositoryFeature(FeatureDescriptor):
    name = "repository"
    description = "Repository Pattern with Unit of Work for result persistence (in-memory, SQLite, filesystem)"
    middleware_priority = 10
    cli_flags = [
        ("--repository", {"type": str, "choices": ["in_memory", "sqlite", "filesystem"],
                          "default": None, "metavar": "BACKEND",
                          "help": "Enable result persistence via Repository Pattern (in_memory | sqlite | filesystem)"}),
        ("--db-path", {"type": str, "default": None, "metavar": "PATH",
                       "help": "Path to SQLite database file (default: from config, only with --repository sqlite)"}),
        ("--results-dir", {"type": str, "default": None, "metavar": "PATH",
                           "help": "Path to results directory (default: from config, only with --repository filesystem)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        repo_backend = getattr(args, "repository", None)
        return repo_backend is not None and repo_backend != "none"

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.persistence import (
            FileSystemUnitOfWork,
            InMemoryUnitOfWork,
            SqliteUnitOfWork,
        )

        repo_backend = args.repository or config.repository_backend
        uow = None

        if repo_backend == "in_memory":
            uow = InMemoryUnitOfWork()
        elif repo_backend == "sqlite":
            db_path = getattr(args, "db_path", None) or config.repository_db_path
            uow = SqliteUnitOfWork(db_path=db_path)
        elif repo_backend == "filesystem":
            fs_path = getattr(args, "results_dir", None) or config.repository_fs_path
            uow = FileSystemUnitOfWork(base_dir=fs_path)

        if uow is not None:
            # Mark the UoW for recognition by __main__.py builder wiring
            uow._is_unit_of_work = True

            print(
                "  +---------------------------------------------------------+\n"
                f"  | REPOSITORY: {repo_backend.upper():<44}|\n"
                "  | FizzBuzz results will now be persisted via the          |\n"
                "  | Repository Pattern + Unit of Work, because storing      |\n"
                "  | modulo results in a variable was insufficiently durable.|\n"
                "  +---------------------------------------------------------+"
            )

        return uow, None
