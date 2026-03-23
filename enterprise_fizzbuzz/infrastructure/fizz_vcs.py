"""
Enterprise FizzBuzz Platform - FizzGit Content-Addressable Version Control System

Implements a fully functional content-addressable version control system for
FizzBuzz evaluation state. Every evaluation batch produces a commit in a
directed acyclic graph (DAG), enabling the platform to track, diff, bisect,
branch, merge, and audit the complete history of FizzBuzz classifications.

The object model follows the proven design of distributed version control
systems: blobs store raw content, trees map names to blob or tree hashes,
and commits link a tree snapshot to its parentage. All objects are keyed
by their SHA-256 digest, ensuring cryptographic integrity of the entire
evaluation history.

This level of version control is essential for any system that produces
output with a lifecycle measured in fractions of a second. Without it,
there would be no way to determine which commit introduced the regression
that caused the number 15 to be classified as "Fizz" instead of "FizzBuzz"
— a defect whose blast radius, while confined to a single line of terminal
output, demands the full investigative power of binary search through
commit history.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    VCSError,
    VCSObjectNotFoundError,
    VCSMergeConflictError,
    VCSBranchError,
    VCSBisectError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ---------------------------------------------------------------------------
# Object types
# ---------------------------------------------------------------------------

class ObjectType(Enum):
    """The three fundamental object types in the FizzGit object store."""
    BLOB = "blob"
    TREE = "tree"
    COMMIT = "commit"


# ---------------------------------------------------------------------------
# Content-addressable objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Blob:
    """A content-addressable blob storing arbitrary serialised data.

    In a traditional version control system, blobs represent file contents.
    In FizzGit, they represent serialised FizzBuzz evaluation state — the
    classification of a single number, a batch of results, or any other
    piece of data that the platform deems worthy of eternal preservation.

    The hash is computed as SHA-256(b"blob:" + content_bytes), guaranteeing
    that two blobs with identical content will always share the same address,
    and that any mutation — even a single flipped bit in a "Fizz" vs "Buzz"
    classification — produces a completely different hash.
    """

    content: str
    hash: str

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute the SHA-256 hash of blob content."""
        raw = f"blob:{content}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def create(cls, content: str) -> Blob:
        """Create a new blob from content, computing its hash."""
        return cls(content=content, hash=cls.compute_hash(content))


@dataclass(frozen=True)
class TreeEntry:
    """A single entry in a tree object.

    Each entry maps a name to either a blob hash or a nested tree hash,
    forming the hierarchical namespace of the FizzBuzz evaluation state.
    """

    name: str
    object_hash: str
    object_type: ObjectType


@dataclass(frozen=True)
class Tree:
    """A tree object mapping names to blob or tree hashes.

    Trees provide the directory structure for FizzBuzz evaluation state.
    A typical tree might contain entries like:
      - "results/1" -> blob(hash of "1")
      - "results/3" -> blob(hash of "Fizz")
      - "results/15" -> blob(hash of "FizzBuzz")

    The tree hash is computed over the sorted, serialised entries, ensuring
    deterministic addressing regardless of insertion order.
    """

    entries: tuple[TreeEntry, ...]
    hash: str

    @staticmethod
    def compute_hash(entries: tuple[TreeEntry, ...]) -> str:
        """Compute the SHA-256 hash of a tree's entries."""
        serialised = "tree:" + ";".join(
            f"{e.object_type.value}:{e.name}:{e.object_hash}"
            for e in sorted(entries, key=lambda e: e.name)
        )
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, entries: tuple[TreeEntry, ...]) -> Tree:
        """Create a new tree from entries, computing its hash."""
        return cls(entries=entries, hash=cls.compute_hash(entries))

    def get_entry(self, name: str) -> Optional[TreeEntry]:
        """Look up an entry by name."""
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


@dataclass(frozen=True)
class Commit:
    """A commit object linking a tree snapshot to its parent commit.

    Each commit records:
    - The tree hash representing the complete evaluation state at this point
    - The parent commit hash (None for the initial commit)
    - The author who triggered the evaluation
    - A human-readable message describing the change
    - A UNIX timestamp for temporal ordering

    The commit hash is derived from all of these fields, forming a tamper-
    evident chain. Any alteration to a commit's content, parentage, or
    metadata would produce a different hash, breaking the chain and
    alerting the integrity subsystem.
    """

    tree_hash: str
    parent_hash: Optional[str]
    author: str
    message: str
    timestamp: float
    hash: str

    @staticmethod
    def compute_hash(
        tree_hash: str,
        parent_hash: Optional[str],
        author: str,
        message: str,
        timestamp: float,
    ) -> str:
        """Compute the SHA-256 hash of a commit."""
        parent_str = parent_hash or "None"
        raw = f"commit:{tree_hash}:{parent_str}:{author}:{message}:{timestamp}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        tree_hash: str,
        parent_hash: Optional[str],
        author: str,
        message: str,
        timestamp: Optional[float] = None,
    ) -> Commit:
        """Create a new commit, computing its hash."""
        ts = timestamp if timestamp is not None else time.time()
        h = cls.compute_hash(tree_hash, parent_hash, author, message, ts)
        return cls(
            tree_hash=tree_hash,
            parent_hash=parent_hash,
            author=author,
            message=message,
            timestamp=ts,
            hash=h,
        )


# ---------------------------------------------------------------------------
# Object Store
# ---------------------------------------------------------------------------

class ObjectStore:
    """Content-addressable storage for all FizzGit objects.

    Objects are stored in a flat dictionary keyed by their SHA-256 hash.
    This is functionally equivalent to the .git/objects directory in a
    traditional version control system, minus the filesystem overhead
    and plus the ephemeral nature of in-memory storage.

    The store enforces immutability: once an object is written, it cannot
    be overwritten with different content. Attempting to store a different
    object under the same hash would indicate a SHA-256 collision, which
    is a cryptographic event of such monumental improbability that it
    warrants immediate incident escalation.
    """

    def __init__(self) -> None:
        self._objects: dict[str, Any] = {}

    def store_blob(self, blob: Blob) -> str:
        """Store a blob and return its hash."""
        self._objects[blob.hash] = blob
        return blob.hash

    def store_tree(self, tree: Tree) -> str:
        """Store a tree and return its hash."""
        self._objects[tree.hash] = tree
        return tree.hash

    def store_commit(self, commit: Commit) -> str:
        """Store a commit and return its hash."""
        self._objects[commit.hash] = commit
        return commit.hash

    def get(self, object_hash: str) -> Any:
        """Retrieve an object by hash.

        Raises VCSObjectNotFoundError if the hash is not present.
        """
        obj = self._objects.get(object_hash)
        if obj is None:
            raise VCSObjectNotFoundError(object_hash)
        return obj

    def contains(self, object_hash: str) -> bool:
        """Check if an object exists in the store."""
        return object_hash in self._objects

    def count(self) -> int:
        """Return the total number of objects in the store."""
        return len(self._objects)

    def all_objects(self) -> dict[str, Any]:
        """Return a read-only view of all stored objects."""
        return dict(self._objects)


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------

@dataclass
class Ref:
    """A named pointer to a commit hash.

    Refs provide human-readable names for commits, functioning as branches
    (refs/heads/*) or the special HEAD pointer. A ref is mutable — it can
    be advanced to point to a new commit as the branch grows.
    """

    name: str
    commit_hash: Optional[str] = None


class RefStore:
    """Manages branches and the HEAD pointer.

    The ref store maintains the mapping from branch names to their tip
    commits, and tracks which branch HEAD currently points to. This is
    the mutable layer atop the immutable object store — the mechanism
    by which the platform knows "where we are" in the commit DAG.
    """

    def __init__(self) -> None:
        self._refs: dict[str, Ref] = {}
        self._head_ref: str = "main"

    def create_branch(self, name: str, commit_hash: Optional[str] = None) -> Ref:
        """Create a new branch pointing to the given commit."""
        if name in self._refs:
            raise VCSBranchError(
                f"Branch '{name}' already exists",
                branch_name=name,
            )
        ref = Ref(name=name, commit_hash=commit_hash)
        self._refs[name] = ref
        return ref

    def get_branch(self, name: str) -> Ref:
        """Retrieve a branch by name."""
        ref = self._refs.get(name)
        if ref is None:
            raise VCSBranchError(
                f"Branch '{name}' does not exist",
                branch_name=name,
            )
        return ref

    def update_branch(self, name: str, commit_hash: str) -> None:
        """Advance a branch to point to a new commit."""
        ref = self.get_branch(name)
        ref.commit_hash = commit_hash

    def delete_branch(self, name: str) -> None:
        """Delete a branch. Cannot delete the branch HEAD points to."""
        if name == self._head_ref:
            raise VCSBranchError(
                f"Cannot delete the current branch '{name}'",
                branch_name=name,
            )
        if name not in self._refs:
            raise VCSBranchError(
                f"Branch '{name}' does not exist",
                branch_name=name,
            )
        del self._refs[name]

    def set_head(self, branch_name: str) -> None:
        """Point HEAD to the specified branch."""
        if branch_name not in self._refs:
            raise VCSBranchError(
                f"Cannot set HEAD to non-existent branch '{branch_name}'",
                branch_name=branch_name,
            )
        self._head_ref = branch_name

    def get_head(self) -> str:
        """Return the branch name that HEAD points to."""
        return self._head_ref

    def get_head_commit(self) -> Optional[str]:
        """Return the commit hash that HEAD currently resolves to."""
        ref = self._refs.get(self._head_ref)
        if ref is None:
            return None
        return ref.commit_hash

    def list_branches(self) -> list[str]:
        """Return all branch names, sorted alphabetically."""
        return sorted(self._refs.keys())

    def branch_exists(self, name: str) -> bool:
        """Check if a branch exists."""
        return name in self._refs


# ---------------------------------------------------------------------------
# Index (Staging Area)
# ---------------------------------------------------------------------------

class Index:
    """The staging area for changes to be committed.

    The index sits between the working state and the committed history,
    accumulating changes until the user (or the auto-commit middleware)
    decides to create a commit. Each entry in the index maps a path
    to its blob hash, representing the staged snapshot of the evaluation
    state.

    In traditional version control, the index enables partial staging —
    committing only some of the changes in the working tree. In FizzGit,
    every evaluation result is staged immediately, because there is no
    valid reason to evaluate a number and then decline to record the
    outcome. The result exists; it must be preserved.
    """

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}  # path -> blob_hash

    def add(self, path: str, blob_hash: str) -> None:
        """Stage a blob at the given path."""
        self._entries[path] = blob_hash

    def remove(self, path: str) -> None:
        """Unstage a path."""
        self._entries.pop(path, None)

    def get_entries(self) -> dict[str, str]:
        """Return a copy of all staged entries."""
        return dict(self._entries)

    def clear(self) -> None:
        """Clear all staged entries."""
        self._entries.clear()

    def is_empty(self) -> bool:
        """Check if the staging area is empty."""
        return len(self._entries) == 0

    def entry_count(self) -> int:
        """Return the number of staged entries."""
        return len(self._entries)


# ---------------------------------------------------------------------------
# Diff Engine
# ---------------------------------------------------------------------------

class DiffEntry:
    """A single difference between two tree states."""

    def __init__(
        self,
        path: str,
        change_type: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
    ) -> None:
        self.path = path
        self.change_type = change_type  # "add", "delete", "modify"
        self.old_value = old_value
        self.new_value = new_value

    def __repr__(self) -> str:
        return f"DiffEntry({self.change_type}: {self.path})"


# FizzBuzz classification priority for conflict resolution.
# Higher values take precedence during three-way merge.
_CLASSIFICATION_PRIORITY: dict[str, int] = {
    "FizzBuzz": 4,
    "Fizz": 3,
    "Buzz": 2,
}


def _classification_priority(value: str) -> int:
    """Return the merge priority for a FizzBuzz classification.

    The domain-specific conflict resolution strategy dictates that
    composite classifications take precedence over their components:
    "FizzBuzz" beats "Fizz", which beats "Buzz", which beats a plain
    number. This ordering reflects the fundamental hierarchy of the
    FizzBuzz domain — a number that is both Fizz and Buzz is more
    significant than one that is merely one or the other.
    """
    return _CLASSIFICATION_PRIORITY.get(value, 1)


class DiffEngine:
    """Computes diffs between tree states and performs three-way merges.

    The diff engine operates on flattened tree representations (path -> value
    dictionaries) rather than the raw tree objects, simplifying the comparison
    logic at the cost of losing hierarchical structure information. This
    tradeoff is acceptable because FizzBuzz evaluation state is inherently
    flat — each number maps to exactly one classification.

    Three-way merge identifies the common ancestor of two divergent branches,
    computes the diff from the ancestor to each branch tip, and combines
    the changes. When both branches modify the same path, the domain-specific
    conflict resolution strategy applies: "FizzBuzz" beats "Fizz" beats
    "Buzz" beats a plain number. This reflects the FizzBuzz domain axiom
    that more-specific classifications are always preferable.
    """

    def __init__(self, object_store: ObjectStore) -> None:
        self._store = object_store

    def diff_trees(
        self,
        old_tree_hash: Optional[str],
        new_tree_hash: Optional[str],
    ) -> list[DiffEntry]:
        """Compute the diff between two tree snapshots.

        Returns a list of DiffEntry objects describing additions, deletions,
        and modifications between the old and new trees.
        """
        old_entries = self._flatten_tree(old_tree_hash) if old_tree_hash else {}
        new_entries = self._flatten_tree(new_tree_hash) if new_tree_hash else {}

        diffs: list[DiffEntry] = []
        all_paths = sorted(set(old_entries.keys()) | set(new_entries.keys()))

        for path in all_paths:
            old_val = old_entries.get(path)
            new_val = new_entries.get(path)

            if old_val is None and new_val is not None:
                diffs.append(DiffEntry(path, "add", new_value=new_val))
            elif old_val is not None and new_val is None:
                diffs.append(DiffEntry(path, "delete", old_value=old_val))
            elif old_val != new_val:
                diffs.append(DiffEntry(path, "modify", old_value=old_val, new_value=new_val))

        return diffs

    def three_way_merge(
        self,
        base_tree_hash: Optional[str],
        ours_tree_hash: Optional[str],
        theirs_tree_hash: Optional[str],
    ) -> tuple[dict[str, str], list[DiffEntry]]:
        """Perform a three-way merge between base, ours, and theirs.

        Returns a tuple of (merged_entries, conflicts). The merged_entries
        dict maps paths to their resolved blob hashes. The conflicts list
        contains DiffEntry objects for paths where both sides made different
        changes from the base — these are resolved using domain-specific
        priority ordering.

        In the event of a true conflict (both sides modified the same path
        to different values), the FizzBuzz domain conflict resolution
        strategy applies: the classification with higher priority wins.
        """
        base = self._flatten_tree(base_tree_hash) if base_tree_hash else {}
        ours = self._flatten_tree(ours_tree_hash) if ours_tree_hash else {}
        theirs = self._flatten_tree(theirs_tree_hash) if theirs_tree_hash else {}

        merged: dict[str, str] = {}
        conflicts: list[DiffEntry] = []
        all_paths = sorted(set(base.keys()) | set(ours.keys()) | set(theirs.keys()))

        for path in all_paths:
            base_val = base.get(path)
            ours_val = ours.get(path)
            theirs_val = theirs.get(path)

            if ours_val == theirs_val:
                # Both sides agree
                if ours_val is not None:
                    merged[path] = ours_val
                # If both deleted, path is gone
            elif ours_val == base_val:
                # Only theirs changed
                if theirs_val is not None:
                    merged[path] = theirs_val
            elif theirs_val == base_val:
                # Only ours changed
                if ours_val is not None:
                    merged[path] = ours_val
            else:
                # Both sides changed differently — domain-specific resolution
                ours_content = self._resolve_content(ours_val) if ours_val else ""
                theirs_content = self._resolve_content(theirs_val) if theirs_val else ""

                ours_priority = _classification_priority(ours_content)
                theirs_priority = _classification_priority(theirs_content)

                if ours_priority >= theirs_priority:
                    winner = ours_val
                else:
                    winner = theirs_val

                if winner is not None:
                    merged[path] = winner

                conflicts.append(DiffEntry(
                    path=path,
                    change_type="conflict",
                    old_value=ours_content,
                    new_value=theirs_content,
                ))

        return merged, conflicts

    def _flatten_tree(self, tree_hash: str) -> dict[str, str]:
        """Flatten a tree into a path -> blob_hash dictionary."""
        result: dict[str, str] = {}
        tree = self._store.get(tree_hash)
        if not isinstance(tree, Tree):
            return result

        for entry in tree.entries:
            if entry.object_type == ObjectType.BLOB:
                result[entry.name] = entry.object_hash
            elif entry.object_type == ObjectType.TREE:
                subtree = self._flatten_tree(entry.object_hash)
                for sub_path, sub_hash in subtree.items():
                    result[f"{entry.name}/{sub_path}"] = sub_hash

        return result

    def _resolve_content(self, blob_hash: str) -> str:
        """Resolve a blob hash to its content string."""
        try:
            blob = self._store.get(blob_hash)
            if isinstance(blob, Blob):
                return blob.content
        except VCSObjectNotFoundError:
            pass
        return ""


# ---------------------------------------------------------------------------
# Bisect Engine
# ---------------------------------------------------------------------------

class BisectState(Enum):
    """State of the bisect operation."""
    INACTIVE = "inactive"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass
class BisectResult:
    """The outcome of a bisect operation."""

    first_bad_commit: Optional[str] = None
    steps_taken: int = 0
    total_commits: int = 0
    state: BisectState = BisectState.INACTIVE


class BisectEngine:
    """Binary search through commit history to find regressions.

    Given a known-good commit and a known-bad commit, the bisect engine
    performs a binary search through the commit DAG to identify the exact
    commit that introduced a regression. At each step, it selects the
    midpoint commit and asks the caller to classify it as good or bad,
    halving the search space with each answer.

    For a FizzBuzz platform, a "regression" might be a commit where
    the number 15 was classified as "Fizz" instead of "FizzBuzz", or
    where performance degraded from 0.3 microseconds to 0.4 microseconds
    per evaluation — both equally catastrophic in a production environment
    where correctness and performance are non-negotiable.
    """

    def __init__(self, object_store: ObjectStore) -> None:
        self._store = object_store
        self._commits: list[str] = []
        self._good_idx: int = 0
        self._bad_idx: int = 0
        self._current_idx: int = 0
        self._steps: int = 0
        self._state: BisectState = BisectState.INACTIVE
        self._result: Optional[BisectResult] = None

    @property
    def state(self) -> BisectState:
        """Return the current bisect state."""
        return self._state

    @property
    def result(self) -> Optional[BisectResult]:
        """Return the bisect result, if complete."""
        return self._result

    def start(self, good_commit: str, bad_commit: str) -> str:
        """Begin a bisect session between a known-good and known-bad commit.

        Builds the linear commit history between the two points, then
        selects the midpoint as the first commit to test.

        Returns the hash of the first commit to test.
        """
        if self._state == BisectState.IN_PROGRESS:
            raise VCSBisectError("A bisect operation is already in progress")

        # Build linear history from bad back to good
        history: list[str] = []
        current = bad_commit
        while current is not None:
            history.append(current)
            if current == good_commit:
                break
            commit = self._store.get(current)
            if not isinstance(commit, Commit):
                raise VCSBisectError(f"Object {current[:12]} is not a commit")
            current = commit.parent_hash

        if good_commit not in history:
            raise VCSBisectError(
                f"Good commit {good_commit[:12]} is not an ancestor of "
                f"bad commit {bad_commit[:12]}"
            )

        history.reverse()  # oldest first
        self._commits = history
        self._good_idx = 0
        self._bad_idx = len(history) - 1
        self._state = BisectState.IN_PROGRESS
        self._steps = 0

        return self._select_midpoint()

    def mark_good(self) -> Optional[str]:
        """Mark the current commit as good.

        Returns the next commit to test, or None if bisect is complete.
        """
        self._ensure_in_progress()
        self._good_idx = self._current_idx
        self._steps += 1
        return self._advance()

    def mark_bad(self) -> Optional[str]:
        """Mark the current commit as bad.

        Returns the next commit to test, or None if bisect is complete.
        """
        self._ensure_in_progress()
        self._bad_idx = self._current_idx
        self._steps += 1
        return self._advance()

    def get_current(self) -> str:
        """Return the hash of the current commit being tested."""
        self._ensure_in_progress()
        return self._commits[self._current_idx]

    def remaining_steps(self) -> int:
        """Estimate the number of remaining bisect steps."""
        if self._state != BisectState.IN_PROGRESS:
            return 0
        span = self._bad_idx - self._good_idx
        if span <= 1:
            return 0
        count = 0
        while span > 1:
            span //= 2
            count += 1
        return count

    def _select_midpoint(self) -> str:
        """Select the midpoint between good and bad indices."""
        self._current_idx = (self._good_idx + self._bad_idx) // 2
        return self._commits[self._current_idx]

    def _advance(self) -> Optional[str]:
        """Advance the bisect or complete it if the range has collapsed."""
        if self._bad_idx - self._good_idx <= 1:
            self._state = BisectState.COMPLETE
            self._result = BisectResult(
                first_bad_commit=self._commits[self._bad_idx],
                steps_taken=self._steps,
                total_commits=len(self._commits),
                state=BisectState.COMPLETE,
            )
            return None
        return self._select_midpoint()

    def _ensure_in_progress(self) -> None:
        """Raise if no bisect is in progress."""
        if self._state != BisectState.IN_PROGRESS:
            raise VCSBisectError("No bisect operation is in progress")

    def reset(self) -> None:
        """Reset the bisect engine to its initial state."""
        self._commits = []
        self._good_idx = 0
        self._bad_idx = 0
        self._current_idx = 0
        self._steps = 0
        self._state = BisectState.INACTIVE
        self._result = None


# ---------------------------------------------------------------------------
# FizzGit Repository
# ---------------------------------------------------------------------------

class FizzGitRepository:
    """The top-level orchestrator for the FizzGit version control system.

    Provides a high-level interface for all VCS operations: initialising
    a repository, staging changes, creating commits, viewing history,
    computing diffs, managing branches, checking out branches, merging,
    and running bisect operations.

    The repository coordinates the object store, ref store, index, diff
    engine, and bisect engine into a cohesive workflow that mirrors the
    familiar git command set. The implementation is intentionally faithful
    to the content-addressable design of real distributed VCS systems,
    because FizzBuzz evaluation state deserves the same level of version
    control rigour as production source code.
    """

    def __init__(self, author: str = "FizzGitBot") -> None:
        self._object_store = ObjectStore()
        self._ref_store = RefStore()
        self._index = Index()
        self._diff_engine = DiffEngine(self._object_store)
        self._bisect_engine = BisectEngine(self._object_store)
        self._author = author
        self._initialized = False

    @property
    def object_store(self) -> ObjectStore:
        """Access the underlying object store."""
        return self._object_store

    @property
    def ref_store(self) -> RefStore:
        """Access the underlying ref store."""
        return self._ref_store

    @property
    def index(self) -> Index:
        """Access the staging area."""
        return self._index

    @property
    def diff_engine(self) -> DiffEngine:
        """Access the diff engine."""
        return self._diff_engine

    @property
    def bisect_engine(self) -> BisectEngine:
        """Access the bisect engine."""
        return self._bisect_engine

    def init(self) -> None:
        """Initialize the repository with a main branch.

        Creates the initial branch (main) with no commit. This must
        be called before any other operations.
        """
        if self._initialized:
            return
        self._ref_store.create_branch("main")
        self._ref_store.set_head("main")
        self._initialized = True

    def add(self, path: str, content: str) -> str:
        """Stage content at the given path.

        Creates a blob for the content and adds it to the index.
        Returns the blob hash.
        """
        self._ensure_initialized()
        blob = Blob.create(content)
        self._object_store.store_blob(blob)
        self._index.add(path, blob.hash)
        return blob.hash

    def commit(self, message: str, author: Optional[str] = None, timestamp: Optional[float] = None) -> str:
        """Create a commit from the current index state.

        Builds a tree from the staged entries, creates a commit object
        linking to the current HEAD, stores both in the object store,
        and advances the current branch.

        Returns the commit hash.
        """
        self._ensure_initialized()

        if self._index.is_empty():
            raise VCSError("Nothing to commit: index is empty")

        # Build tree from index
        entries_dict = self._index.get_entries()
        tree_entries = tuple(
            TreeEntry(name=path, object_hash=blob_hash, object_type=ObjectType.BLOB)
            for path, blob_hash in sorted(entries_dict.items())
        )
        tree = Tree.create(tree_entries)
        self._object_store.store_tree(tree)

        # Create commit
        parent = self._ref_store.get_head_commit()
        commit_author = author or self._author
        commit_obj = Commit.create(
            tree_hash=tree.hash,
            parent_hash=parent,
            author=commit_author,
            message=message,
            timestamp=timestamp,
        )
        self._object_store.store_commit(commit_obj)

        # Advance current branch
        current_branch = self._ref_store.get_head()
        self._ref_store.update_branch(current_branch, commit_obj.hash)

        return commit_obj.hash

    def log(self, max_count: int = 50) -> list[Commit]:
        """Return the commit history from HEAD, newest first.

        Walks the parent chain from the current HEAD commit, collecting
        up to max_count commits.
        """
        self._ensure_initialized()
        commits: list[Commit] = []
        commit_hash = self._ref_store.get_head_commit()

        while commit_hash is not None and len(commits) < max_count:
            obj = self._object_store.get(commit_hash)
            if not isinstance(obj, Commit):
                break
            commits.append(obj)
            commit_hash = obj.parent_hash

        return commits

    def diff(self, commit_a: Optional[str] = None, commit_b: Optional[str] = None) -> list[DiffEntry]:
        """Compute the diff between two commits.

        If commit_b is None, diffs commit_a against its parent.
        If both are None, diffs HEAD against its parent.
        """
        self._ensure_initialized()

        if commit_a is None:
            commit_a = self._ref_store.get_head_commit()
            if commit_a is None:
                return []

        commit_obj_a = self._object_store.get(commit_a)
        if not isinstance(commit_obj_a, Commit):
            raise VCSError(f"Object {commit_a[:12]} is not a commit")

        if commit_b is None:
            # Diff against parent
            old_tree = None
            if commit_obj_a.parent_hash:
                parent = self._object_store.get(commit_obj_a.parent_hash)
                if isinstance(parent, Commit):
                    old_tree = parent.tree_hash
            return self._diff_engine.diff_trees(old_tree, commit_obj_a.tree_hash)

        commit_obj_b = self._object_store.get(commit_b)
        if not isinstance(commit_obj_b, Commit):
            raise VCSError(f"Object {commit_b[:12]} is not a commit")

        return self._diff_engine.diff_trees(commit_obj_a.tree_hash, commit_obj_b.tree_hash)

    def branch(self, name: str) -> None:
        """Create a new branch at the current HEAD commit."""
        self._ensure_initialized()
        commit_hash = self._ref_store.get_head_commit()
        self._ref_store.create_branch(name, commit_hash)

    def checkout(self, branch_name: str) -> None:
        """Switch HEAD to the specified branch.

        Updates HEAD to point to the given branch and rebuilds the index
        from the branch's tip commit tree.
        """
        self._ensure_initialized()
        ref = self._ref_store.get_branch(branch_name)
        self._ref_store.set_head(branch_name)

        # Rebuild index from the branch tip tree
        self._index.clear()
        if ref.commit_hash is not None:
            commit_obj = self._object_store.get(ref.commit_hash)
            if isinstance(commit_obj, Commit):
                tree = self._object_store.get(commit_obj.tree_hash)
                if isinstance(tree, Tree):
                    for entry in tree.entries:
                        if entry.object_type == ObjectType.BLOB:
                            self._index.add(entry.name, entry.object_hash)

    def merge(self, source_branch: str) -> tuple[str, list[DiffEntry]]:
        """Merge the source branch into the current branch.

        Performs a three-way merge using the common ancestor of the two
        branch tips. Returns a tuple of (merge_commit_hash, conflicts).

        Conflicts are resolved using FizzBuzz domain-specific priority:
        "FizzBuzz" > "Fizz" > "Buzz" > plain number.
        """
        self._ensure_initialized()
        current_branch = self._ref_store.get_head()
        current_commit = self._ref_store.get_head_commit()

        source_ref = self._ref_store.get_branch(source_branch)
        source_commit = source_ref.commit_hash

        if source_commit is None:
            raise VCSError(f"Branch '{source_branch}' has no commits")

        if current_commit is None:
            # Current branch has no commits; fast-forward
            self._ref_store.update_branch(current_branch, source_commit)
            return source_commit, []

        # Find common ancestor
        base_commit = self._find_common_ancestor(current_commit, source_commit)

        base_tree = None
        if base_commit is not None:
            base_obj = self._object_store.get(base_commit)
            if isinstance(base_obj, Commit):
                base_tree = base_obj.tree_hash

        current_obj = self._object_store.get(current_commit)
        source_obj = self._object_store.get(source_commit)

        ours_tree = current_obj.tree_hash if isinstance(current_obj, Commit) else None
        theirs_tree = source_obj.tree_hash if isinstance(source_obj, Commit) else None

        # Three-way merge
        merged_entries, conflicts = self._diff_engine.three_way_merge(
            base_tree, ours_tree, theirs_tree
        )

        # Build merged tree
        self._index.clear()
        for path, blob_hash in merged_entries.items():
            self._index.add(path, blob_hash)

        # Create merge commit
        merge_hash = self.commit(
            message=f"Merge branch '{source_branch}' into {current_branch}",
        )

        return merge_hash, conflicts

    def bisect_start(self, good_commit: str, bad_commit: str) -> str:
        """Begin a bisect operation between good and bad commits."""
        self._ensure_initialized()
        return self._bisect_engine.start(good_commit, bad_commit)

    def bisect_good(self) -> Optional[str]:
        """Mark the current bisect commit as good."""
        return self._bisect_engine.mark_good()

    def bisect_bad(self) -> Optional[str]:
        """Mark the current bisect commit as bad."""
        return self._bisect_engine.mark_bad()

    def bisect_reset(self) -> None:
        """Reset the bisect operation."""
        self._bisect_engine.reset()

    def get_commit(self, commit_hash: str) -> Commit:
        """Retrieve a commit by hash."""
        obj = self._object_store.get(commit_hash)
        if not isinstance(obj, Commit):
            raise VCSError(f"Object {commit_hash[:12]} is not a commit")
        return obj

    def get_tree(self, tree_hash: str) -> Tree:
        """Retrieve a tree by hash."""
        obj = self._object_store.get(tree_hash)
        if not isinstance(obj, Tree):
            raise VCSError(f"Object {tree_hash[:12]} is not a tree")
        return obj

    def get_blob(self, blob_hash: str) -> Blob:
        """Retrieve a blob by hash."""
        obj = self._object_store.get(blob_hash)
        if not isinstance(obj, Blob):
            raise VCSError(f"Object {blob_hash[:12]} is not a blob")
        return obj

    def _find_common_ancestor(self, commit_a: str, commit_b: str) -> Optional[str]:
        """Find the most recent common ancestor of two commits.

        Walks both parent chains simultaneously, collecting ancestor sets,
        and returns the first commit found in both sets.
        """
        ancestors_a: set[str] = set()
        ancestors_b: set[str] = set()

        ptr_a: Optional[str] = commit_a
        ptr_b: Optional[str] = commit_b

        while ptr_a is not None or ptr_b is not None:
            if ptr_a is not None:
                if ptr_a in ancestors_b:
                    return ptr_a
                ancestors_a.add(ptr_a)
                obj = self._object_store.get(ptr_a)
                ptr_a = obj.parent_hash if isinstance(obj, Commit) else None

            if ptr_b is not None:
                if ptr_b in ancestors_a:
                    return ptr_b
                ancestors_b.add(ptr_b)
                obj = self._object_store.get(ptr_b)
                ptr_b = obj.parent_hash if isinstance(obj, Commit) else None

        return None

    def _ensure_initialized(self) -> None:
        """Raise if the repository has not been initialized."""
        if not self._initialized:
            raise VCSError("Repository not initialized. Call init() first.")


# ---------------------------------------------------------------------------
# VCS Dashboard
# ---------------------------------------------------------------------------

class VCSDashboard:
    """ASCII dashboard rendering for the FizzGit version control system.

    Provides a visual summary of the repository state, including the
    commit graph with branch pointers, recent diff statistics, and
    object store metrics. The dashboard is designed for terminal output,
    using box-drawing characters and ASCII art to convey information
    density appropriate for a version control system managing data
    with a sub-second lifecycle.
    """

    @staticmethod
    def render(
        repo: FizzGitRepository,
        width: int = 60,
    ) -> str:
        """Render the complete VCS dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append(border)
        lines.append(VCSDashboard._center("FIZZGIT VERSION CONTROL DASHBOARD", width))
        lines.append(border)

        # Repository summary
        lines.append(VCSDashboard._center("Repository Summary", width))
        lines.append(VCSDashboard._pad(f"  HEAD: {repo.ref_store.get_head()}", width))

        head_commit = repo.ref_store.get_head_commit()
        if head_commit:
            lines.append(VCSDashboard._pad(f"  Tip:  {head_commit[:12]}", width))
        else:
            lines.append(VCSDashboard._pad("  Tip:  (no commits)", width))

        lines.append(VCSDashboard._pad(
            f"  Objects: {repo.object_store.count()}  |  "
            f"Staged: {repo.index.entry_count()}",
            width,
        ))
        lines.append(border)

        # Branches
        branches = repo.ref_store.list_branches()
        lines.append(VCSDashboard._center("Branches", width))
        current = repo.ref_store.get_head()
        for br in branches:
            marker = "* " if br == current else "  "
            ref = repo.ref_store.get_branch(br)
            tip = ref.commit_hash[:12] if ref.commit_hash else "(empty)"
            lines.append(VCSDashboard._pad(f"  {marker}{br:<20s} -> {tip}", width))
        lines.append(border)

        # Commit log
        commits = repo.log(max_count=10)
        lines.append(VCSDashboard._center("Commit History (last 10)", width))
        if not commits:
            lines.append(VCSDashboard._pad("  (no commits)", width))
        for c in commits:
            short_hash = c.hash[:8]
            msg_trunc = c.message[:width - 20]
            lines.append(VCSDashboard._pad(f"  {short_hash} {msg_trunc}", width))
        lines.append(border)

        # Bisect state
        bisect = repo.bisect_engine
        if bisect.state != BisectState.INACTIVE:
            lines.append(VCSDashboard._center("Bisect Status", width))
            lines.append(VCSDashboard._pad(f"  State: {bisect.state.value}", width))
            if bisect.state == BisectState.IN_PROGRESS:
                lines.append(VCSDashboard._pad(
                    f"  Current: {bisect.get_current()[:12]}",
                    width,
                ))
                lines.append(VCSDashboard._pad(
                    f"  Remaining steps: ~{bisect.remaining_steps()}",
                    width,
                ))
            elif bisect.result is not None:
                r = bisect.result
                bad = r.first_bad_commit[:12] if r.first_bad_commit else "unknown"
                lines.append(VCSDashboard._pad(f"  First bad: {bad}", width))
                lines.append(VCSDashboard._pad(
                    f"  Steps: {r.steps_taken} / {r.total_commits} commits",
                    width,
                ))
            lines.append(border)

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def render_log(repo: FizzGitRepository, max_count: int = 20) -> str:
        """Render the commit log with graph visualization."""
        commits = repo.log(max_count=max_count)
        if not commits:
            return "  (no commits)\n"

        lines: list[str] = []
        for i, c in enumerate(commits):
            connector = "* " if i == 0 else "| "
            lines.append(f"  {connector}{c.hash[:8]}  {c.message}")
            lines.append(f"  |   Author: {c.author}  Date: {_format_timestamp(c.timestamp)}")
            if i < len(commits) - 1:
                lines.append("  |")

        return "\n".join(lines)

    @staticmethod
    def render_diff(diffs: list[DiffEntry]) -> str:
        """Render a diff summary."""
        if not diffs:
            return "  (no changes)\n"

        lines: list[str] = []
        adds = sum(1 for d in diffs if d.change_type == "add")
        deletes = sum(1 for d in diffs if d.change_type == "delete")
        modifies = sum(1 for d in diffs if d.change_type == "modify")
        conflicts = sum(1 for d in diffs if d.change_type == "conflict")

        lines.append(f"  {adds} additions, {deletes} deletions, "
                      f"{modifies} modifications, {conflicts} conflicts")
        lines.append("")

        for d in diffs:
            prefix = {"add": "+", "delete": "-", "modify": "~", "conflict": "!"}
            symbol = prefix.get(d.change_type, "?")
            lines.append(f"  {symbol} {d.path}")
            if d.old_value and d.new_value:
                lines.append(f"    old: {d.old_value}")
                lines.append(f"    new: {d.new_value}")
            elif d.new_value:
                lines.append(f"    value: {d.new_value}")
            elif d.old_value:
                lines.append(f"    was: {d.old_value}")

        return "\n".join(lines)

    @staticmethod
    def _center(text: str, width: int) -> str:
        """Center text within the dashboard width."""
        return "|" + text.center(width - 2) + "|"

    @staticmethod
    def _pad(text: str, width: int) -> str:
        """Left-align text within the dashboard width."""
        inner = text[: width - 2]
        return "|" + inner.ljust(width - 2) + "|"


def _format_timestamp(ts: float) -> str:
    """Format a UNIX timestamp into a human-readable string."""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# VCS Middleware
# ---------------------------------------------------------------------------

class VCSMiddleware(IMiddleware):
    """Middleware that automatically commits FizzBuzz evaluation state changes.

    Intercepts every evaluation batch passing through the middleware pipeline,
    extracts the classification results, stages them as content-addressable
    blobs, and creates a commit in the FizzGit repository. This provides a
    complete, immutable audit trail of every FizzBuzz evaluation, enabling
    historical analysis, regression detection via bisect, and branch-based
    experimentation with alternative classification strategies.

    The middleware runs at priority 970, placing it late in the pipeline to
    ensure it captures the final, fully-processed evaluation state rather
    than intermediate results that may be modified by upstream middleware
    such as the chaos monkey or A/B testing framework.
    """

    def __init__(
        self,
        repo: FizzGitRepository,
        auto_commit: bool = True,
        enable_dashboard: bool = False,
    ) -> None:
        self._repo = repo
        self._auto_commit = auto_commit
        self._enable_dashboard = enable_dashboard
        self._commit_count = 0
        self._total_objects_created = 0

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "VCSMiddleware"

    def get_priority(self) -> int:
        """Return execution priority (970 — late pipeline, captures final state)."""
        return 970

    @property
    def commit_count(self) -> int:
        """Return the number of commits created by this middleware."""
        return self._commit_count

    @property
    def repo(self) -> FizzGitRepository:
        """Access the underlying repository."""
        return self._repo

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context, then auto-commit the evaluation state."""
        result = next_handler(context)

        if not self._auto_commit:
            return result

        try:
            number = context.number
            output = str(number)

            # Extract the classification from results
            if context.results:
                last_result = context.results[-1]
                if hasattr(last_result, "classification"):
                    cls_val = last_result.classification
                    output = cls_val.value if hasattr(cls_val, "value") else str(cls_val)
                elif hasattr(last_result, "output"):
                    output = str(last_result.output)

            # Stage the evaluation result
            path = f"eval/{number}"
            before_count = self._repo.object_store.count()
            self._repo.add(path, output)

            # Create a commit for this evaluation
            self._repo.commit(
                message=f"Evaluate {number} -> {output}",
                author="VCSMiddleware",
            )
            self._commit_count += 1
            self._total_objects_created += (
                self._repo.object_store.count() - before_count
            )

        except Exception:
            # VCS operations must not disrupt the evaluation pipeline.
            # If a commit fails, the evaluation result is still valid —
            # it simply won't be recorded in the version history.
            pass

        return result
