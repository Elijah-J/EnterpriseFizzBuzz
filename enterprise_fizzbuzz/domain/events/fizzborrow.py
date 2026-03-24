"""FizzBorrow ownership and borrow checker events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

# Ownership events
EventType.register("BORROW_OWNERSHIP_TRANSFERRED")
EventType.register("BORROW_VALUE_CLONED")
EventType.register("BORROW_VALUE_DROPPED")
EventType.register("BORROW_PARTIAL_MOVE")

# Borrow lifecycle events
EventType.register("BORROW_SHARED_CREATED")
EventType.register("BORROW_MUTABLE_CREATED")
EventType.register("BORROW_RELEASED")
EventType.register("BORROW_CONFLICT_DETECTED")
EventType.register("BORROW_REBORROW_CREATED")
EventType.register("BORROW_TWO_PHASE_RESERVED")
EventType.register("BORROW_TWO_PHASE_ACTIVATED")

# Lifetime events
EventType.register("BORROW_LIFETIME_CONSTRAINT_ADDED")
EventType.register("BORROW_REGION_SOLVED")
EventType.register("BORROW_ELISION_APPLIED")

# Analysis events
EventType.register("BORROW_MIR_BUILT")
EventType.register("BORROW_NLL_COMPLETED")
EventType.register("BORROW_CHECK_PASSED")
EventType.register("BORROW_CHECK_FAILED")
EventType.register("BORROW_DROP_CHECK_COMPLETED")
EventType.register("BORROW_VARIANCE_COMPUTED")

# Dashboard events
EventType.register("BORROW_DASHBOARD_RENDERED")
EventType.register("BORROW_MIR_DUMPED")
