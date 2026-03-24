"""Fizzimage configuration properties."""

from __future__ import annotations

from typing import Any


class FizzimageConfigMixin:
    """Configuration properties for the fizzimage subsystem."""

    @property
    def fizzimage_enabled(self) -> bool:
        """Whether the FizzImage container image catalog is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("enabled", False)

    @property
    def fizzimage_base_image_name(self) -> str:
        """Name of the base image in the catalog."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("base_image_name", "fizzbuzz-base")

    @property
    def fizzimage_registry_url(self) -> str:
        """Registry URL for image push/pull operations."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("registry_url", "registry.fizzbuzz.internal:5000")

    @property
    def fizzimage_scan_severity_threshold(self) -> str:
        """Maximum vulnerability severity that blocks image admission."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("scan_severity_threshold", "critical")

    @property
    def fizzimage_max_catalog_size(self) -> int:
        """Maximum number of images in the catalog."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzimage", {}).get("max_catalog_size", 1024))

    @property
    def fizzimage_python_version(self) -> str:
        """Python version installed in the base image."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("python_version", "3.12")

    @property
    def fizzimage_initial_version(self) -> str:
        """Initial semantic version for new images."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("initial_version", "1.0.0")

    @property
    def fizzimage_vuln_db_size(self) -> int:
        """Number of entries in the simulated vulnerability database."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzimage", {}).get("vuln_db_size", 512))

    @property
    def fizzimage_module_base_path(self) -> str:
        """Base Python package path for infrastructure modules."""
        self._ensure_loaded()
        return self._raw_config.get("fizzimage", {}).get("module_base_path", "enterprise_fizzbuzz.infrastructure")

    @property
    def fizzimage_dashboard_width(self) -> int:
        """Width of the FizzImage ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzimage", {}).get("dashboard", {}).get("width", 72))

