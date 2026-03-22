"""
Enterprise FizzBuzz Platform - Knowledge Graph & Domain Ontology Module

Implements a complete RDF triple store with OWL class hierarchy reasoning,
forward-chaining inference engine, and a bespoke FizzSPARQL query language
for the FizzBuzz domain. Because modulo arithmetic was insufficiently
semantic, and the W3C Semantic Web stack needed a killer app.

The ontology models every integer from 1-100 as an RDF resource with
formal class membership (fizz:Fizz, fizz:Buzz, fizz:FizzBuzz, fizz:Plain),
divisibility predicates, and OWL subclass relationships. fizz:FizzBuzz
inherits from BOTH fizz:Fizz AND fizz:Buzz via multiple inheritance,
because diamond problems are a feature, not a bug.

Tim Berners-Lee would weep — from joy or horror, we cannot say.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FizzSPARQLSyntaxError,
    InferenceFixpointError,
    InvalidTripleError,
    NamespaceResolutionError,
    OntologyConsistencyError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Namespace Registry
# ════════════════════════════════════════════════════════════════════

NAMESPACES: dict[str, str] = {
    "fizz": "http://enterprise-fizzbuzz.example.com/ontology#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


def expand_uri(prefixed: str) -> str:
    """Expand a prefixed URI (e.g. fizz:Number) to its full form."""
    if ":" not in prefixed:
        return prefixed
    prefix, local = prefixed.split(":", 1)
    if prefix not in NAMESPACES:
        raise NamespaceResolutionError(prefix)
    return NAMESPACES[prefix] + local


def compact_uri(full: str) -> str:
    """Compact a full URI to its prefixed form, if possible."""
    for prefix, ns in NAMESPACES.items():
        if full.startswith(ns):
            return f"{prefix}:{full[len(ns):]}"
    return full


# ════════════════════════════════════════════════════════════════════
# RDF Node & Triple
# ════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, eq=True)
class RDFNode:
    """A node in the RDF graph — either a URI resource or a literal value.

    In the Semantic Web, everything is a resource identified by a URI.
    In Enterprise FizzBuzz, everything is a number identified by its
    relationship to modulo arithmetic. The difference is negligible.
    """

    value: str
    is_literal: bool = False

    def __repr__(self) -> str:
        if self.is_literal:
            return f'"{self.value}"'
        return compact_uri(self.value)

    def __str__(self) -> str:
        return repr(self)

    @classmethod
    def uri(cls, prefixed: str) -> RDFNode:
        """Create a URI node from a prefixed URI string."""
        return cls(value=expand_uri(prefixed), is_literal=False)

    @classmethod
    def literal(cls, value: str) -> RDFNode:
        """Create a literal node from a string value."""
        return cls(value=value, is_literal=True)

    @property
    def compact(self) -> str:
        """Return the compact prefixed form of this node."""
        if self.is_literal:
            return f'"{self.value}"'
        return compact_uri(self.value)


@dataclass(frozen=True, eq=True)
class RDFTriple:
    """An RDF triple: the atomic unit of knowledge in the Semantic Web.

    Every fact in the FizzBuzz ontology is expressed as a (subject,
    predicate, object) triple. "fizz:Number_15 fizz:hasClassification
    fizz:FizzBuzz" is arguably the most important triple in the
    history of knowledge representation.
    """

    subject: RDFNode
    predicate: RDFNode
    obj: RDFNode

    def __repr__(self) -> str:
        return f"({self.subject} {self.predicate} {self.obj})"

    def matches(
        self,
        subject: Optional[RDFNode] = None,
        predicate: Optional[RDFNode] = None,
        obj: Optional[RDFNode] = None,
    ) -> bool:
        """Check if this triple matches a pattern (None = wildcard)."""
        if subject is not None and self.subject != subject:
            return False
        if predicate is not None and self.predicate != predicate:
            return False
        if obj is not None and self.obj != obj:
            return False
        return True


# ════════════════════════════════════════════════════════════════════
# Triple Store
# ════════════════════════════════════════════════════════════════════


class TripleStore:
    """An in-memory RDF triple store with three-way indexing.

    Maintains three indices (by subject, predicate, and object) for
    O(1) pattern matching in any position. Because linear scans over
    triples are the kind of performance antipattern that enterprise
    ontology engineers lose sleep over.

    The store also tracks provenance: each triple remembers whether
    it was asserted (explicit) or inferred (derived by the reasoning
    engine). This distinction matters for audit purposes, because
    the compliance team needs to know if a FizzBuzz classification
    was directly observed or merely logically entailed.
    """

    def __init__(self) -> None:
        self._triples: set[RDFTriple] = set()
        self._by_subject: dict[RDFNode, set[RDFTriple]] = {}
        self._by_predicate: dict[RDFNode, set[RDFTriple]] = {}
        self._by_object: dict[RDFNode, set[RDFTriple]] = {}
        self._inferred: set[RDFTriple] = set()
        self._asserted: set[RDFTriple] = set()

    @property
    def size(self) -> int:
        """Total number of triples in the store."""
        return len(self._triples)

    @property
    def asserted_count(self) -> int:
        return len(self._asserted)

    @property
    def inferred_count(self) -> int:
        return len(self._inferred)

    def add(self, triple: RDFTriple, *, inferred: bool = False) -> bool:
        """Add a triple to the store. Returns True if newly added."""
        if triple.subject.value == "" or triple.predicate.value == "" or triple.obj.value == "":
            raise InvalidTripleError(
                triple.subject.value, triple.predicate.value, triple.obj.value
            )

        if triple in self._triples:
            return False

        self._triples.add(triple)
        self._by_subject.setdefault(triple.subject, set()).add(triple)
        self._by_predicate.setdefault(triple.predicate, set()).add(triple)
        self._by_object.setdefault(triple.obj, set()).add(triple)

        if inferred:
            self._inferred.add(triple)
        else:
            self._asserted.add(triple)

        return True

    def add_spo(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        inferred: bool = False,
        obj_literal: bool = False,
    ) -> bool:
        """Convenience: add a triple from prefixed URI strings."""
        s = RDFNode.uri(subject)
        p = RDFNode.uri(predicate)
        o = RDFNode.literal(obj) if obj_literal else RDFNode.uri(obj)
        return self.add(RDFTriple(s, p, o), inferred=inferred)

    def query(
        self,
        subject: Optional[RDFNode] = None,
        predicate: Optional[RDFNode] = None,
        obj: Optional[RDFNode] = None,
    ) -> list[RDFTriple]:
        """Pattern-match triples. None in any position is a wildcard.

        Uses the appropriate index for O(1) lookup when possible,
        falling back to intersection when multiple constraints are
        specified. This is the kind of query optimization that makes
        triple store engineers nod approvingly.
        """
        candidates: Optional[set[RDFTriple]] = None

        if subject is not None:
            s_set = self._by_subject.get(subject, set())
            candidates = s_set if candidates is None else candidates & s_set

        if predicate is not None:
            p_set = self._by_predicate.get(predicate, set())
            candidates = p_set if candidates is None else candidates & p_set

        if obj is not None:
            o_set = self._by_object.get(obj, set())
            candidates = o_set if candidates is None else candidates & o_set

        if candidates is None:
            candidates = self._triples

        # Apply remaining filters
        results = []
        for t in candidates:
            if t.matches(subject, predicate, obj):
                results.append(t)

        return sorted(results, key=lambda t: (t.subject.value, t.predicate.value, t.obj.value))

    def contains(self, subject: str, predicate: str, obj: str) -> bool:
        """Check if a triple exists (using prefixed URIs)."""
        s = RDFNode.uri(subject)
        p = RDFNode.uri(predicate)
        o = RDFNode.uri(obj)
        return RDFTriple(s, p, o) in self._triples

    def all_triples(self) -> list[RDFTriple]:
        """Return all triples, sorted for deterministic output."""
        return sorted(
            self._triples,
            key=lambda t: (t.subject.value, t.predicate.value, t.obj.value),
        )

    def subjects(self) -> set[RDFNode]:
        """Return all unique subjects."""
        return set(self._by_subject.keys())

    def predicates(self) -> set[RDFNode]:
        """Return all unique predicates."""
        return set(self._by_predicate.keys())

    def objects(self) -> set[RDFNode]:
        """Return all unique objects."""
        return set(self._by_object.keys())


def populate_fizzbuzz_domain(
    store: TripleStore,
    range_start: int = 1,
    range_end: int = 100,
    rules: Optional[list[Any]] = None,
) -> int:
    """Populate the triple store with the FizzBuzz domain ontology.

    Creates RDF triples for:
    - Class hierarchy (fizz:Number, fizz:Fizz, fizz:Buzz, fizz:FizzBuzz, fizz:Plain)
    - OWL class definitions
    - Individual numbers with classifications and divisibility properties
    - fizz:FizzBuzz as a subclass of BOTH fizz:Fizz AND fizz:Buzz

    Returns the number of triples added.
    """
    initial_size = store.size

    # ── OWL Class Hierarchy ──
    # fizz:Number is the root class
    store.add_spo("fizz:Number", "rdf:type", "owl:Class")
    store.add_spo("fizz:Fizz", "rdf:type", "owl:Class")
    store.add_spo("fizz:Buzz", "rdf:type", "owl:Class")
    store.add_spo("fizz:FizzBuzz", "rdf:type", "owl:Class")
    store.add_spo("fizz:Plain", "rdf:type", "owl:Class")

    # Subclass relationships
    store.add_spo("fizz:Fizz", "rdfs:subClassOf", "fizz:Number")
    store.add_spo("fizz:Buzz", "rdfs:subClassOf", "fizz:Number")
    store.add_spo("fizz:Plain", "rdfs:subClassOf", "fizz:Number")

    # THE DIAMOND: fizz:FizzBuzz inherits from BOTH fizz:Fizz AND fizz:Buzz
    # Multiple inheritance — the OWL way. Because if Python can do it,
    # so can our ontology. The MRO (Method Resolution Order) is left
    # as an exercise for the reader.
    store.add_spo("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Fizz")
    store.add_spo("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Buzz")

    # Property definitions
    store.add_spo("fizz:hasClassification", "rdf:type", "owl:ObjectProperty")
    store.add_spo("fizz:hasValue", "rdf:type", "owl:DatatypeProperty")
    store.add_spo("fizz:isDivisibleBy", "rdf:type", "owl:ObjectProperty")
    store.add_spo("fizz:hasLabel", "rdf:type", "owl:DatatypeProperty")

    # Divisor resources
    store.add_spo("fizz:Divisor_3", "rdf:type", "fizz:Number")
    store.add_spo("fizz:Divisor_3", "fizz:hasValue", "3", obj_literal=True)
    store.add_spo("fizz:Divisor_5", "rdf:type", "fizz:Number")
    store.add_spo("fizz:Divisor_5", "fizz:hasValue", "5", obj_literal=True)
    store.add_spo("fizz:Divisor_15", "rdf:type", "fizz:Number")
    store.add_spo("fizz:Divisor_15", "fizz:hasValue", "15", obj_literal=True)

    # ── Individual Numbers ──
    for n in range(range_start, range_end + 1):
        num_uri = f"fizz:Number_{n}"
        store.add_spo(num_uri, "rdf:type", "fizz:Number")
        store.add_spo(num_uri, "fizz:hasValue", str(n), obj_literal=True)

        # Classification
        if n % 15 == 0:
            store.add_spo(num_uri, "fizz:hasClassification", "fizz:FizzBuzz")
            store.add_spo(num_uri, "rdf:type", "fizz:FizzBuzz")
            store.add_spo(num_uri, "fizz:hasLabel", "FizzBuzz", obj_literal=True)
        elif n % 3 == 0:
            store.add_spo(num_uri, "fizz:hasClassification", "fizz:Fizz")
            store.add_spo(num_uri, "rdf:type", "fizz:Fizz")
            store.add_spo(num_uri, "fizz:hasLabel", "Fizz", obj_literal=True)
        elif n % 5 == 0:
            store.add_spo(num_uri, "fizz:hasClassification", "fizz:Buzz")
            store.add_spo(num_uri, "rdf:type", "fizz:Buzz")
            store.add_spo(num_uri, "fizz:hasLabel", "Buzz", obj_literal=True)
        else:
            store.add_spo(num_uri, "fizz:hasClassification", "fizz:Plain")
            store.add_spo(num_uri, "rdf:type", "fizz:Plain")
            store.add_spo(num_uri, "fizz:hasLabel", str(n), obj_literal=True)

        # Divisibility properties
        if n % 3 == 0:
            store.add_spo(num_uri, "fizz:isDivisibleBy", "fizz:Divisor_3")
        if n % 5 == 0:
            store.add_spo(num_uri, "fizz:isDivisibleBy", "fizz:Divisor_5")
        if n % 15 == 0:
            store.add_spo(num_uri, "fizz:isDivisibleBy", "fizz:Divisor_15")

    return store.size - initial_size


# ════════════════════════════════════════════════════════════════════
# OWL Class Hierarchy
# ════════════════════════════════════════════════════════════════════


class OWLClassHierarchy:
    """OWL class hierarchy manager with multiple inheritance support.

    Builds a class tree from rdfs:subClassOf triples and supports
    ancestor queries, descendant queries, and the kind of diamond
    inheritance that would make a C++ vtable blush.

    fizz:FizzBuzz is a subclass of BOTH fizz:Fizz AND fizz:Buzz.
    This means every FizzBuzz number is simultaneously a Fizz AND
    a Buzz, which is ontologically accurate and computationally
    satisfying.
    """

    def __init__(self, store: TripleStore) -> None:
        self._store = store
        self._parents: dict[str, list[str]] = {}
        self._children: dict[str, list[str]] = {}
        self._rebuild()

    def _rebuild(self) -> None:
        """Rebuild the class hierarchy from rdfs:subClassOf triples."""
        self._parents.clear()
        self._children.clear()

        subclass_pred = RDFNode.uri("rdfs:subClassOf")
        for triple in self._store.query(predicate=subclass_pred):
            child = compact_uri(triple.subject.value)
            parent = compact_uri(triple.obj.value)
            self._parents.setdefault(child, [])
            if parent not in self._parents[child]:
                self._parents[child].append(parent)
            self._children.setdefault(parent, [])
            if child not in self._children[parent]:
                self._children[parent].append(child)

    def get_parents(self, class_uri: str) -> list[str]:
        """Return direct parent classes."""
        return list(self._parents.get(class_uri, []))

    def get_children(self, class_uri: str) -> list[str]:
        """Return direct child classes."""
        return list(self._children.get(class_uri, []))

    def get_ancestors(self, class_uri: str) -> set[str]:
        """Return all ancestor classes (transitive closure)."""
        ancestors: set[str] = set()
        stack = list(self._parents.get(class_uri, []))
        while stack:
            parent = stack.pop()
            if parent not in ancestors:
                ancestors.add(parent)
                stack.extend(self._parents.get(parent, []))
        return ancestors

    def get_descendants(self, class_uri: str) -> set[str]:
        """Return all descendant classes (transitive closure)."""
        descendants: set[str] = set()
        stack = list(self._children.get(class_uri, []))
        while stack:
            child = stack.pop()
            if child not in descendants:
                descendants.add(child)
                stack.extend(self._children.get(child, []))
        return descendants

    def is_subclass_of(self, child: str, parent: str) -> bool:
        """Check if child is a subclass of parent (direct or transitive)."""
        if child == parent:
            return True
        return parent in self.get_ancestors(child)

    def get_all_classes(self) -> list[str]:
        """Return all classes in the hierarchy."""
        classes: set[str] = set()
        for k, v in self._parents.items():
            classes.add(k)
            classes.update(v)
        for k, v in self._children.items():
            classes.add(k)
            classes.update(v)
        return sorted(classes)

    def get_roots(self) -> list[str]:
        """Return root classes (no parents in the hierarchy)."""
        all_children = set(self._parents.keys())
        all_parents = set()
        for parents in self._parents.values():
            all_parents.update(parents)
        return sorted(all_parents - all_children)

    def validate_consistency(self) -> list[str]:
        """Check for circular inheritance and other inconsistencies."""
        errors: list[str] = []
        for cls in self.get_all_classes():
            if cls in self.get_ancestors(cls):
                errors.append(f"Circular inheritance detected: {cls} is its own ancestor")
        return errors


# ════════════════════════════════════════════════════════════════════
# Forward-Chaining Inference Engine
# ════════════════════════════════════════════════════════════════════


@dataclass
class InferenceRule:
    """A rule for the forward-chaining inference engine.

    Each rule has a name and a function that, given the current
    triple store, returns new triples to add. Rules are applied
    repeatedly until no new triples are generated (fixpoint).
    """

    name: str
    apply: Callable[[TripleStore], list[RDFTriple]]
    description: str = ""


class InferenceEngine:
    """Forward-chaining inference engine for OWL reasoning.

    Repeatedly applies inference rules to the triple store until
    a fixpoint is reached (no new triples generated). This is the
    knowledge graph equivalent of stirring a pot until the soup
    stops changing — except the soup is made of RDF triples and
    the spoon is first-order logic.

    Built-in rules:
    - Transitive subclass closure (rdfs:subClassOf)
    - Instance type propagation (if X rdf:type fizz:Fizz and
      fizz:Fizz rdfs:subClassOf fizz:Number, then X rdf:type fizz:Number)
    """

    def __init__(self, store: TripleStore, max_iterations: int = 100) -> None:
        self._store = store
        self._max_iterations = max_iterations
        self._rules: list[InferenceRule] = []
        self._iterations_run: int = 0
        self._triples_inferred: int = 0
        self._register_builtin_rules()

    @property
    def iterations_run(self) -> int:
        return self._iterations_run

    @property
    def triples_inferred(self) -> int:
        return self._triples_inferred

    @property
    def rules(self) -> list[InferenceRule]:
        return list(self._rules)

    def _register_builtin_rules(self) -> None:
        """Register the built-in OWL/RDFS inference rules."""
        self._rules.append(InferenceRule(
            name="rdfs:subClassOf transitivity",
            description=(
                "If A rdfs:subClassOf B and B rdfs:subClassOf C, "
                "then A rdfs:subClassOf C. The transitive closure "
                "of class hierarchies, because indirect ancestry "
                "matters in ontologies and in enterprise org charts."
            ),
            apply=self._rule_subclass_transitivity,
        ))
        self._rules.append(InferenceRule(
            name="rdf:type propagation via rdfs:subClassOf",
            description=(
                "If X rdf:type A and A rdfs:subClassOf B, "
                "then X rdf:type B. Every instance of a subclass "
                "is also an instance of its superclass(es). FizzBuzz "
                "numbers are simultaneously Fizz, Buzz, AND Number."
            ),
            apply=self._rule_type_propagation,
        ))

    def add_rule(self, rule: InferenceRule) -> None:
        """Register a custom inference rule."""
        self._rules.append(rule)

    def _rule_subclass_transitivity(self, store: TripleStore) -> list[RDFTriple]:
        """Compute transitive closure of rdfs:subClassOf."""
        new_triples: list[RDFTriple] = []
        subclass_pred = RDFNode.uri("rdfs:subClassOf")
        subclass_triples = store.query(predicate=subclass_pred)

        # Build adjacency
        parents: dict[RDFNode, set[RDFNode]] = {}
        for t in subclass_triples:
            parents.setdefault(t.subject, set()).add(t.obj)

        # Transitive closure
        for child, direct_parents in list(parents.items()):
            for parent in list(direct_parents):
                for grandparent in parents.get(parent, set()):
                    new_triple = RDFTriple(child, subclass_pred, grandparent)
                    if new_triple not in store._triples:
                        new_triples.append(new_triple)

        return new_triples

    def _rule_type_propagation(self, store: TripleStore) -> list[RDFTriple]:
        """Propagate rdf:type along rdfs:subClassOf relationships."""
        new_triples: list[RDFTriple] = []
        type_pred = RDFNode.uri("rdf:type")
        subclass_pred = RDFNode.uri("rdfs:subClassOf")

        type_triples = store.query(predicate=type_pred)
        subclass_triples = store.query(predicate=subclass_pred)

        # Build subclass map: class -> set of superclasses
        superclasses: dict[RDFNode, set[RDFNode]] = {}
        for t in subclass_triples:
            superclasses.setdefault(t.subject, set()).add(t.obj)

        # For each typed instance, add types for all superclasses
        for t in type_triples:
            instance = t.subject
            cls = t.obj
            for superclass in superclasses.get(cls, set()):
                new_triple = RDFTriple(instance, type_pred, superclass)
                if new_triple not in store._triples:
                    new_triples.append(new_triple)

        return new_triples

    def run(self) -> int:
        """Run forward chaining until fixpoint or max iterations.

        Returns the total number of new triples inferred.
        """
        self._iterations_run = 0
        self._triples_inferred = 0

        for iteration in range(1, self._max_iterations + 1):
            self._iterations_run = iteration
            new_triples: list[RDFTriple] = []

            for rule in self._rules:
                generated = rule.apply(self._store)
                new_triples.extend(generated)

            if not new_triples:
                # Fixpoint reached — no new knowledge discovered
                logger.debug(
                    "Inference fixpoint reached after %d iterations. "
                    "The ontology has achieved enlightenment.",
                    iteration,
                )
                return self._triples_inferred

            added = 0
            for triple in new_triples:
                if self._store.add(triple, inferred=True):
                    added += 1
            self._triples_inferred += added

            if added == 0:
                # All generated triples were duplicates
                logger.debug(
                    "Inference fixpoint reached after %d iterations "
                    "(all generated triples were redundant).",
                    iteration,
                )
                return self._triples_inferred

        raise InferenceFixpointError(self._max_iterations, self._triples_inferred)


# ════════════════════════════════════════════════════════════════════
# FizzSPARQL Parser & Executor
# ════════════════════════════════════════════════════════════════════


@dataclass
class FizzSPARQLQuery:
    """Parsed representation of a FizzSPARQL query.

    Supports: SELECT ?var1 ?var2 WHERE { pattern1 . pattern2 } LIMIT N

    This is a strict subset of SPARQL 1.1 that supports exactly enough
    features to query a FizzBuzz ontology. The W3C working group
    would be proud of our conformance level: approximately 0.3%.
    """

    variables: list[str]
    patterns: list[tuple[str, str, str]]  # (subject, predicate, object) patterns
    limit: Optional[int] = None


class FizzSPARQLParser:
    """Recursive descent parser for the FizzSPARQL query language.

    Grammar:
        query     ::= SELECT variables WHERE '{' patterns '}' (LIMIT INT)?
        variables ::= variable+
        variable  ::= '?' IDENT
        patterns  ::= pattern ('.' pattern)*
        pattern   ::= term term term
        term      ::= variable | prefixed_uri | literal

    The parser is deliberately over-engineered for a language that
    supports exactly one query form. In enterprise software, every
    parser must be recursive descent, even when a regular expression
    would suffice.
    """

    def __init__(self, query: str) -> None:
        self._query = query
        self._tokens: list[str] = []
        self._pos = 0

    def parse(self) -> FizzSPARQLQuery:
        """Parse the query string into a FizzSPARQLQuery object."""
        self._tokenize()
        self._pos = 0

        # SELECT
        self._expect("SELECT")

        # Variables
        variables: list[str] = []
        while self._pos < len(self._tokens) and self._peek().startswith("?"):
            variables.append(self._advance())
        if not variables:
            self._error("Expected at least one variable after SELECT")

        # WHERE
        self._expect("WHERE")

        # { patterns }
        self._expect("{")
        patterns = self._parse_patterns()
        self._expect("}")

        # Optional LIMIT
        limit: Optional[int] = None
        if self._pos < len(self._tokens) and self._peek() == "LIMIT":
            self._advance()
            limit_str = self._advance()
            try:
                limit = int(limit_str)
            except ValueError:
                self._error(f"Expected integer after LIMIT, got '{limit_str}'")

        return FizzSPARQLQuery(
            variables=variables,
            patterns=patterns,
            limit=limit,
        )

    def _tokenize(self) -> None:
        """Split the query into tokens, respecting braces and dots."""
        tokens: list[str] = []
        i = 0
        q = self._query.strip()

        while i < len(q):
            # Skip whitespace
            if q[i].isspace():
                i += 1
                continue

            # Braces and dots are their own tokens
            if q[i] in "{}." :
                tokens.append(q[i])
                i += 1
                continue

            # Quoted literals
            if q[i] == '"':
                j = i + 1
                while j < len(q) and q[j] != '"':
                    j += 1
                tokens.append(q[i : j + 1])
                i = j + 1
                continue

            # Regular token (word, variable, URI)
            j = i
            while j < len(q) and not q[j].isspace() and q[j] not in "{}.":
                j += 1
            tokens.append(q[i:j])
            i = j

        self._tokens = tokens

    def _peek(self) -> str:
        if self._pos >= len(self._tokens):
            self._error("Unexpected end of query")
        return self._tokens[self._pos]

    def _advance(self) -> str:
        token = self._peek()
        self._pos += 1
        return token

    def _expect(self, expected: str) -> None:
        token = self._advance()
        if token.upper() != expected.upper():
            self._error(f"Expected '{expected}', got '{token}'")

    def _error(self, reason: str) -> None:
        raise FizzSPARQLSyntaxError(self._query, self._pos, reason)

    def _parse_patterns(self) -> list[tuple[str, str, str]]:
        """Parse triple patterns: s p o (. s p o)*"""
        patterns: list[tuple[str, str, str]] = []

        while self._pos < len(self._tokens) and self._peek() != "}":
            # Skip dots between patterns
            if self._peek() == ".":
                self._advance()
                continue

            s = self._advance()
            p = self._advance()
            o = self._advance()
            patterns.append((s, p, o))

        if not patterns:
            self._error("Expected at least one triple pattern in WHERE clause")

        return patterns


class FizzSPARQLExecutor:
    """Executes FizzSPARQL queries against a triple store.

    Implements pattern matching with variable binding, joining
    results across multiple patterns. The join algorithm is a
    nested loop join, because hash joins are for databases that
    process more than 100 triples.
    """

    def __init__(self, store: TripleStore) -> None:
        self._store = store

    def execute(self, query: FizzSPARQLQuery) -> list[dict[str, str]]:
        """Execute a parsed FizzSPARQL query and return bindings."""
        # Start with an empty binding set
        bindings: list[dict[str, str]] = [{}]

        for pattern in query.patterns:
            bindings = self._join_pattern(bindings, pattern)

        # Project only requested variables
        results: list[dict[str, str]] = []
        seen: set[tuple[tuple[str, str], ...]] = set()

        for binding in bindings:
            projected: dict[str, str] = {}
            for var in query.variables:
                if var in binding:
                    projected[var] = binding[var]
            key = tuple(sorted(projected.items()))
            if key not in seen:
                seen.add(key)
                results.append(projected)

        # Apply LIMIT
        if query.limit is not None:
            results = results[: query.limit]

        return results

    def _join_pattern(
        self,
        bindings: list[dict[str, str]],
        pattern: tuple[str, str, str],
    ) -> list[dict[str, str]]:
        """Join existing bindings with a triple pattern."""
        s_pat, p_pat, o_pat = pattern
        new_bindings: list[dict[str, str]] = []

        for binding in bindings:
            # Resolve pattern terms against current binding
            s_resolved = self._resolve_term(s_pat, binding)
            p_resolved = self._resolve_term(p_pat, binding)
            o_resolved = self._resolve_term(o_pat, binding)

            # Convert resolved terms to RDFNodes for querying
            s_node = self._term_to_node(s_resolved) if s_resolved is not None else None
            p_node = self._term_to_node(p_resolved) if p_resolved is not None else None
            o_node = self._term_to_node(o_resolved) if o_resolved is not None else None

            matches = self._store.query(s_node, p_node, o_node)

            for triple in matches:
                new_binding = dict(binding)
                if self._bind_term(s_pat, triple.subject, new_binding) and \
                   self._bind_term(p_pat, triple.predicate, new_binding) and \
                   self._bind_term(o_pat, triple.obj, new_binding):
                    new_bindings.append(new_binding)

        return new_bindings

    def _resolve_term(self, term: str, binding: dict[str, str]) -> Optional[str]:
        """Resolve a term: if it's a bound variable, return its value; otherwise return the term."""
        if term.startswith("?"):
            return binding.get(term)  # None if unbound = wildcard
        return term

    def _term_to_node(self, term: str) -> RDFNode:
        """Convert a resolved term string to an RDFNode."""
        if term.startswith('"') and term.endswith('"'):
            return RDFNode.literal(term[1:-1])
        return RDFNode.uri(term)

    def _bind_term(self, term: str, node: RDFNode, binding: dict[str, str]) -> bool:
        """Attempt to bind a variable to a node value. Returns False on conflict."""
        if not term.startswith("?"):
            return True  # Not a variable, nothing to bind

        node_str = node.compact
        if term in binding:
            return binding[term] == node_str
        binding[term] = node_str
        return True


def execute_fizzsparql(store: TripleStore, query_str: str) -> list[dict[str, str]]:
    """Parse and execute a FizzSPARQL query in one step."""
    parser = FizzSPARQLParser(query_str)
    query = parser.parse()
    executor = FizzSPARQLExecutor(store)
    return executor.execute(query)


# ════════════════════════════════════════════════════════════════════
# Ontology Visualizer
# ════════════════════════════════════════════════════════════════════


class OntologyVisualizer:
    """Renders ASCII class hierarchy trees for the FizzBuzz ontology.

    Produces a tree diagram showing the OWL class hierarchy with
    multiple inheritance indicators. The diamond pattern between
    fizz:Fizz, fizz:Buzz, and fizz:FizzBuzz is rendered with special
    notation to highlight this ontological milestone.
    """

    @staticmethod
    def render_class_tree(hierarchy: OWLClassHierarchy, width: int = 60) -> str:
        """Render the OWL class hierarchy as an ASCII tree."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        lines.append(border)
        lines.append("|" + " OWL CLASS HIERARCHY".ljust(width - 2) + "|")
        lines.append("|" + " (with multiple inheritance)".ljust(width - 2) + "|")
        lines.append(border)
        lines.append("")

        roots = hierarchy.get_roots()
        if not roots:
            # If no roots found, try owl:Thing or fizz:Number
            all_classes = hierarchy.get_all_classes()
            if all_classes:
                roots = [all_classes[0]]

        for root in roots:
            OntologyVisualizer._render_node(
                hierarchy, root, lines, prefix="  ", is_last=True, visited=set()
            )

        lines.append("")
        lines.append(border)

        # Diamond inheritance annotation
        if hierarchy.is_subclass_of("fizz:FizzBuzz", "fizz:Fizz") and \
           hierarchy.is_subclass_of("fizz:FizzBuzz", "fizz:Buzz"):
            lines.append("|" + " DIAMOND INHERITANCE DETECTED".ljust(width - 2) + "|")
            lines.append("|" + " fizz:FizzBuzz <-- fizz:Fizz".ljust(width - 2) + "|")
            lines.append("|" + "               <-- fizz:Buzz".ljust(width - 2) + "|")
            lines.append("|" + " The MRO is: FizzBuzz -> Fizz -> Buzz -> Number".ljust(width - 2) + "|")
            lines.append(border)

        return "\n".join(lines)

    @staticmethod
    def _render_node(
        hierarchy: OWLClassHierarchy,
        class_uri: str,
        lines: list[str],
        prefix: str,
        is_last: bool,
        visited: set[str],
    ) -> None:
        """Recursively render a class node and its children."""
        if class_uri in visited:
            connector = "\\-- " if is_last else "+-- "
            lines.append(f"{prefix}{connector}{class_uri} (circular ref)")
            return

        visited.add(class_uri)
        connector = "\\-- " if is_last else "+-- "
        parents = hierarchy.get_parents(class_uri)
        parent_note = ""
        if len(parents) > 1:
            parent_note = f" [multiple inheritance: {', '.join(parents)}]"

        lines.append(f"{prefix}{connector}{class_uri}{parent_note}")

        children = hierarchy.get_children(class_uri)
        for i, child in enumerate(children):
            child_prefix = prefix + ("    " if is_last else "|   ")
            OntologyVisualizer._render_node(
                hierarchy, child, lines, child_prefix,
                is_last=(i == len(children) - 1),
                visited=set(visited),  # Copy to allow diamond rendering
            )


# ════════════════════════════════════════════════════════════════════
# Knowledge Dashboard
# ════════════════════════════════════════════════════════════════════


class KnowledgeDashboard:
    """ASCII dashboard for the Knowledge Graph & Domain Ontology.

    Renders comprehensive statistics about the triple store,
    inference engine, OWL class hierarchy, and FizzSPARQL query
    capabilities. Because every enterprise subsystem needs a
    dashboard, even the ones that model FizzBuzz as an ontology.
    """

    @staticmethod
    def render(
        store: TripleStore,
        hierarchy: OWLClassHierarchy,
        engine: InferenceEngine,
        *,
        width: int = 60,
        show_class_hierarchy: bool = True,
        show_triple_stats: bool = True,
        show_inference_stats: bool = True,
    ) -> str:
        """Render the full knowledge graph dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        lines.append(border)
        title = "KNOWLEDGE GRAPH & DOMAIN ONTOLOGY DASHBOARD"
        lines.append("|" + title.center(width - 2) + "|")
        subtitle = "Semantic Web for FizzBuzz"
        lines.append("|" + subtitle.center(width - 2) + "|")
        lines.append(border)

        if show_triple_stats:
            lines.append("")
            lines.append(thin)
            lines.append("|" + " TRIPLE STORE STATISTICS".ljust(width - 2) + "|")
            lines.append(thin)

            stats = [
                ("Total Triples", str(store.size)),
                ("Asserted (explicit)", str(store.asserted_count)),
                ("Inferred (derived)", str(store.inferred_count)),
                ("Unique Subjects", str(len(store.subjects()))),
                ("Unique Predicates", str(len(store.predicates()))),
                ("Unique Objects", str(len(store.objects()))),
            ]

            for label, value in stats:
                padding = width - 4 - len(label) - len(value)
                lines.append(f"| {label}{'.' * max(1, padding)}{value} |")

            lines.append(thin)

        if show_inference_stats:
            lines.append("")
            lines.append(thin)
            lines.append("|" + " INFERENCE ENGINE STATISTICS".ljust(width - 2) + "|")
            lines.append(thin)

            inf_stats = [
                ("Inference Rules", str(len(engine.rules))),
                ("Iterations Run", str(engine.iterations_run)),
                ("Triples Inferred", str(engine.triples_inferred)),
                ("Status", "FIXPOINT REACHED" if engine.iterations_run > 0 else "NOT RUN"),
            ]

            for label, value in inf_stats:
                padding = width - 4 - len(label) - len(value)
                lines.append(f"| {label}{'.' * max(1, padding)}{value} |")

            for rule in engine.rules:
                lines.append(f"|   Rule: {rule.name:<{width - 13}}|")

            lines.append(thin)

        if show_class_hierarchy:
            lines.append("")
            lines.append(OntologyVisualizer.render_class_tree(hierarchy, width))

        # Namespace registry
        lines.append("")
        lines.append(thin)
        lines.append("|" + " REGISTERED NAMESPACES".ljust(width - 2) + "|")
        lines.append(thin)
        for prefix, uri in sorted(NAMESPACES.items()):
            entry = f" {prefix}: -> {uri}"
            if len(entry) > width - 3:
                entry = entry[: width - 6] + "..."
            lines.append("|" + entry.ljust(width - 2) + "|")
        lines.append(thin)

        lines.append("")
        lines.append(border)
        lines.append("|" + " Tim Berners-Lee would be proud. Probably.".center(width - 2) + "|")
        lines.append(border)

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph Middleware
# ════════════════════════════════════════════════════════════════════


class KnowledgeGraphMiddleware(IMiddleware):
    """Middleware that annotates each FizzBuzz evaluation with Knowledge Graph data.

    For every number processed, this middleware queries the ontology to
    determine the number's formal RDF classification, class memberships,
    and ontological ancestors. This information is added to the processing
    context metadata, because a FizzBuzz result without semantic annotations
    is just... a string.

    Priority 16 ensures this runs after validation and logging but before
    translation, giving the Knowledge Graph a clear view of the raw
    evaluation result before it gets localized.
    """

    def __init__(
        self,
        store: TripleStore,
        hierarchy: OWLClassHierarchy,
        event_bus: Any = None,
    ) -> None:
        self._store = store
        self._hierarchy = hierarchy
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        num_uri = f"fizz:Number_{context.number}"
        num_node = RDFNode.uri(num_uri)

        # Query classification
        class_pred = RDFNode.uri("fizz:hasClassification")
        classifications = self._store.query(subject=num_node, predicate=class_pred)

        # Query divisibility
        div_pred = RDFNode.uri("fizz:isDivisibleBy")
        divisibilities = self._store.query(subject=num_node, predicate=div_pred)

        # Query type memberships
        type_pred = RDFNode.uri("rdf:type")
        types = self._store.query(subject=num_node, predicate=type_pred)

        result.metadata["kg_classification"] = [
            compact_uri(t.obj.value) for t in classifications
        ]
        result.metadata["kg_divisible_by"] = [
            compact_uri(t.obj.value) for t in divisibilities
        ]
        result.metadata["kg_type_memberships"] = [
            compact_uri(t.obj.value) for t in types
        ]
        result.metadata["kg_triple_count"] = self._store.size

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.KG_SPARQL_EXECUTED,
                payload={
                    "number": context.number,
                    "classifications": result.metadata["kg_classification"],
                },
                source="KnowledgeGraphMiddleware",
            ))

        return result

    def get_name(self) -> str:
        return "KnowledgeGraphMiddleware"

    def get_priority(self) -> int:
        return 16
