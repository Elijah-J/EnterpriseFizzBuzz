"""
Enterprise FizzBuzz Platform - Persistence Layer

A comprehensive suite of repository and Unit of Work implementations
for durably persisting FizzBuzz evaluation results across multiple
storage backends.

Supported backends:
  - in_memory:  A Python dict, the Ferrari of ephemeral storage.
  - sqlite:     Real SQL for real enterprise needs. Your FizzBuzz
                results now live in a b-tree. Congratulations.
  - filesystem: Individual JSON files, because every FizzBuzz result
                deserves its own file on disk with its own inode.

All backends implement the AbstractRepository and AbstractUnitOfWork
contracts from the application ports layer, ensuring that the business
logic remains blissfully decoupled from the storage mechanism — even
though the business logic is literally "n % 3".
"""

from enterprise_fizzbuzz.infrastructure.persistence.in_memory import (
    InMemoryRepository,
    InMemoryUnitOfWork,
)
from enterprise_fizzbuzz.infrastructure.persistence.sqlite import (
    SqliteRepository,
    SqliteUnitOfWork,
)
from enterprise_fizzbuzz.infrastructure.persistence.filesystem import (
    FileSystemRepository,
    FileSystemUnitOfWork,
)

__all__ = [
    "InMemoryRepository",
    "InMemoryUnitOfWork",
    "SqliteRepository",
    "SqliteUnitOfWork",
    "FileSystemRepository",
    "FileSystemUnitOfWork",
]
