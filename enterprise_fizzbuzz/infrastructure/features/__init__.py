"""
Enterprise FizzBuzz Platform - Feature Registry Package

Auto-discovery plugin system for self-registering feature descriptors.
Each feature declares its CLI flags, initialization logic, and rendering
in a FeatureDescriptor subclass. The FeatureRegistry discovers all
descriptors and drives the platform lifecycle.
"""

from enterprise_fizzbuzz.infrastructure.features._registry import (
    FeatureDescriptor,
    FeatureRegistry,
)

__all__ = [
    "FeatureDescriptor",
    "FeatureRegistry",
]
