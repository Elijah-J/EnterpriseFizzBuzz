"""
Tests for the FizzGit Content-Addressable Version Control System.

Validates the complete VCS lifecycle: content-addressable object storage,
commit DAG construction, branch management, diff computation, three-way
merge with domain-specific conflict resolution, bisect binary search,
staging area operations, dashboard rendering, and middleware auto-commit.
"""

from __future__ import annotations

import time
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    VCSBisectError,
    VCSBranchError,
    VCSError,
    VCSMergeConflictError,
    VCSObjectNotFoundError,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizz_vcs import (
    BisectEngine,
    BisectResult,
    BisectState,
    Blob,
    Commit,
    DiffEngine,
    DiffEntry,
    FizzGitRepository,
    Index,
    ObjectStore,
    ObjectType,
    Ref,
    RefStore,
    Tree,
    TreeEntry,
    VCSDashboard,
    VCSMiddleware,
    _classification_priority,
    _format_timestamp,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# =====================================================================
# Blob Tests
# =====================================================================

class TestBlob:
    """Tests for the content-addressable Blob object."""

    def test_create_blob(self):
        """A blob stores content and computes a deterministic SHA-256 hash."""
        blob = Blob.create("FizzBuzz")
        assert blob.content == "FizzBuzz"
        assert len(blob.hash) == 64  # SHA-256 hex digest

    def test_identical_content_same_hash(self):
        """Two blobs with identical content produce the same hash."""
        blob_a = Blob.create("Fizz")
        blob_b = Blob.create("Fizz")
        assert blob_a.hash == blob_b.hash

    def test_different_content_different_hash(self):
        """Two blobs with different content produce different hashes."""
        blob_a = Blob.create("Fizz")
        blob_b = Blob.create("Buzz")
        assert blob_a.hash != blob_b.hash

    def test_empty_content(self):
        """An empty blob is still a valid content-addressable object."""
        blob = Blob.create("")
        assert blob.content == ""
        assert len(blob.hash) == 64

    def test_hash_includes_type_prefix(self):
        """The hash is computed over 'blob:' + content, not raw content."""
        import hashlib
        content = "15"
        expected = hashlib.sha256(f"blob:{content}".encode("utf-8")).hexdigest()
        blob = Blob.create(content)
        assert blob.hash == expected

    def test_blob_is_frozen(self):
        """Blobs are immutable dataclasses."""
        blob = Blob.create("test")
        with pytest.raises(AttributeError):
            blob.content = "modified"


# =====================================================================
# Tree Tests
# =====================================================================

class TestTree:
    """Tests for the Tree directory object."""

    def test_create_tree(self):
        """A tree is created from entries and computes a deterministic hash."""
        entry = TreeEntry(name="result", object_hash="abc123", object_type=ObjectType.BLOB)
        tree = Tree.create((entry,))
        assert len(tree.hash) == 64
        assert len(tree.entries) == 1

    def test_tree_hash_deterministic(self):
        """Trees with the same entries produce the same hash regardless of order."""
        e1 = TreeEntry(name="a", object_hash="hash_a", object_type=ObjectType.BLOB)
        e2 = TreeEntry(name="b", object_hash="hash_b", object_type=ObjectType.BLOB)
        tree_ab = Tree.create((e1, e2))
        tree_ba = Tree.create((e2, e1))
        assert tree_ab.hash == tree_ba.hash

    def test_different_entries_different_hash(self):
        """Trees with different entries produce different hashes."""
        e1 = TreeEntry(name="a", object_hash="hash_a", object_type=ObjectType.BLOB)
        e2 = TreeEntry(name="a", object_hash="hash_b", object_type=ObjectType.BLOB)
        tree_a = Tree.create((e1,))
        tree_b = Tree.create((e2,))
        assert tree_a.hash != tree_b.hash

    def test_get_entry_found(self):
        """get_entry returns the matching entry when present."""
        entry = TreeEntry(name="fizz", object_hash="abc", object_type=ObjectType.BLOB)
        tree = Tree.create((entry,))
        assert tree.get_entry("fizz") is entry

    def test_get_entry_not_found(self):
        """get_entry returns None when the name is not present."""
        tree = Tree.create(())
        assert tree.get_entry("missing") is None

    def test_empty_tree(self):
        """An empty tree is a valid object with a deterministic hash."""
        tree = Tree.create(())
        assert tree.hash is not None
        assert len(tree.entries) == 0


# =====================================================================
# Commit Tests
# =====================================================================

class TestCommit:
    """Tests for the Commit object."""

    def test_create_commit(self):
        """A commit links a tree to its parent with metadata."""
        c = Commit.create(
            tree_hash="tree_abc",
            parent_hash=None,
            author="TestBot",
            message="Initial commit",
            timestamp=1000000.0,
        )
        assert c.tree_hash == "tree_abc"
        assert c.parent_hash is None
        assert c.author == "TestBot"
        assert c.message == "Initial commit"
        assert len(c.hash) == 64

    def test_commit_hash_includes_parent(self):
        """Commits with different parents produce different hashes."""
        c1 = Commit.create("tree", None, "a", "msg", 1.0)
        c2 = Commit.create("tree", "parent_abc", "a", "msg", 1.0)
        assert c1.hash != c2.hash

    def test_commit_hash_includes_message(self):
        """Commits with different messages produce different hashes."""
        c1 = Commit.create("tree", None, "a", "msg1", 1.0)
        c2 = Commit.create("tree", None, "a", "msg2", 1.0)
        assert c1.hash != c2.hash

    def test_commit_hash_includes_timestamp(self):
        """Commits with different timestamps produce different hashes."""
        c1 = Commit.create("tree", None, "a", "msg", 1.0)
        c2 = Commit.create("tree", None, "a", "msg", 2.0)
        assert c1.hash != c2.hash

    def test_commit_is_frozen(self):
        """Commits are immutable dataclasses."""
        c = Commit.create("tree", None, "a", "msg", 1.0)
        with pytest.raises(AttributeError):
            c.message = "modified"

    def test_commit_auto_timestamp(self):
        """Commits without explicit timestamp use current time."""
        before = time.time()
        c = Commit.create("tree", None, "a", "msg")
        after = time.time()
        assert before <= c.timestamp <= after


# =====================================================================
# ObjectStore Tests
# =====================================================================

class TestObjectStore:
    """Tests for the content-addressable object store."""

    def test_store_and_retrieve_blob(self):
        """Blobs can be stored and retrieved by hash."""
        store = ObjectStore()
        blob = Blob.create("Fizz")
        store.store_blob(blob)
        retrieved = store.get(blob.hash)
        assert retrieved.content == "Fizz"

    def test_store_and_retrieve_tree(self):
        """Trees can be stored and retrieved by hash."""
        store = ObjectStore()
        entry = TreeEntry(name="x", object_hash="h", object_type=ObjectType.BLOB)
        tree = Tree.create((entry,))
        store.store_tree(tree)
        retrieved = store.get(tree.hash)
        assert len(retrieved.entries) == 1

    def test_store_and_retrieve_commit(self):
        """Commits can be stored and retrieved by hash."""
        store = ObjectStore()
        commit = Commit.create("tree_hash", None, "bot", "msg", 1.0)
        store.store_commit(commit)
        retrieved = store.get(commit.hash)
        assert retrieved.message == "msg"

    def test_get_nonexistent_raises(self):
        """Retrieving a non-existent hash raises VCSObjectNotFoundError."""
        store = ObjectStore()
        with pytest.raises(VCSObjectNotFoundError):
            store.get("nonexistent_hash")

    def test_contains(self):
        """contains() returns True for stored objects, False otherwise."""
        store = ObjectStore()
        blob = Blob.create("test")
        assert not store.contains(blob.hash)
        store.store_blob(blob)
        assert store.contains(blob.hash)

    def test_count(self):
        """count() returns the number of stored objects."""
        store = ObjectStore()
        assert store.count() == 0
        store.store_blob(Blob.create("a"))
        assert store.count() == 1
        store.store_blob(Blob.create("b"))
        assert store.count() == 2

    def test_all_objects(self):
        """all_objects() returns a dict of all stored objects."""
        store = ObjectStore()
        blob = Blob.create("x")
        store.store_blob(blob)
        objs = store.all_objects()
        assert blob.hash in objs


# =====================================================================
# RefStore Tests
# =====================================================================

class TestRefStore:
    """Tests for branch and HEAD management."""

    def test_create_branch(self):
        """Branches can be created with an optional initial commit."""
        refs = RefStore()
        ref = refs.create_branch("main")
        assert ref.name == "main"
        assert ref.commit_hash is None

    def test_create_branch_with_commit(self):
        """Branches can be created pointing to a specific commit."""
        refs = RefStore()
        ref = refs.create_branch("feature", "commit_abc")
        assert ref.commit_hash == "commit_abc"

    def test_duplicate_branch_raises(self):
        """Creating a branch that already exists raises VCSBranchError."""
        refs = RefStore()
        refs.create_branch("main")
        with pytest.raises(VCSBranchError):
            refs.create_branch("main")

    def test_get_branch(self):
        """Branches can be retrieved by name."""
        refs = RefStore()
        refs.create_branch("dev")
        ref = refs.get_branch("dev")
        assert ref.name == "dev"

    def test_get_nonexistent_branch_raises(self):
        """Getting a non-existent branch raises VCSBranchError."""
        refs = RefStore()
        with pytest.raises(VCSBranchError):
            refs.get_branch("ghost")

    def test_update_branch(self):
        """Branches can be advanced to point to a new commit."""
        refs = RefStore()
        refs.create_branch("main")
        refs.update_branch("main", "commit_1")
        assert refs.get_branch("main").commit_hash == "commit_1"

    def test_delete_branch(self):
        """Branches can be deleted unless they are the current HEAD."""
        refs = RefStore()
        refs.create_branch("main")
        refs.create_branch("feature")
        refs.set_head("main")
        refs.delete_branch("feature")
        assert not refs.branch_exists("feature")

    def test_delete_current_branch_raises(self):
        """Deleting the current branch raises VCSBranchError."""
        refs = RefStore()
        refs.create_branch("main")
        refs.set_head("main")
        with pytest.raises(VCSBranchError):
            refs.delete_branch("main")

    def test_delete_nonexistent_branch_raises(self):
        """Deleting a non-existent branch raises VCSBranchError."""
        refs = RefStore()
        with pytest.raises(VCSBranchError):
            refs.delete_branch("ghost")

    def test_set_head(self):
        """HEAD can be pointed to an existing branch."""
        refs = RefStore()
        refs.create_branch("main")
        refs.create_branch("dev")
        refs.set_head("dev")
        assert refs.get_head() == "dev"

    def test_set_head_nonexistent_raises(self):
        """Setting HEAD to a non-existent branch raises VCSBranchError."""
        refs = RefStore()
        with pytest.raises(VCSBranchError):
            refs.set_head("ghost")

    def test_get_head_commit(self):
        """get_head_commit resolves HEAD to the tip commit hash."""
        refs = RefStore()
        refs.create_branch("main", "commit_1")
        refs.set_head("main")
        assert refs.get_head_commit() == "commit_1"

    def test_get_head_commit_empty(self):
        """get_head_commit returns None when HEAD branch has no commits."""
        refs = RefStore()
        refs.create_branch("main")
        refs.set_head("main")
        assert refs.get_head_commit() is None

    def test_list_branches(self):
        """list_branches returns sorted branch names."""
        refs = RefStore()
        refs.create_branch("zebra")
        refs.create_branch("alpha")
        assert refs.list_branches() == ["alpha", "zebra"]

    def test_branch_exists(self):
        """branch_exists returns True for existing branches."""
        refs = RefStore()
        refs.create_branch("main")
        assert refs.branch_exists("main")
        assert not refs.branch_exists("dev")


# =====================================================================
# Index Tests
# =====================================================================

class TestIndex:
    """Tests for the staging area."""

    def test_add_entry(self):
        """Entries can be staged by path."""
        idx = Index()
        idx.add("eval/3", "hash_fizz")
        assert idx.get_entries() == {"eval/3": "hash_fizz"}

    def test_remove_entry(self):
        """Entries can be unstaged."""
        idx = Index()
        idx.add("eval/3", "hash_fizz")
        idx.remove("eval/3")
        assert idx.is_empty()

    def test_remove_nonexistent_is_noop(self):
        """Removing a non-existent path does not raise."""
        idx = Index()
        idx.remove("ghost")  # Should not raise

    def test_clear(self):
        """clear() removes all staged entries."""
        idx = Index()
        idx.add("a", "h1")
        idx.add("b", "h2")
        idx.clear()
        assert idx.is_empty()

    def test_entry_count(self):
        """entry_count returns the number of staged entries."""
        idx = Index()
        assert idx.entry_count() == 0
        idx.add("a", "h1")
        assert idx.entry_count() == 1

    def test_overwrite_entry(self):
        """Staging the same path again overwrites the previous entry."""
        idx = Index()
        idx.add("eval/3", "old_hash")
        idx.add("eval/3", "new_hash")
        assert idx.get_entries()["eval/3"] == "new_hash"
        assert idx.entry_count() == 1


# =====================================================================
# DiffEngine Tests
# =====================================================================

class TestDiffEngine:
    """Tests for tree diff computation."""

    def _make_tree(self, store: ObjectStore, entries: dict[str, str]) -> str:
        """Helper: create blobs and a tree, return tree hash."""
        tree_entries = []
        for name, content in sorted(entries.items()):
            blob = Blob.create(content)
            store.store_blob(blob)
            tree_entries.append(TreeEntry(
                name=name,
                object_hash=blob.hash,
                object_type=ObjectType.BLOB,
            ))
        tree = Tree.create(tuple(tree_entries))
        store.store_tree(tree)
        return tree.hash

    def test_diff_addition(self):
        """Detects additions when new paths appear."""
        store = ObjectStore()
        old = self._make_tree(store, {"a": "1"})
        new = self._make_tree(store, {"a": "1", "b": "2"})
        engine = DiffEngine(store)
        diffs = engine.diff_trees(old, new)
        assert any(d.change_type == "add" and d.path == "b" for d in diffs)

    def test_diff_deletion(self):
        """Detects deletions when paths disappear."""
        store = ObjectStore()
        old = self._make_tree(store, {"a": "1", "b": "2"})
        new = self._make_tree(store, {"a": "1"})
        engine = DiffEngine(store)
        diffs = engine.diff_trees(old, new)
        assert any(d.change_type == "delete" and d.path == "b" for d in diffs)

    def test_diff_modification(self):
        """Detects modifications when blob hashes change."""
        store = ObjectStore()
        old = self._make_tree(store, {"a": "Fizz"})
        new = self._make_tree(store, {"a": "Buzz"})
        engine = DiffEngine(store)
        diffs = engine.diff_trees(old, new)
        assert any(d.change_type == "modify" and d.path == "a" for d in diffs)

    def test_diff_no_changes(self):
        """Returns empty diff when trees are identical."""
        store = ObjectStore()
        tree_hash = self._make_tree(store, {"a": "1"})
        engine = DiffEngine(store)
        diffs = engine.diff_trees(tree_hash, tree_hash)
        assert len(diffs) == 0

    def test_diff_from_empty(self):
        """All entries are additions when diffing from None."""
        store = ObjectStore()
        new = self._make_tree(store, {"x": "1", "y": "2"})
        engine = DiffEngine(store)
        diffs = engine.diff_trees(None, new)
        assert all(d.change_type == "add" for d in diffs)
        assert len(diffs) == 2


# =====================================================================
# Three-Way Merge Tests
# =====================================================================

class TestThreeWayMerge:
    """Tests for three-way merge with domain-specific conflict resolution."""

    def _make_tree(self, store: ObjectStore, entries: dict[str, str]) -> str:
        """Helper: create blobs and a tree, return tree hash."""
        tree_entries = []
        for name, content in sorted(entries.items()):
            blob = Blob.create(content)
            store.store_blob(blob)
            tree_entries.append(TreeEntry(
                name=name,
                object_hash=blob.hash,
                object_type=ObjectType.BLOB,
            ))
        tree = Tree.create(tuple(tree_entries))
        store.store_tree(tree)
        return tree.hash

    def test_no_conflicts_ours_only(self):
        """When only one side changes, those changes are accepted."""
        store = ObjectStore()
        base = self._make_tree(store, {"a": "1"})
        ours = self._make_tree(store, {"a": "1", "b": "Fizz"})
        theirs = self._make_tree(store, {"a": "1"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(base, ours, theirs)
        assert "b" in merged
        assert len(conflicts) == 0

    def test_no_conflicts_theirs_only(self):
        """When only theirs changes, those changes are accepted."""
        store = ObjectStore()
        base = self._make_tree(store, {"a": "1"})
        ours = self._make_tree(store, {"a": "1"})
        theirs = self._make_tree(store, {"a": "1", "c": "Buzz"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(base, ours, theirs)
        assert "c" in merged
        assert len(conflicts) == 0

    def test_conflict_fizzbuzz_beats_fizz(self):
        """FizzBuzz wins over Fizz in conflict resolution."""
        store = ObjectStore()
        base = self._make_tree(store, {"x": "1"})
        ours = self._make_tree(store, {"x": "Fizz"})
        theirs = self._make_tree(store, {"x": "FizzBuzz"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(base, ours, theirs)
        assert len(conflicts) == 1
        # The merged value should be the FizzBuzz blob hash
        theirs_blob_hash = Blob.create("FizzBuzz").hash
        assert merged["x"] == theirs_blob_hash

    def test_conflict_fizz_beats_buzz(self):
        """Fizz wins over Buzz in conflict resolution."""
        store = ObjectStore()
        base = self._make_tree(store, {"x": "1"})
        ours = self._make_tree(store, {"x": "Fizz"})
        theirs = self._make_tree(store, {"x": "Buzz"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(base, ours, theirs)
        assert len(conflicts) == 1
        ours_blob_hash = Blob.create("Fizz").hash
        assert merged["x"] == ours_blob_hash

    def test_conflict_buzz_beats_number(self):
        """Buzz wins over a plain number in conflict resolution."""
        store = ObjectStore()
        base = self._make_tree(store, {"x": "1"})
        ours = self._make_tree(store, {"x": "7"})
        theirs = self._make_tree(store, {"x": "Buzz"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(base, ours, theirs)
        assert len(conflicts) == 1
        theirs_blob_hash = Blob.create("Buzz").hash
        assert merged["x"] == theirs_blob_hash

    def test_both_sides_agree(self):
        """When both sides make the same change, no conflict occurs."""
        store = ObjectStore()
        base = self._make_tree(store, {"x": "1"})
        both = self._make_tree(store, {"x": "Fizz"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(base, both, both)
        assert len(conflicts) == 0
        assert "x" in merged

    def test_merge_from_empty_base(self):
        """Merge with empty base treats all entries as additions."""
        store = ObjectStore()
        ours = self._make_tree(store, {"a": "Fizz"})
        theirs = self._make_tree(store, {"b": "Buzz"})
        engine = DiffEngine(store)
        merged, conflicts = engine.three_way_merge(None, ours, theirs)
        assert "a" in merged
        assert "b" in merged
        assert len(conflicts) == 0


# =====================================================================
# Classification Priority Tests
# =====================================================================

class TestClassificationPriority:
    """Tests for domain-specific conflict resolution priority."""

    def test_fizzbuzz_highest(self):
        """FizzBuzz has the highest priority."""
        assert _classification_priority("FizzBuzz") == 4

    def test_fizz_second(self):
        """Fizz has the second-highest priority."""
        assert _classification_priority("Fizz") == 3

    def test_buzz_third(self):
        """Buzz has the third-highest priority."""
        assert _classification_priority("Buzz") == 2

    def test_number_lowest(self):
        """Plain numbers have the lowest priority."""
        assert _classification_priority("42") == 1
        assert _classification_priority("7") == 1

    def test_priority_ordering(self):
        """The full priority ordering is correct."""
        assert (_classification_priority("FizzBuzz")
                > _classification_priority("Fizz")
                > _classification_priority("Buzz")
                > _classification_priority("99"))


# =====================================================================
# BisectEngine Tests
# =====================================================================

class TestBisectEngine:
    """Tests for the binary search regression finder."""

    def _build_linear_history(self, store: ObjectStore, count: int) -> list[str]:
        """Build a linear chain of commits, return hashes oldest-first."""
        hashes = []
        parent = None
        for i in range(count):
            tree = Tree.create(())
            store.store_tree(tree)
            c = Commit.create(tree.hash, parent, "bot", f"commit {i}", float(i))
            store.store_commit(c)
            hashes.append(c.hash)
            parent = c.hash
        return hashes

    def test_bisect_finds_midpoint(self):
        """Bisect starts at the midpoint of the commit range."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 8)
        engine = BisectEngine(store)
        mid = engine.start(hashes[0], hashes[-1])
        assert mid in hashes
        assert engine.state == BisectState.IN_PROGRESS

    def test_bisect_converges(self):
        """Bisect converges to a single commit."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 8)
        engine = BisectEngine(store)
        engine.start(hashes[0], hashes[-1])

        # Mark all midpoints as good until convergence
        steps = 0
        while engine.state == BisectState.IN_PROGRESS:
            result = engine.mark_bad()
            steps += 1
            if result is None:
                break

        assert engine.state == BisectState.COMPLETE
        assert engine.result is not None
        assert engine.result.first_bad_commit in hashes

    def test_bisect_alternating(self):
        """Bisect works with alternating good/bad marks."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 16)
        engine = BisectEngine(store)
        engine.start(hashes[0], hashes[-1])

        toggle = True
        while engine.state == BisectState.IN_PROGRESS:
            if toggle:
                result = engine.mark_good()
            else:
                result = engine.mark_bad()
            toggle = not toggle
            if result is None:
                break

        assert engine.state == BisectState.COMPLETE

    def test_bisect_not_started_raises(self):
        """Operations on an inactive bisect raise VCSBisectError."""
        store = ObjectStore()
        engine = BisectEngine(store)
        with pytest.raises(VCSBisectError):
            engine.mark_good()

    def test_bisect_already_in_progress_raises(self):
        """Starting a bisect when one is already running raises VCSBisectError."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 4)
        engine = BisectEngine(store)
        engine.start(hashes[0], hashes[-1])
        with pytest.raises(VCSBisectError):
            engine.start(hashes[0], hashes[-1])

    def test_bisect_good_not_ancestor_raises(self):
        """Starting bisect with a good commit not in bad's ancestry raises."""
        store = ObjectStore()
        tree = Tree.create(())
        store.store_tree(tree)
        c1 = Commit.create(tree.hash, None, "a", "msg", 1.0)
        c2 = Commit.create(tree.hash, None, "a", "msg2", 2.0)
        store.store_commit(c1)
        store.store_commit(c2)
        engine = BisectEngine(store)
        with pytest.raises(VCSBisectError):
            engine.start(c1.hash, c2.hash)

    def test_bisect_reset(self):
        """Resetting bisect returns to inactive state."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 4)
        engine = BisectEngine(store)
        engine.start(hashes[0], hashes[-1])
        engine.reset()
        assert engine.state == BisectState.INACTIVE

    def test_bisect_remaining_steps(self):
        """remaining_steps estimates correctly."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 8)
        engine = BisectEngine(store)
        engine.start(hashes[0], hashes[-1])
        # With 8 commits, should need ~3 steps
        assert engine.remaining_steps() >= 1

    def test_bisect_result_attributes(self):
        """BisectResult has expected attributes."""
        r = BisectResult()
        assert r.first_bad_commit is None
        assert r.steps_taken == 0
        assert r.total_commits == 0
        assert r.state == BisectState.INACTIVE

    def test_bisect_minimum_commits(self):
        """Bisect works with the minimum 2 commits (good + bad)."""
        store = ObjectStore()
        hashes = self._build_linear_history(store, 2)
        engine = BisectEngine(store)
        mid = engine.start(hashes[0], hashes[-1])
        # With only 2 commits (good=0, bad=1), midpoint is 0
        result = engine.mark_bad()
        assert result is None
        assert engine.state == BisectState.COMPLETE


# =====================================================================
# FizzGitRepository Tests
# =====================================================================

class TestFizzGitRepository:
    """Tests for the top-level VCS orchestrator."""

    def test_init(self):
        """init() creates the main branch."""
        repo = FizzGitRepository()
        repo.init()
        assert repo.ref_store.get_head() == "main"
        assert repo.ref_store.branch_exists("main")

    def test_init_idempotent(self):
        """Calling init() twice does not raise."""
        repo = FizzGitRepository()
        repo.init()
        repo.init()  # Should not raise

    def test_add_and_commit(self):
        """Content can be staged and committed."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("eval/3", "Fizz")
        commit_hash = repo.commit("Evaluate 3")
        assert len(commit_hash) == 64

    def test_log_returns_commits(self):
        """log() returns the commit history."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("eval/1", "1")
        h1 = repo.commit("First")
        repo.add("eval/2", "2")
        h2 = repo.commit("Second")
        log = repo.log()
        assert len(log) == 2
        assert log[0].hash == h2  # newest first
        assert log[1].hash == h1

    def test_commit_empty_index_raises(self):
        """Committing with an empty index raises VCSError."""
        repo = FizzGitRepository()
        repo.init()
        with pytest.raises(VCSError):
            repo.commit("empty")

    def test_diff_head_vs_parent(self):
        """diff() computes changes between HEAD and its parent."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("eval/1", "1")
        repo.commit("First")
        repo.add("eval/1", "1")
        repo.add("eval/2", "2")
        repo.commit("Second")
        diffs = repo.diff()
        assert any(d.path == "eval/2" for d in diffs)

    def test_branch_and_checkout(self):
        """Branches can be created and checked out."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("eval/1", "1")
        repo.commit("Initial")
        repo.branch("feature")
        repo.checkout("feature")
        assert repo.ref_store.get_head() == "feature"

    def test_merge_simple(self):
        """Simple merge combines changes from two branches."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("eval/1", "1")
        repo.commit("Initial")

        repo.branch("feature")
        repo.checkout("feature")
        repo.add("eval/1", "1")
        repo.add("eval/2", "Fizz")
        repo.commit("Add Fizz")

        repo.checkout("main")
        repo.add("eval/1", "1")
        repo.add("eval/3", "Buzz")
        repo.commit("Add Buzz")

        merge_hash, conflicts = repo.merge("feature")
        assert len(merge_hash) == 64

    def test_not_initialized_raises(self):
        """Operations on an uninitialized repo raise VCSError."""
        repo = FizzGitRepository()
        with pytest.raises(VCSError):
            repo.add("x", "y")

    def test_get_commit(self):
        """get_commit retrieves a commit by hash."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        h = repo.commit("msg")
        c = repo.get_commit(h)
        assert c.message == "msg"

    def test_get_tree(self):
        """get_tree retrieves a tree by hash."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        h = repo.commit("msg")
        c = repo.get_commit(h)
        t = repo.get_tree(c.tree_hash)
        assert len(t.entries) >= 1

    def test_get_blob(self):
        """get_blob retrieves a blob by hash."""
        repo = FizzGitRepository()
        repo.init()
        blob_hash = repo.add("a", "Fizz")
        b = repo.get_blob(blob_hash)
        assert b.content == "Fizz"

    def test_custom_author(self):
        """Repository respects custom author."""
        repo = FizzGitRepository(author="CustomBot")
        repo.init()
        repo.add("a", "1")
        h = repo.commit("test")
        c = repo.get_commit(h)
        assert c.author == "CustomBot"

    def test_commit_with_explicit_author(self):
        """Commits can override the default author."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        h = repo.commit("test", author="OtherBot")
        c = repo.get_commit(h)
        assert c.author == "OtherBot"

    def test_multiple_branches(self):
        """Multiple branches can coexist."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        repo.commit("Initial")
        repo.branch("dev")
        repo.branch("staging")
        branches = repo.ref_store.list_branches()
        assert "main" in branches
        assert "dev" in branches
        assert "staging" in branches

    def test_bisect_via_repo(self):
        """Bisect operations work through the repository interface."""
        repo = FizzGitRepository()
        repo.init()
        commits = []
        for i in range(5):
            repo.add(f"eval/{i}", str(i))
            h = repo.commit(f"Commit {i}", timestamp=float(i))
            commits.append(h)

        mid = repo.bisect_start(commits[0], commits[-1])
        assert mid in commits
        repo.bisect_reset()

    def test_log_max_count(self):
        """log() respects the max_count parameter."""
        repo = FizzGitRepository()
        repo.init()
        for i in range(10):
            repo.add(f"eval/{i}", str(i))
            repo.commit(f"Commit {i}")
        log = repo.log(max_count=3)
        assert len(log) == 3

    def test_checkout_rebuilds_index(self):
        """Checking out a branch rebuilds the index from the tip tree."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("eval/1", "1")
        repo.commit("On main")

        repo.branch("feature")
        repo.checkout("feature")
        # Index should have the entries from main's tip
        entries = repo.index.get_entries()
        assert "eval/1" in entries

    def test_merge_fast_forward(self):
        """Merge fast-forwards when the current branch has no commits."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        c1 = repo.commit("First")

        repo.ref_store.create_branch("empty")
        repo.ref_store.set_head("empty")

        merge_hash, conflicts = repo.merge("main")
        assert merge_hash == c1
        assert len(conflicts) == 0

    def test_find_common_ancestor(self):
        """Common ancestor is found for divergent branches."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("base", "x")
        base_hash = repo.commit("Base")

        repo.branch("feature")

        # Commit on main
        repo.add("base", "x")
        repo.add("main_file", "m")
        repo.commit("Main work")

        # Commit on feature
        repo.checkout("feature")
        repo.add("base", "x")
        repo.add("feat_file", "f")
        repo.commit("Feature work")

        # Find ancestor
        main_tip = repo.ref_store.get_branch("main").commit_hash
        feat_tip = repo.ref_store.get_branch("feature").commit_hash
        ancestor = repo._find_common_ancestor(main_tip, feat_tip)
        assert ancestor == base_hash


# =====================================================================
# VCSDashboard Tests
# =====================================================================

class TestVCSDashboard:
    """Tests for the ASCII dashboard renderer."""

    def test_render_empty_repo(self):
        """Dashboard renders for an empty repository."""
        repo = FizzGitRepository()
        repo.init()
        output = VCSDashboard.render(repo)
        assert "FIZZGIT" in output
        assert "main" in output

    def test_render_with_commits(self):
        """Dashboard renders commit history."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        repo.commit("First commit")
        output = VCSDashboard.render(repo)
        assert "First commit" in output

    def test_render_log(self):
        """render_log shows commit messages."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        repo.commit("Test message")
        output = VCSDashboard.render_log(repo)
        assert "Test message" in output

    def test_render_log_empty(self):
        """render_log handles empty history gracefully."""
        repo = FizzGitRepository()
        repo.init()
        output = VCSDashboard.render_log(repo)
        assert "no commits" in output

    def test_render_diff(self):
        """render_diff shows change summary."""
        diffs = [
            DiffEntry("eval/1", "add", new_value="1"),
            DiffEntry("eval/3", "modify", old_value="3", new_value="Fizz"),
            DiffEntry("eval/5", "delete", old_value="Buzz"),
        ]
        output = VCSDashboard.render_diff(diffs)
        assert "addition" in output
        assert "deletion" in output
        assert "modification" in output

    def test_render_diff_empty(self):
        """render_diff handles no changes."""
        output = VCSDashboard.render_diff([])
        assert "no changes" in output

    def test_render_with_branches(self):
        """Dashboard shows all branches."""
        repo = FizzGitRepository()
        repo.init()
        repo.add("a", "1")
        repo.commit("Init")
        repo.branch("feature")
        output = VCSDashboard.render(repo)
        assert "feature" in output
        assert "main" in output

    def test_render_custom_width(self):
        """Dashboard respects custom width."""
        repo = FizzGitRepository()
        repo.init()
        output = VCSDashboard.render(repo, width=80)
        for line in output.strip().split("\n"):
            if line.startswith("|"):
                assert len(line) == 80 or line.strip() == ""

    def test_render_bisect_in_progress(self):
        """Dashboard shows bisect status when active."""
        repo = FizzGitRepository()
        repo.init()
        commits = []
        for i in range(4):
            repo.add(f"e/{i}", str(i))
            commits.append(repo.commit(f"C{i}", timestamp=float(i)))
        repo.bisect_start(commits[0], commits[-1])
        output = VCSDashboard.render(repo)
        assert "Bisect" in output


# =====================================================================
# VCSMiddleware Tests
# =====================================================================

class TestVCSMiddleware:
    """Tests for the auto-commit middleware."""

    def _make_context(self, number: int = 1) -> ProcessingContext:
        """Create a minimal ProcessingContext."""
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-session")

    def test_get_name(self):
        """Middleware identifies itself correctly."""
        repo = FizzGitRepository()
        repo.init()
        mw = VCSMiddleware(repo)
        assert mw.get_name() == "VCSMiddleware"

    def test_get_priority(self):
        """Middleware runs at priority 970."""
        repo = FizzGitRepository()
        repo.init()
        mw = VCSMiddleware(repo)
        assert mw.get_priority() == 970

    def test_auto_commit_creates_commit(self):
        """Middleware auto-commits evaluation results."""
        repo = FizzGitRepository()
        repo.init()
        mw = VCSMiddleware(repo)

        ctx = self._make_context(3)

        def next_handler(c):
            return c

        mw.process(ctx, next_handler)

        assert mw.commit_count == 1
        log = repo.log()
        assert len(log) >= 1

    def test_auto_commit_disabled(self):
        """Middleware skips commit when auto_commit is False."""
        repo = FizzGitRepository()
        repo.init()
        mw = VCSMiddleware(repo, auto_commit=False)

        ctx = self._make_context(3)
        mw.process(ctx, lambda c: c)

        assert mw.commit_count == 0

    def test_middleware_does_not_break_pipeline(self):
        """VCS failures do not disrupt the evaluation pipeline."""
        repo = FizzGitRepository()
        # Intentionally NOT calling init() to cause internal errors
        mw = VCSMiddleware(repo)

        ctx = self._make_context(5)
        result = mw.process(ctx, lambda c: c)

        # Should still return the context despite VCS errors
        assert result is ctx

    def test_multiple_evaluations(self):
        """Middleware creates one commit per evaluation."""
        repo = FizzGitRepository()
        repo.init()
        mw = VCSMiddleware(repo)

        for i in range(5):
            ctx = self._make_context(i)
            mw.process(ctx, lambda c: c)

        assert mw.commit_count == 5
        log = repo.log()
        assert len(log) == 5

    def test_repo_property(self):
        """Middleware exposes its repository."""
        repo = FizzGitRepository()
        repo.init()
        mw = VCSMiddleware(repo)
        assert mw.repo is repo


# =====================================================================
# Utility Tests
# =====================================================================

class TestFormatTimestamp:
    """Tests for the timestamp formatter."""

    def test_format_epoch(self):
        """Epoch time formats correctly."""
        result = _format_timestamp(0.0)
        assert "1970" in result
        assert "UTC" in result

    def test_format_known_time(self):
        """A known timestamp formats to the expected string."""
        # 2025-01-01 00:00:00 UTC
        result = _format_timestamp(1735689600.0)
        assert "2025" in result


class TestDiffEntry:
    """Tests for the DiffEntry representation."""

    def test_repr(self):
        """DiffEntry has a readable repr."""
        d = DiffEntry("eval/3", "add")
        assert "add" in repr(d)
        assert "eval/3" in repr(d)

    def test_attributes(self):
        """DiffEntry stores all attributes."""
        d = DiffEntry("p", "modify", old_value="a", new_value="b")
        assert d.path == "p"
        assert d.change_type == "modify"
        assert d.old_value == "a"
        assert d.new_value == "b"
