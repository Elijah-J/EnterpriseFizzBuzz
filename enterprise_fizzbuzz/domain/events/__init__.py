"""Enterprise FizzBuzz Platform - Event Type Registry.

Event types are registered by subsystem modules at import time.
All registration files are loaded eagerly to maintain backward
compatibility: every EventType member that existed before the
split is available immediately after importing this package.

Import order is critical: it determines the auto-incrementing
integer values assigned to each event type, matching the original
Enum member ordering.
"""

from enterprise_fizzbuzz.domain.events._registry import (  # noqa: F401
    EventType,
    _EventValue,
)

# Registration files are imported in the same order as the original
# EventType Enum members appeared in models.py. This ensures that
# auto-incrementing integer values match the original auto() values.
import enterprise_fizzbuzz.domain.events._core  # noqa: F401
import enterprise_fizzbuzz.domain.events._event_sourcing  # noqa: F401
import enterprise_fizzbuzz.domain.events._chaos  # noqa: F401
import enterprise_fizzbuzz.domain.events._feature_flags  # noqa: F401
import enterprise_fizzbuzz.domain.events._sla  # noqa: F401
import enterprise_fizzbuzz.domain.events._anti_corruption  # noqa: F401
import enterprise_fizzbuzz.domain.events._cache  # noqa: F401
import enterprise_fizzbuzz.domain.events._repository  # noqa: F401
import enterprise_fizzbuzz.domain.events._migrations  # noqa: F401
import enterprise_fizzbuzz.domain.events._metrics  # noqa: F401
import enterprise_fizzbuzz.domain.events._webhooks  # noqa: F401
import enterprise_fizzbuzz.domain.events._health  # noqa: F401
import enterprise_fizzbuzz.domain.events._service_mesh  # noqa: F401
import enterprise_fizzbuzz.domain.events._ab_testing  # noqa: F401
import enterprise_fizzbuzz.domain.events._hot_reload  # noqa: F401
import enterprise_fizzbuzz.domain.events._message_queue  # noqa: F401
import enterprise_fizzbuzz.domain.events._rate_limiter  # noqa: F401
import enterprise_fizzbuzz.domain.events._compliance  # noqa: F401
import enterprise_fizzbuzz.domain.events._finops  # noqa: F401
import enterprise_fizzbuzz.domain.events._disaster_recovery  # noqa: F401
import enterprise_fizzbuzz.domain.events._secrets_vault  # noqa: F401
import enterprise_fizzbuzz.domain.events._openapi  # noqa: F401
import enterprise_fizzbuzz.domain.events._data_pipeline  # noqa: F401
import enterprise_fizzbuzz.domain.events._api_gateway  # noqa: F401
import enterprise_fizzbuzz.domain.events._graph_db  # noqa: F401
import enterprise_fizzbuzz.domain.events._genetic  # noqa: F401
import enterprise_fizzbuzz.domain.events._blue_green  # noqa: F401
import enterprise_fizzbuzz.domain.events._nlq  # noqa: F401
import enterprise_fizzbuzz.domain.events._load_testing  # noqa: F401
import enterprise_fizzbuzz.domain.events._audit  # noqa: F401
import enterprise_fizzbuzz.domain.events._gitops  # noqa: F401
import enterprise_fizzbuzz.domain.events._verification  # noqa: F401
import enterprise_fizzbuzz.domain.events._billing  # noqa: F401
import enterprise_fizzbuzz.domain.events._time_travel  # noqa: F401
import enterprise_fizzbuzz.domain.events._bytecode_vm  # noqa: F401
import enterprise_fizzbuzz.domain.events._query_optimizer  # noqa: F401
import enterprise_fizzbuzz.domain.events._paxos  # noqa: F401
import enterprise_fizzbuzz.domain.events._quantum  # noqa: F401
import enterprise_fizzbuzz.domain.events._cross_compiler  # noqa: F401
import enterprise_fizzbuzz.domain.events._federated  # noqa: F401
import enterprise_fizzbuzz.domain.events._knowledge_graph  # noqa: F401
import enterprise_fizzbuzz.domain.events._self_modifying  # noqa: F401
import enterprise_fizzbuzz.domain.events._fizzkube  # noqa: F401
import enterprise_fizzbuzz.domain.events._chatbot  # noqa: F401
import enterprise_fizzbuzz.domain.events._kernel  # noqa: F401
import enterprise_fizzbuzz.domain.events._p2p_network  # noqa: F401
import enterprise_fizzbuzz.domain.events._digital_twin  # noqa: F401
import enterprise_fizzbuzz.domain.events._dap  # noqa: F401
import enterprise_fizzbuzz.domain.events._ip_office  # noqa: F401
import enterprise_fizzbuzz.domain.events._distributed_locks  # noqa: F401
import enterprise_fizzbuzz.domain.events._misc  # noqa: F401
import enterprise_fizzbuzz.domain.events._containers  # noqa: F401
import enterprise_fizzbuzz.domain.events._fizzlife  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzmvcc  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzlambda  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzwasm  # noqa: F401
import enterprise_fizzbuzz.domain.events._fizzs3  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzstream  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzborrow  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzpolicy  # noqa: F401
import enterprise_fizzbuzz.domain.events.fizzadmit  # noqa: F401

__all__ = ["EventType", "_EventValue"]
