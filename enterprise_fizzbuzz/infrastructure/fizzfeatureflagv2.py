"""
Enterprise FizzBuzz Platform - FizzFeatureFlagV2: Feature Flags V2

Gradual rollout with consistent hashing, A/B testing, audience targeting.

Architecture reference: LaunchDarkly, Split.io, Unleash, Flagsmith.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzfeatureflagv2 import (
    FizzFeatureFlagV2Error, FizzFeatureFlagV2NotFoundError,
    FizzFeatureFlagV2EvaluationError, FizzFeatureFlagV2TargetingError,
    FizzFeatureFlagV2ABTestError, FizzFeatureFlagV2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzfeatureflagv2")

EVENT_FF_EVALUATED = EventType.register("FIZZFEATUREFLAGV2_EVALUATED")

FIZZFEATUREFLAGV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 176


class FlagState(Enum):
    ON = "on"
    OFF = "off"
    PERCENTAGE = "percentage"
    TARGETED = "targeted"

class VariantType(Enum):
    BOOLEAN = "boolean"
    STRING = "string"
    NUMBER = "number"
    JSON = "json"


@dataclass
class FizzFeatureFlagV2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class FeatureFlag:
    flag_id: str = ""
    name: str = ""
    state: FlagState = FlagState.OFF
    default_value: Any = True
    variants: Dict[str, Any] = field(default_factory=dict)
    rollout_percentage: float = 0.0
    targeting_rules: List[Dict[str, Any]] = field(default_factory=list)
    description: str = ""

@dataclass
class EvaluationContext:
    user_id: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EvaluationResult:
    flag_name: str = ""
    value: Any = None
    variant: str = ""
    reason: str = ""


class FlagStore:
    """Feature flag storage with CRUD operations."""

    def __init__(self) -> None:
        self._flags: OrderedDict[str, FeatureFlag] = OrderedDict()

    def create(self, flag: FeatureFlag) -> FeatureFlag:
        if not flag.flag_id:
            flag.flag_id = f"ff-{uuid.uuid4().hex[:8]}"
        self._flags[flag.name] = flag
        return flag

    def get(self, name: str) -> FeatureFlag:
        flag = self._flags.get(name)
        if flag is None:
            raise FizzFeatureFlagV2NotFoundError(name)
        return flag

    def update(self, name: str, **kwargs: Any) -> FeatureFlag:
        flag = self.get(name)
        for k, v in kwargs.items():
            if hasattr(flag, k):
                setattr(flag, k, v)
        return flag

    def delete(self, name: str) -> bool:
        return self._flags.pop(name, None) is not None

    def list_flags(self) -> List[FeatureFlag]:
        return list(self._flags.values())


class FlagEvaluator:
    """Evaluates feature flags against context."""

    def __init__(self, store: FlagStore) -> None:
        self._store = store

    def evaluate(self, flag_name: str, context: EvaluationContext) -> EvaluationResult:
        flag = self._store.get(flag_name)

        if flag.state == FlagState.ON:
            return EvaluationResult(flag_name=flag_name, value=flag.default_value,
                                    variant="default", reason="flag_on")

        if flag.state == FlagState.OFF:
            off_value = flag.variants.get("off", False)
            return EvaluationResult(flag_name=flag_name, value=off_value,
                                    variant="off", reason="flag_off")

        if flag.state == FlagState.PERCENTAGE:
            # Consistent hashing based on user_id + flag_name
            hash_input = f"{flag_name}:{context.user_id}"
            hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16) % 100
            if hash_val < flag.rollout_percentage:
                # In rollout: return enabled variant or True
                enabled_value = flag.variants.get("enabled", flag.variants.get("on", True))
                return EvaluationResult(flag_name=flag_name, value=enabled_value,
                                        variant="enabled", reason="percentage_in")
            else:
                # Out of rollout: return disabled variant or default
                disabled_value = flag.variants.get("disabled", flag.variants.get("off", flag.default_value))
                return EvaluationResult(flag_name=flag_name, value=disabled_value,
                                        variant="disabled", reason="percentage_out")

        if flag.state == FlagState.TARGETED:
            for rule in flag.targeting_rules:
                attr_name = rule.get("attribute", "")
                operator = rule.get("operator", "==")
                target_value = rule.get("value")
                user_value = context.attributes.get(attr_name)

                match = False
                if operator in ("==", "eq", "equals") and user_value == target_value:
                    match = True
                elif operator in ("in", "contains") and user_value in (target_value if isinstance(target_value, (list, set)) else [target_value]):
                    match = True
                elif operator in ("!=", "ne", "not_equals") and user_value != target_value:
                    match = True

                if match:
                    variant_name = rule.get("variant", "on")
                    value = flag.variants.get(variant_name, flag.default_value)
                    return EvaluationResult(flag_name=flag_name, value=value,
                                            variant=variant_name, reason="targeting_match")

            # No rule matched -- fall through to off
            off_value = flag.variants.get("off", False)
            return EvaluationResult(flag_name=flag_name, value=off_value,
                                    variant="default", reason="targeting_no_match")

        return EvaluationResult(flag_name=flag_name, value=flag.default_value,
                                variant="default", reason="unknown_state")


class ABTestManager:
    """A/B test experiment management."""

    def __init__(self, store: Optional[Any] = None, evaluator: Optional[Any] = None) -> None:
        self._store = store
        self._evaluator = evaluator
        self._experiments: Dict[str, Dict[str, Any]] = {}
        self._conversions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def create_experiment(self, name: str, flag_name: str,
                          variants: List[str], traffic_split: Dict[str, float]) -> Dict[str, Any]:
        experiment = {
            "name": name,
            "flag_name": flag_name,
            "variants": variants,
            "traffic_split": traffic_split,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._experiments[name] = experiment
        return experiment

    def record_conversion(self, experiment_name: str, variant: str, user_id: str) -> None:
        self._conversions[experiment_name].append({
            "variant": variant,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_results(self, name: str) -> Dict[str, Any]:
        experiment = self._experiments.get(name, {})
        conversions = self._conversions.get(name, [])
        variant_counts: Dict[str, int] = defaultdict(int)
        for c in conversions:
            variant_counts[c["variant"]] += 1
        return {
            "experiment": name,
            "total_conversions": len(conversions),
            "variant_conversions": dict(variant_counts),
            "variants": experiment.get("variants", []),
            "traffic_split": experiment.get("traffic_split", {}),
        }


class FizzFeatureFlagV2Dashboard:
    def __init__(self, store: Optional[FlagStore] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width,
                 "FizzFeatureFlagV2 Dashboard".center(self._width),
                 "=" * self._width,
                 f"  Version: {FIZZFEATUREFLAGV2_VERSION}"]
        if self._store:
            flags = self._store.list_flags()
            lines.append(f"  Flags: {len(flags)}")
            for f in flags:
                lines.append(f"  {f.name:<25} {f.state.value:<12} rollout={f.rollout_percentage}%")
        return "\n".join(lines)


class FizzFeatureFlagV2Middleware(IMiddleware):
    def __init__(self, store: Optional[FlagStore] = None,
                 evaluator: Optional[FlagEvaluator] = None,
                 dashboard: Optional[FizzFeatureFlagV2Dashboard] = None) -> None:
        self._store = store
        self._evaluator = evaluator
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzfeatureflagv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzfeatureflagv2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[FlagStore, FlagEvaluator, FizzFeatureFlagV2Dashboard, FizzFeatureFlagV2Middleware]:
    store = FlagStore()
    evaluator = FlagEvaluator(store)

    # Default flags
    store.create(FeatureFlag(
        name="fizzbuzz.new_algorithm", state=FlagState.PERCENTAGE,
        default_value=True, rollout_percentage=50.0,
        variants={"off": False},
        description="Gradual rollout of new FizzBuzz evaluation algorithm",
    ))
    store.create(FeatureFlag(
        name="fizzbuzz.dark_mode", state=FlagState.TARGETED,
        default_value=True,
        targeting_rules=[{"attribute": "tier", "operator": "==", "value": "premium", "variant": "treatment"}],
        variants={"treatment": True, "off": False},
        description="Dark mode for premium users",
    ))
    store.create(FeatureFlag(
        name="fizzbuzz.enhanced_logging", state=FlagState.ON,
        default_value=True,
        description="Enhanced logging for all evaluations",
    ))

    dashboard = FizzFeatureFlagV2Dashboard(store, dashboard_width)
    middleware = FizzFeatureFlagV2Middleware(store, evaluator, dashboard)

    logger.info("FizzFeatureFlagV2 initialized: %d flags", len(store.list_flags()))
    return store, evaluator, dashboard, middleware
