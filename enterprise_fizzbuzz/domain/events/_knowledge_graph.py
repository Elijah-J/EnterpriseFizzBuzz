"""Knowledge Graph and Domain Ontology events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("KG_TRIPLE_ADDED")
EventType.register("KG_INFERENCE_STARTED")
EventType.register("KG_INFERENCE_FIXPOINT")
EventType.register("KG_SPARQL_PARSED")
EventType.register("KG_SPARQL_EXECUTED")
EventType.register("KG_ONTOLOGY_RENDERED")
