"""Feature descriptor for the Knowledge Graph & Domain Ontology subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class OntologyFeature(FeatureDescriptor):
    name = "ontology"
    description = "Knowledge Graph and Domain Ontology with RDF triples, OWL class hierarchy, and FizzSPARQL queries"
    middleware_priority = 125
    cli_flags = [
        ("--ontology", {"action": "store_true", "default": False,
                        "help": "Enable the Knowledge Graph & Domain Ontology: model FizzBuzz as RDF triples with OWL class hierarchy"}),
        ("--sparql", {"type": str, "metavar": "QUERY", "default": None,
                      "help": 'Execute a FizzSPARQL query (e.g. --sparql "SELECT ?n WHERE { ?n fizz:hasClassification fizz:Fizz } LIMIT 10")'}),
        ("--ontology-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the Knowledge Graph & Domain Ontology ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "ontology", False),
            bool(getattr(args, "sparql", None)),
            getattr(args, "ontology_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        # SPARQL-only mode: execute query and exit before pipeline
        sparql = getattr(args, "sparql", None)
        ontology = getattr(args, "ontology", False)
        return bool(sparql) and not ontology

    def run_early_exit(self, args: Any, config: Any) -> int:
        """Execute a standalone FizzSPARQL query and exit."""
        from enterprise_fizzbuzz.infrastructure.graph_db import (
            TripleStore,
            execute_fizzsparql,
            populate_fizzbuzz_domain,
        )

        kg_store = TripleStore()
        populate_fizzbuzz_domain(
            kg_store,
            range_start=config.knowledge_graph_domain_range_start,
            range_end=config.knowledge_graph_domain_range_end,
        )

        try:
            results = execute_fizzsparql(kg_store, args.sparql)
            print()
            print("  FizzSPARQL Query Results:")
            print("  " + "-" * 56)
            if not results:
                print("  (no results)")
            else:
                headers = list(results[0].keys())
                header_line = "  " + "  ".join(f"{h:<20}" for h in headers)
                print(header_line)
                print("  " + "-" * 56)
                for row in results:
                    vals = [f"{v:<20}" for v in row.values()]
                    print("  " + "  ".join(vals))
            print("  " + "-" * 56)
            print(f"  {len(results)} result(s)")
            print()
        except Exception as e:
            print(f"\n  FizzSPARQL Error: {e}\n")
            return 1
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.graph_db import (
            InferenceEngine,
            KnowledgeGraphMiddleware,
            OWLClassHierarchy,
            OntologyVisualizer,
            TripleStore,
            execute_fizzsparql,
            populate_fizzbuzz_domain,
        )

        kg_store = TripleStore()
        triple_count = populate_fizzbuzz_domain(
            kg_store,
            range_start=config.knowledge_graph_domain_range_start,
            range_end=config.knowledge_graph_domain_range_end,
        )

        kg_hierarchy = OWLClassHierarchy(kg_store)
        kg_engine = InferenceEngine(
            kg_store,
            max_iterations=config.knowledge_graph_max_inference_iterations,
        )

        # Run forward-chaining inference to fixpoint
        inferred = kg_engine.run()

        # Rebuild hierarchy after inference (new subclass triples may exist)
        kg_hierarchy = OWLClassHierarchy(kg_store)

        kg_middleware = KnowledgeGraphMiddleware(
            store=kg_store,
            hierarchy=kg_hierarchy,
            event_bus=event_bus,
        )

        print(
            "  +---------------------------------------------------------+\n"
            "  | KNOWLEDGE GRAPH: Semantic Web for FizzBuzz ENABLED      |\n"
            f"  | Triples: {kg_store.size:<47}|\n"
            f"  | Inferred: {inferred:<46}|\n"
            f"  | Classes: {len(kg_hierarchy.get_all_classes()):<47}|\n"
            "  | Every integer is now an RDF resource with formal class  |\n"
            "  | membership, divisibility properties, and an OWL class   |\n"
            "  | hierarchy featuring diamond inheritance. Linked Data!   |\n"
            "  +---------------------------------------------------------+"
        )

        # Show class hierarchy if visualization is enabled
        if config.knowledge_graph_enable_visualization:
            print()
            print(OntologyVisualizer.render_class_tree(
                kg_hierarchy, width=config.knowledge_graph_dashboard_width
            ))

        # Execute inline SPARQL query if provided alongside --ontology
        sparql = getattr(args, "sparql", None)
        if sparql:
            try:
                results = execute_fizzsparql(kg_store, sparql)
                print()
                print("  FizzSPARQL Query Results:")
                print("  " + "-" * 56)
                if not results:
                    print("  (no results)")
                else:
                    headers = list(results[0].keys())
                    header_line = "  " + "  ".join(f"{h:<20}" for h in headers)
                    print(header_line)
                    print("  " + "-" * 56)
                    for row in results:
                        vals = [f"{v:<20}" for v in row.values()]
                        print("  " + "  ".join(vals))
                print("  " + "-" * 56)
                print(f"  {len(results)} result(s)")
                print()
            except Exception as e:
                print(f"\n  FizzSPARQL Error: {e}\n")

        # Store references for dashboard rendering
        self._kg_store = kg_store
        self._kg_hierarchy = kg_hierarchy
        self._kg_engine = kg_engine

        return kg_store, kg_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "ontology_dashboard", False):
            return None

        kg_store = getattr(self, "_kg_store", None)
        if kg_store is None:
            return "\n  Knowledge Graph not enabled. Use --ontology to enable.\n"

        from enterprise_fizzbuzz.infrastructure.graph_db import KnowledgeDashboard

        kg_hierarchy = getattr(self, "_kg_hierarchy", None)
        kg_engine = getattr(self, "_kg_engine", None)
        config_width = 60

        return KnowledgeDashboard.render(
            kg_store,
            kg_hierarchy,
            kg_engine,
            width=config_width,
            show_class_hierarchy=True,
            show_triple_stats=True,
            show_inference_stats=True,
        )
