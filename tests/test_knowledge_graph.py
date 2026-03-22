"""
Enterprise FizzBuzz Platform - Knowledge Graph & Domain Ontology Test Suite

Comprehensive tests for the RDF triple store, OWL class hierarchy reasoning,
forward-chaining inference engine, FizzSPARQL query language, ontology
visualizer, knowledge dashboard, and middleware integration.

Because if you're going to model FizzBuzz as a Semantic Web ontology,
you had better make sure the ontological commitments are rigorously tested.
Tim Berners-Lee would expect nothing less.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.knowledge_graph import (
    NAMESPACES,
    FizzSPARQLExecutor,
    FizzSPARQLParser,
    FizzSPARQLQuery,
    InferenceEngine,
    InferenceRule,
    KnowledgeDashboard,
    KnowledgeGraphMiddleware,
    OWLClassHierarchy,
    OntologyVisualizer,
    RDFNode,
    RDFTriple,
    TripleStore,
    compact_uri,
    expand_uri,
    execute_fizzsparql,
    populate_fizzbuzz_domain,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzSPARQLSyntaxError,
    InferenceFixpointError,
    InvalidTripleError,
    KnowledgeGraphError,
    NamespaceResolutionError,
    OntologyConsistencyError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def empty_store() -> TripleStore:
    """A pristine triple store, unsullied by semantic knowledge."""
    return TripleStore()


@pytest.fixture
def populated_store() -> TripleStore:
    """A triple store populated with the FizzBuzz domain ontology (1-15)."""
    store = TripleStore()
    populate_fizzbuzz_domain(store, range_start=1, range_end=15)
    return store


@pytest.fixture
def hierarchy(populated_store: TripleStore) -> OWLClassHierarchy:
    """An OWL class hierarchy built from the populated store."""
    return OWLClassHierarchy(populated_store)


@pytest.fixture
def engine(populated_store: TripleStore) -> InferenceEngine:
    """An inference engine bound to the populated store."""
    return InferenceEngine(populated_store)


# ════════════════════════════════════════════════════════════════════
# RDFNode Tests
# ════════════════════════════════════════════════════════════════════


class TestRDFNode:
    """Tests for RDF node creation, equality, and URI handling."""

    def test_uri_node_creation(self):
        """A URI node expands the prefixed URI and stores the full form."""
        node = RDFNode.uri("fizz:Number")
        assert node.value == NAMESPACES["fizz"] + "Number"
        assert node.is_literal is False

    def test_literal_node_creation(self):
        """A literal node stores the raw value and marks itself as literal."""
        node = RDFNode.literal("42")
        assert node.value == "42"
        assert node.is_literal is True

    def test_uri_node_equality(self):
        """Two URI nodes with the same expanded URI are equal."""
        a = RDFNode.uri("fizz:Number")
        b = RDFNode.uri("fizz:Number")
        assert a == b
        assert hash(a) == hash(b)

    def test_literal_node_equality(self):
        """Two literal nodes with the same value are equal."""
        a = RDFNode.literal("hello")
        b = RDFNode.literal("hello")
        assert a == b

    def test_uri_vs_literal_inequality(self):
        """A URI node and a literal node with the same string are not equal."""
        uri = RDFNode(value="42", is_literal=False)
        lit = RDFNode.literal("42")
        assert uri != lit

    def test_compact_property_uri(self):
        """The compact property returns the prefixed form for URI nodes."""
        node = RDFNode.uri("fizz:Buzz")
        assert node.compact == "fizz:Buzz"

    def test_compact_property_literal(self):
        """The compact property wraps literal values in quotes."""
        node = RDFNode.literal("15")
        assert node.compact == '"15"'

    def test_repr_uri(self):
        """URI node repr shows the compact prefixed form."""
        node = RDFNode.uri("rdf:type")
        assert "rdf:type" in repr(node)

    def test_repr_literal(self):
        """Literal node repr wraps the value in double quotes."""
        node = RDFNode.literal("Fizz")
        assert repr(node) == '"Fizz"'


# ════════════════════════════════════════════════════════════════════
# Namespace Resolution Tests
# ════════════════════════════════════════════════════════════════════


class TestNamespaceResolution:
    """Tests for URI expansion and compaction."""

    def test_expand_known_prefix(self):
        """Expanding a known prefix produces the full namespace URI."""
        result = expand_uri("fizz:FizzBuzz")
        assert result == NAMESPACES["fizz"] + "FizzBuzz"

    def test_expand_unknown_prefix_raises(self):
        """Expanding an unknown prefix raises NamespaceResolutionError."""
        with pytest.raises(NamespaceResolutionError):
            expand_uri("bogus:Something")

    def test_expand_no_colon(self):
        """A string without a colon is returned as-is (no prefix)."""
        assert expand_uri("noprefix") == "noprefix"

    def test_compact_known_uri(self):
        """Compacting a full namespace URI returns the prefixed form."""
        full = NAMESPACES["fizz"] + "Plain"
        assert compact_uri(full) == "fizz:Plain"

    def test_compact_unknown_uri(self):
        """Compacting an unknown URI returns it unchanged."""
        unknown = "http://example.com/unknown#thing"
        assert compact_uri(unknown) == unknown


# ════════════════════════════════════════════════════════════════════
# RDFTriple Tests
# ════════════════════════════════════════════════════════════════════


class TestRDFTriple:
    """Tests for RDF triple creation and pattern matching."""

    def test_triple_creation(self):
        """A triple is created from three RDF nodes."""
        s = RDFNode.uri("fizz:Number_3")
        p = RDFNode.uri("rdf:type")
        o = RDFNode.uri("fizz:Fizz")
        triple = RDFTriple(s, p, o)
        assert triple.subject == s
        assert triple.predicate == p
        assert triple.obj == o

    def test_triple_equality(self):
        """Two triples with the same s/p/o are equal."""
        t1 = RDFTriple(
            RDFNode.uri("fizz:Number_3"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Fizz"),
        )
        t2 = RDFTriple(
            RDFNode.uri("fizz:Number_3"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Fizz"),
        )
        assert t1 == t2
        assert hash(t1) == hash(t2)

    def test_triple_matches_wildcard_all(self):
        """A triple matches a pattern where all positions are None (wildcard)."""
        t = RDFTriple(
            RDFNode.uri("fizz:Number_1"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        assert t.matches() is True

    def test_triple_matches_subject(self):
        """A triple matches when only the subject is constrained and matches."""
        t = RDFTriple(
            RDFNode.uri("fizz:Number_5"),
            RDFNode.uri("fizz:hasClassification"),
            RDFNode.uri("fizz:Buzz"),
        )
        assert t.matches(subject=RDFNode.uri("fizz:Number_5")) is True
        assert t.matches(subject=RDFNode.uri("fizz:Number_3")) is False

    def test_triple_matches_predicate_and_object(self):
        """A triple matches when both predicate and object are constrained."""
        t = RDFTriple(
            RDFNode.uri("fizz:Number_15"),
            RDFNode.uri("fizz:hasClassification"),
            RDFNode.uri("fizz:FizzBuzz"),
        )
        assert t.matches(
            predicate=RDFNode.uri("fizz:hasClassification"),
            obj=RDFNode.uri("fizz:FizzBuzz"),
        ) is True
        assert t.matches(
            predicate=RDFNode.uri("fizz:hasClassification"),
            obj=RDFNode.uri("fizz:Fizz"),
        ) is False


# ════════════════════════════════════════════════════════════════════
# TripleStore Tests
# ════════════════════════════════════════════════════════════════════


class TestTripleStore:
    """Tests for the triple store: add, remove, query, and bulk populate."""

    def test_empty_store_has_zero_size(self, empty_store: TripleStore):
        """A fresh triple store has size zero."""
        assert empty_store.size == 0

    def test_add_triple(self, empty_store: TripleStore):
        """Adding a triple increases the store size by one."""
        triple = RDFTriple(
            RDFNode.uri("fizz:Number_1"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        result = empty_store.add(triple)
        assert result is True
        assert empty_store.size == 1

    def test_add_duplicate_returns_false(self, empty_store: TripleStore):
        """Adding a duplicate triple returns False and does not increase size."""
        triple = RDFTriple(
            RDFNode.uri("fizz:Number_1"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        empty_store.add(triple)
        result = empty_store.add(triple)
        assert result is False
        assert empty_store.size == 1

    def test_add_invalid_triple_raises(self, empty_store: TripleStore):
        """Adding a triple with an empty string component raises InvalidTripleError."""
        triple = RDFTriple(
            RDFNode(value="", is_literal=False),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        with pytest.raises(InvalidTripleError):
            empty_store.add(triple)

    def test_add_spo_convenience(self, empty_store: TripleStore):
        """The add_spo convenience method creates and adds a triple from strings."""
        result = empty_store.add_spo("fizz:Number_7", "rdf:type", "fizz:Plain")
        assert result is True
        assert empty_store.size == 1

    def test_add_spo_literal_object(self, empty_store: TripleStore):
        """add_spo with obj_literal=True creates a literal object node."""
        empty_store.add_spo("fizz:Number_3", "fizz:hasValue", "3", obj_literal=True)
        results = empty_store.query(
            subject=RDFNode.uri("fizz:Number_3"),
            predicate=RDFNode.uri("fizz:hasValue"),
        )
        assert len(results) == 1
        assert results[0].obj.is_literal is True
        assert results[0].obj.value == "3"

    def test_query_wildcard_all(self, populated_store: TripleStore):
        """Querying with all wildcards returns all triples."""
        all_triples = populated_store.query()
        assert len(all_triples) == populated_store.size

    def test_query_by_subject(self, populated_store: TripleStore):
        """Querying by subject returns only triples with that subject."""
        results = populated_store.query(subject=RDFNode.uri("fizz:Number_15"))
        assert len(results) > 0
        for t in results:
            assert t.subject == RDFNode.uri("fizz:Number_15")

    def test_query_by_predicate(self, populated_store: TripleStore):
        """Querying by predicate returns only triples with that predicate."""
        results = populated_store.query(predicate=RDFNode.uri("fizz:hasClassification"))
        assert len(results) == 15  # One classification per number in 1-15

    def test_query_by_subject_and_predicate(self, populated_store: TripleStore):
        """Querying by both subject and predicate narrows results correctly."""
        results = populated_store.query(
            subject=RDFNode.uri("fizz:Number_3"),
            predicate=RDFNode.uri("fizz:hasClassification"),
        )
        assert len(results) == 1
        assert results[0].obj == RDFNode.uri("fizz:Fizz")

    def test_contains_existing_triple(self, populated_store: TripleStore):
        """contains() returns True for a triple that exists in the store."""
        assert populated_store.contains("fizz:Number_3", "fizz:hasClassification", "fizz:Fizz")

    def test_contains_missing_triple(self, populated_store: TripleStore):
        """contains() returns False for a triple that does not exist."""
        assert not populated_store.contains("fizz:Number_3", "fizz:hasClassification", "fizz:Buzz")

    def test_subjects_returns_unique_subjects(self, populated_store: TripleStore):
        """subjects() returns the set of all unique subject nodes."""
        subjects = populated_store.subjects()
        assert len(subjects) > 0
        assert RDFNode.uri("fizz:Number_1") in subjects

    def test_predicates_returns_unique_predicates(self, populated_store: TripleStore):
        """predicates() returns the set of all unique predicate nodes."""
        predicates = populated_store.predicates()
        assert RDFNode.uri("rdf:type") in predicates
        assert RDFNode.uri("fizz:hasClassification") in predicates

    def test_asserted_vs_inferred_counts(self, empty_store: TripleStore):
        """Asserted and inferred triples are tracked separately."""
        t1 = RDFTriple(
            RDFNode.uri("fizz:A"), RDFNode.uri("rdf:type"), RDFNode.uri("fizz:B"),
        )
        t2 = RDFTriple(
            RDFNode.uri("fizz:C"), RDFNode.uri("rdf:type"), RDFNode.uri("fizz:D"),
        )
        empty_store.add(t1, inferred=False)
        empty_store.add(t2, inferred=True)
        assert empty_store.asserted_count == 1
        assert empty_store.inferred_count == 1
        assert empty_store.size == 2

    def test_all_triples_sorted(self, empty_store: TripleStore):
        """all_triples() returns triples sorted by (subject, predicate, object)."""
        empty_store.add_spo("fizz:Z", "rdf:type", "fizz:A")
        empty_store.add_spo("fizz:A", "rdf:type", "fizz:Z")
        triples = empty_store.all_triples()
        assert triples[0].subject.value < triples[1].subject.value


# ════════════════════════════════════════════════════════════════════
# Bulk Population Tests
# ════════════════════════════════════════════════════════════════════


class TestPopulateFizzBuzzDomain:
    """Tests for populating the triple store with the FizzBuzz ontology."""

    def test_populate_returns_triple_count(self, empty_store: TripleStore):
        """populate_fizzbuzz_domain returns the number of triples added."""
        count = populate_fizzbuzz_domain(empty_store, range_start=1, range_end=5)
        assert count > 0
        assert count == empty_store.size

    def test_populate_creates_class_hierarchy(self, populated_store: TripleStore):
        """The ontology defines fizz:Fizz, fizz:Buzz, fizz:FizzBuzz, fizz:Plain as OWL classes."""
        for cls in ["fizz:Fizz", "fizz:Buzz", "fizz:FizzBuzz", "fizz:Plain", "fizz:Number"]:
            assert populated_store.contains(cls, "rdf:type", "owl:Class"), \
                f"{cls} should be defined as an owl:Class"

    def test_populate_fizzbuzz_is_subclass_of_fizz_and_buzz(self, populated_store: TripleStore):
        """fizz:FizzBuzz is a subclass of both fizz:Fizz and fizz:Buzz (diamond)."""
        assert populated_store.contains("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Fizz")
        assert populated_store.contains("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Buzz")

    def test_populate_number_15_is_fizzbuzz(self, populated_store: TripleStore):
        """Number 15 is classified as fizz:FizzBuzz."""
        assert populated_store.contains(
            "fizz:Number_15", "fizz:hasClassification", "fizz:FizzBuzz"
        )

    def test_populate_number_3_is_fizz(self, populated_store: TripleStore):
        """Number 3 is classified as fizz:Fizz."""
        assert populated_store.contains("fizz:Number_3", "fizz:hasClassification", "fizz:Fizz")

    def test_populate_number_5_is_buzz(self, populated_store: TripleStore):
        """Number 5 is classified as fizz:Buzz."""
        assert populated_store.contains("fizz:Number_5", "fizz:hasClassification", "fizz:Buzz")

    def test_populate_number_7_is_plain(self, populated_store: TripleStore):
        """Number 7 is classified as fizz:Plain."""
        assert populated_store.contains("fizz:Number_7", "fizz:hasClassification", "fizz:Plain")

    def test_populate_divisibility_by_3(self, populated_store: TripleStore):
        """Numbers divisible by 3 have fizz:isDivisibleBy fizz:Divisor_3."""
        assert populated_store.contains("fizz:Number_9", "fizz:isDivisibleBy", "fizz:Divisor_3")
        assert not populated_store.contains("fizz:Number_7", "fizz:isDivisibleBy", "fizz:Divisor_3")


# ════════════════════════════════════════════════════════════════════
# OWL Class Hierarchy Tests
# ════════════════════════════════════════════════════════════════════


class TestOWLClassHierarchy:
    """Tests for OWL class hierarchy reasoning, including transitive subclass queries."""

    def test_get_parents(self, hierarchy: OWLClassHierarchy):
        """get_parents returns direct parent classes."""
        parents = hierarchy.get_parents("fizz:Fizz")
        assert "fizz:Number" in parents

    def test_get_children(self, hierarchy: OWLClassHierarchy):
        """get_children returns direct child classes."""
        children = hierarchy.get_children("fizz:Number")
        assert "fizz:Fizz" in children
        assert "fizz:Buzz" in children
        assert "fizz:Plain" in children

    def test_fizzbuzz_has_two_parents(self, hierarchy: OWLClassHierarchy):
        """fizz:FizzBuzz has two direct parents: fizz:Fizz and fizz:Buzz."""
        parents = hierarchy.get_parents("fizz:FizzBuzz")
        assert len(parents) == 2
        assert "fizz:Fizz" in parents
        assert "fizz:Buzz" in parents

    def test_get_ancestors_transitive(self, hierarchy: OWLClassHierarchy):
        """get_ancestors returns transitive closure: FizzBuzz -> Fizz, Buzz -> Number."""
        ancestors = hierarchy.get_ancestors("fizz:FizzBuzz")
        assert "fizz:Fizz" in ancestors
        assert "fizz:Buzz" in ancestors
        assert "fizz:Number" in ancestors

    def test_get_descendants(self, hierarchy: OWLClassHierarchy):
        """get_descendants returns all descendants transitively."""
        descendants = hierarchy.get_descendants("fizz:Number")
        assert "fizz:Fizz" in descendants
        assert "fizz:Buzz" in descendants
        assert "fizz:FizzBuzz" in descendants
        assert "fizz:Plain" in descendants

    def test_is_subclass_of_direct(self, hierarchy: OWLClassHierarchy):
        """is_subclass_of returns True for direct subclass relationships."""
        assert hierarchy.is_subclass_of("fizz:Fizz", "fizz:Number") is True

    def test_is_subclass_of_transitive(self, hierarchy: OWLClassHierarchy):
        """is_subclass_of returns True for transitive subclass relationships."""
        assert hierarchy.is_subclass_of("fizz:FizzBuzz", "fizz:Number") is True

    def test_is_subclass_of_self(self, hierarchy: OWLClassHierarchy):
        """A class is always a subclass of itself (reflexive property)."""
        assert hierarchy.is_subclass_of("fizz:Number", "fizz:Number") is True

    def test_is_subclass_of_false(self, hierarchy: OWLClassHierarchy):
        """is_subclass_of returns False when there is no subclass relationship."""
        assert hierarchy.is_subclass_of("fizz:Number", "fizz:FizzBuzz") is False

    def test_get_all_classes(self, hierarchy: OWLClassHierarchy):
        """get_all_classes returns all classes in the hierarchy."""
        classes = hierarchy.get_all_classes()
        assert "fizz:Number" in classes
        assert "fizz:Fizz" in classes
        assert "fizz:FizzBuzz" in classes

    def test_get_roots(self, hierarchy: OWLClassHierarchy):
        """get_roots returns classes with no parents in the hierarchy."""
        roots = hierarchy.get_roots()
        assert "fizz:Number" in roots

    def test_validate_consistency_no_errors(self, hierarchy: OWLClassHierarchy):
        """A well-formed hierarchy has no consistency errors."""
        errors = hierarchy.validate_consistency()
        assert errors == []


# ════════════════════════════════════════════════════════════════════
# Inference Engine Tests
# ════════════════════════════════════════════════════════════════════


class TestInferenceEngine:
    """Tests for the forward-chaining inference engine."""

    def test_engine_has_builtin_rules(self, engine: InferenceEngine):
        """The inference engine registers two built-in rules on creation."""
        assert len(engine.rules) == 2

    def test_engine_run_produces_inferred_triples(self, engine: InferenceEngine):
        """Running the engine produces new inferred triples."""
        inferred = engine.run()
        assert inferred > 0
        assert engine.triples_inferred > 0
        assert engine.iterations_run >= 1

    def test_engine_reaches_fixpoint(self, engine: InferenceEngine):
        """Running the engine twice produces the same result (fixpoint)."""
        first_run = engine.run()
        assert first_run > 0
        # Running again should not produce new triples
        engine2 = InferenceEngine(engine._store)
        second_run = engine2.run()
        assert second_run == 0

    def test_subclass_transitivity_inference(self, engine: InferenceEngine):
        """After inference, fizz:FizzBuzz rdfs:subClassOf fizz:Number is inferred."""
        engine.run()
        store = engine._store
        assert store.contains("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Number")

    def test_type_propagation_inference(self, engine: InferenceEngine):
        """After inference, Number_15 rdf:type fizz:Number is inferred (via FizzBuzz -> Fizz -> Number)."""
        engine.run()
        store = engine._store
        # Number_15 is typed as fizz:FizzBuzz, and FizzBuzz subClassOf Fizz subClassOf Number
        assert store.contains("fizz:Number_15", "rdf:type", "fizz:Number")

    def test_add_custom_rule(self, engine: InferenceEngine):
        """A custom inference rule can be added and is applied during run."""
        custom_triples = []

        def custom_rule(store: TripleStore) -> list[RDFTriple]:
            # Add a single triple: fizz:CustomFact rdf:type fizz:Fact
            t = RDFTriple(
                RDFNode.uri("fizz:CustomFact"),
                RDFNode.uri("rdf:type"),
                RDFNode.uri("fizz:Fact"),
            )
            if t not in store._triples:
                return [t]
            return []

        engine.add_rule(InferenceRule(
            name="custom_test_rule",
            apply=custom_rule,
            description="Adds a custom fact for testing",
        ))
        engine.run()
        assert engine._store.contains("fizz:CustomFact", "rdf:type", "fizz:Fact")

    def test_max_iterations_exceeded_raises(self):
        """An engine that cannot reach fixpoint raises InferenceFixpointError."""
        store = TripleStore()
        store.add_spo("fizz:A", "rdf:type", "fizz:B")
        engine = InferenceEngine(store, max_iterations=1)

        counter = [0]

        def infinite_rule(s: TripleStore) -> list[RDFTriple]:
            counter[0] += 1
            return [RDFTriple(
                RDFNode.uri(f"fizz:Gen_{counter[0]}"),
                RDFNode.uri("rdf:type"),
                RDFNode.uri("fizz:Generated"),
            )]

        # Remove builtin rules and add the infinite one
        engine._rules.clear()
        engine.add_rule(InferenceRule(name="infinite", apply=infinite_rule))

        with pytest.raises(InferenceFixpointError):
            engine.run()


# ════════════════════════════════════════════════════════════════════
# FizzSPARQL Parser Tests
# ════════════════════════════════════════════════════════════════════


class TestFizzSPARQLParser:
    """Tests for the FizzSPARQL query parser."""

    def test_parse_simple_select(self):
        """Parses a simple SELECT query with one variable and one pattern."""
        query = "SELECT ?x WHERE { ?x rdf:type fizz:Fizz }"
        parsed = FizzSPARQLParser(query).parse()
        assert parsed.variables == ["?x"]
        assert len(parsed.patterns) == 1
        assert parsed.patterns[0] == ("?x", "rdf:type", "fizz:Fizz")
        assert parsed.limit is None

    def test_parse_multiple_variables(self):
        """Parses a SELECT query with multiple variables."""
        query = "SELECT ?s ?o WHERE { ?s fizz:hasClassification ?o }"
        parsed = FizzSPARQLParser(query).parse()
        assert parsed.variables == ["?s", "?o"]

    def test_parse_multiple_patterns(self):
        """Parses a query with multiple triple patterns separated by dots."""
        query = "SELECT ?x WHERE { ?x rdf:type fizz:Number . ?x fizz:hasClassification fizz:Fizz }"
        parsed = FizzSPARQLParser(query).parse()
        assert len(parsed.patterns) == 2

    def test_parse_with_limit(self):
        """Parses a query with a LIMIT clause."""
        query = "SELECT ?x WHERE { ?x rdf:type fizz:Fizz } LIMIT 5"
        parsed = FizzSPARQLParser(query).parse()
        assert parsed.limit == 5

    def test_parse_missing_select_raises(self):
        """A query without SELECT raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("FIND ?x WHERE { ?x rdf:type fizz:Fizz }").parse()

    def test_parse_missing_where_raises(self):
        """A query without WHERE raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("SELECT ?x { ?x rdf:type fizz:Fizz }").parse()

    def test_parse_empty_pattern_raises(self):
        """A query with an empty WHERE clause raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("SELECT ?x WHERE { }").parse()

    def test_parse_no_variables_raises(self):
        """A SELECT with no variables raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("SELECT WHERE { fizz:A rdf:type fizz:B }").parse()


# ════════════════════════════════════════════════════════════════════
# FizzSPARQL Executor Tests
# ════════════════════════════════════════════════════════════════════


class TestFizzSPARQLExecutor:
    """Tests for FizzSPARQL query execution with variable binding."""

    def test_simple_type_query(self, populated_store: TripleStore):
        """SELECT all resources of type fizz:Fizz returns the correct numbers."""
        query = FizzSPARQLQuery(
            variables=["?x"],
            patterns=[("?x", "rdf:type", "fizz:Fizz")],
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        # Numbers 3, 6, 9, 12, 15 are Fizz-typed (3, 6, 9, 12 directly; 15 as FizzBuzz which is typed fizz:FizzBuzz not fizz:Fizz)
        fizz_numbers = {r["?x"] for r in results}
        assert "fizz:Number_3" in fizz_numbers
        assert "fizz:Number_6" in fizz_numbers

    def test_classification_query(self, populated_store: TripleStore):
        """SELECT classification for a specific number."""
        query = FizzSPARQLQuery(
            variables=["?class"],
            patterns=[("fizz:Number_15", "fizz:hasClassification", "?class")],
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        assert len(results) == 1
        assert results[0]["?class"] == "fizz:FizzBuzz"

    def test_two_pattern_join(self, populated_store: TripleStore):
        """A query with two patterns joins on shared variables."""
        query = FizzSPARQLQuery(
            variables=["?x"],
            patterns=[
                ("?x", "fizz:hasClassification", "fizz:Fizz"),
                ("?x", "fizz:isDivisibleBy", "fizz:Divisor_3"),
            ],
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        # All Fizz-classified numbers are divisible by 3
        assert len(results) > 0
        for r in results:
            assert "Number_" in r["?x"]

    def test_limit_applied(self, populated_store: TripleStore):
        """LIMIT restricts the number of results returned."""
        query = FizzSPARQLQuery(
            variables=["?x"],
            patterns=[("?x", "rdf:type", "fizz:Number")],
            limit=3,
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        assert len(results) == 3

    def test_execute_fizzsparql_convenience(self, populated_store: TripleStore):
        """execute_fizzsparql parses and executes a query string in one step."""
        results = execute_fizzsparql(
            populated_store,
            "SELECT ?x WHERE { ?x fizz:hasClassification fizz:Buzz } LIMIT 2",
        )
        assert len(results) <= 2
        assert all("?x" in r for r in results)


# ════════════════════════════════════════════════════════════════════
# Ontology Visualizer Tests
# ════════════════════════════════════════════════════════════════════


class TestOntologyVisualizer:
    """Tests for the ASCII class hierarchy renderer."""

    def test_render_contains_header(self, hierarchy: OWLClassHierarchy):
        """The rendered tree contains the OWL CLASS HIERARCHY header."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "OWL CLASS HIERARCHY" in output

    def test_render_contains_class_names(self, hierarchy: OWLClassHierarchy):
        """The rendered tree contains the class names from the hierarchy."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "fizz:Number" in output
        assert "fizz:Fizz" in output
        assert "fizz:FizzBuzz" in output

    def test_render_diamond_annotation(self, hierarchy: OWLClassHierarchy):
        """The rendered tree includes a diamond inheritance annotation."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "DIAMOND INHERITANCE DETECTED" in output

    def test_render_multiple_inheritance_marker(self, hierarchy: OWLClassHierarchy):
        """FizzBuzz node is annotated with 'multiple inheritance'."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "multiple inheritance" in output


# ════════════════════════════════════════════════════════════════════
# Knowledge Dashboard Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeDashboard:
    """Tests for the ASCII knowledge graph dashboard."""

    def test_render_contains_title(self, populated_store, hierarchy, engine):
        """The dashboard contains the main title."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "KNOWLEDGE GRAPH & DOMAIN ONTOLOGY DASHBOARD" in output

    def test_render_contains_triple_stats(self, populated_store, hierarchy, engine):
        """The dashboard contains triple store statistics."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "TRIPLE STORE STATISTICS" in output
        assert "Total Triples" in output

    def test_render_contains_inference_stats(self, populated_store, hierarchy, engine):
        """The dashboard contains inference engine statistics."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "INFERENCE ENGINE STATISTICS" in output

    def test_render_contains_namespaces(self, populated_store, hierarchy, engine):
        """The dashboard lists registered namespaces."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "REGISTERED NAMESPACES" in output
        assert "fizz:" in output

    def test_render_without_class_hierarchy(self, populated_store, hierarchy, engine):
        """The dashboard can be rendered without the class hierarchy section."""
        output = KnowledgeDashboard.render(
            populated_store, hierarchy, engine, show_class_hierarchy=False,
        )
        assert "KNOWLEDGE GRAPH & DOMAIN ONTOLOGY DASHBOARD" in output
        assert "OWL CLASS HIERARCHY" not in output

    def test_render_after_inference(self, populated_store, hierarchy, engine):
        """After running inference, the dashboard shows non-zero inferred stats."""
        engine.run()
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "FIXPOINT REACHED" in output


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph Middleware Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphMiddleware:
    """Tests for the middleware that annotates FizzBuzz results with KG data."""

    def test_middleware_name(self, populated_store, hierarchy):
        """The middleware identifies itself as KnowledgeGraphMiddleware."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        assert mw.get_name() == "KnowledgeGraphMiddleware"

    def test_middleware_priority(self, populated_store, hierarchy):
        """The middleware has priority 16."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        assert mw.get_priority() == 16

    def test_middleware_delegates_to_next(self, populated_store, hierarchy):
        """The middleware delegates to the next handler in the pipeline."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=3, session_id="test-session")

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            c.metadata["delegated"] = True
            return c

        result = mw.process(ctx, next_handler)
        assert result.metadata["delegated"] is True

    def test_middleware_adds_classification(self, populated_store, hierarchy):
        """The middleware adds kg_classification to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=3, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert "kg_classification" in result.metadata
        assert "fizz:Fizz" in result.metadata["kg_classification"]

    def test_middleware_adds_divisibility(self, populated_store, hierarchy):
        """The middleware adds kg_divisible_by to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=15, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert "kg_divisible_by" in result.metadata
        assert "fizz:Divisor_3" in result.metadata["kg_divisible_by"]
        assert "fizz:Divisor_5" in result.metadata["kg_divisible_by"]
        assert "fizz:Divisor_15" in result.metadata["kg_divisible_by"]

    def test_middleware_adds_type_memberships(self, populated_store, hierarchy):
        """The middleware adds kg_type_memberships to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=5, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert "kg_type_memberships" in result.metadata
        assert "fizz:Buzz" in result.metadata["kg_type_memberships"]

    def test_middleware_adds_triple_count(self, populated_store, hierarchy):
        """The middleware adds the total triple count to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=1, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert result.metadata["kg_triple_count"] == populated_store.size


# ════════════════════════════════════════════════════════════════════
# Exception Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphExceptions:
    """Tests for all Knowledge Graph exception classes."""

    def test_knowledge_graph_error_base(self):
        """KnowledgeGraphError is the base class with default error code."""
        err = KnowledgeGraphError("Something went wrong")
        assert "Something went wrong" in str(err)

    def test_invalid_triple_error(self):
        """InvalidTripleError reports the offending subject, predicate, object."""
        err = InvalidTripleError("s", "p", "")
        assert "Invalid RDF triple" in str(err)
        assert "EFP-KG01" in err.error_code

    def test_namespace_resolution_error(self):
        """NamespaceResolutionError reports the unknown prefix."""
        err = NamespaceResolutionError("bogus")
        assert "bogus" in str(err)
        assert "EFP-KG02" in err.error_code

    def test_fizzsparql_syntax_error(self):
        """FizzSPARQLSyntaxError reports the query, position, and reason."""
        err = FizzSPARQLSyntaxError("SELECT", 0, "missing variables")
        assert "FizzSPARQL syntax error" in str(err)
        assert "EFP-KG03" in err.error_code

    def test_inference_fixpoint_error(self):
        """InferenceFixpointError reports max iterations and triple count."""
        err = InferenceFixpointError(100, 9999)
        assert "fixpoint" in str(err).lower()
        assert "EFP-KG04" in err.error_code

    def test_ontology_consistency_error(self):
        """OntologyConsistencyError reports the class URI and reason."""
        err = OntologyConsistencyError("fizz:Loop", "circular inheritance")
        assert "fizz:Loop" in str(err)
        assert "EFP-KG05" in err.error_code


# ════════════════════════════════════════════════════════════════════
# EventType Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphEventTypes:
    """Tests for Knowledge Graph EventType enum entries."""

    def test_kg_triple_added_exists(self):
        """The KG_TRIPLE_ADDED event type exists."""
        assert EventType.KG_TRIPLE_ADDED is not None

    def test_kg_inference_started_exists(self):
        """The KG_INFERENCE_STARTED event type exists."""
        assert EventType.KG_INFERENCE_STARTED is not None

    def test_kg_inference_fixpoint_exists(self):
        """The KG_INFERENCE_FIXPOINT event type exists."""
        assert EventType.KG_INFERENCE_FIXPOINT is not None

    def test_kg_sparql_parsed_exists(self):
        """The KG_SPARQL_PARSED event type exists."""
        assert EventType.KG_SPARQL_PARSED is not None

    def test_kg_sparql_executed_exists(self):
        """The KG_SPARQL_EXECUTED event type exists."""
        assert EventType.KG_SPARQL_EXECUTED is not None

    def test_kg_ontology_rendered_exists(self):
        """The KG_ONTOLOGY_RENDERED event type exists."""
        assert EventType.KG_ONTOLOGY_RENDERED is not None
