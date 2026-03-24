"""FizzWASM events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("WASM_MODULE_DECODED")
EventType.register("WASM_MODULE_VALIDATED")
EventType.register("WASM_MODULE_INSTANTIATED")
EventType.register("WASM_EXECUTION_STARTED")
EventType.register("WASM_EXECUTION_COMPLETED")
EventType.register("WASM_EXECUTION_TRAPPED")
EventType.register("WASM_FUEL_EXHAUSTED")
EventType.register("WASM_MEMORY_GROWN")
EventType.register("WASM_WASI_CALL")
EventType.register("WASM_WASI_DENIED")
EventType.register("WASM_IMPORT_RESOLVED")
EventType.register("WASM_EXPORT_CALLED")
EventType.register("WASM_COMPONENT_INSTANTIATED")
EventType.register("WASM_COMPONENT_CALL")
