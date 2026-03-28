"""
Enterprise FizzBuzz Platform - FizzEFI UEFI Firmware Interface

Implements a UEFI firmware interface with boot services, runtime services,
variable store, boot manager, driver loading, and secure boot chain
verification for trusted FizzBuzz platform initialization.

The Unified Extensible Firmware Interface (UEFI) is the standard firmware
layer between FizzBuzz platform hardware and the operating system. The
FizzEFI subsystem models the UEFI 2.10 specification:

    UEFIFirmware
        ├── BootServices          (memory allocation, protocol handling, events)
        │     ├── AllocatePages   (page-granularity memory allocation)
        │     ├── LocateProtocol  (protocol interface discovery)
        │     └── CreateEvent     (timer/signal event management)
        ├── RuntimeServices       (variable access, time, reset)
        │     ├── GetVariable     (NVRAM variable read)
        │     ├── SetVariable     (NVRAM variable write)
        │     └── GetTime         (real-time clock)
        ├── VariableStore         (non-volatile variable persistence)
        ├── BootManager           (boot option enumeration, selection)
        ├── DriverLoader          (PE/COFF image loading, binding)
        └── SecureBootValidator   (signature database, chain verification)

The FizzBuzz classification engine is loaded as a UEFI application
during the boot services phase, enabling firmware-level FizzBuzz
computation before the operating system takes control.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZEFI_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 246

MAX_VARIABLES = 256
MAX_VARIABLE_SIZE = 4096
MAX_BOOT_OPTIONS = 64
MAX_DRIVERS = 128
MAX_PROTOCOLS = 256
MAX_MEMORY_PAGES = 1048576  # 4GB at 4KB/page

# UEFI Status Codes
EFI_SUCCESS = 0x0000000000000000
EFI_INVALID_PARAMETER = 0x8000000000000002
EFI_NOT_FOUND = 0x800000000000000E
EFI_BUFFER_TOO_SMALL = 0x8000000000000005
EFI_OUT_OF_RESOURCES = 0x8000000000000009
EFI_SECURITY_VIOLATION = 0x800000000000001A


# ============================================================================
# Enums
# ============================================================================

class EFIMemoryType(Enum):
    """UEFI memory type allocations."""
    RESERVED = 0
    LOADER_CODE = 1
    LOADER_DATA = 2
    BOOT_SERVICES_CODE = 3
    BOOT_SERVICES_DATA = 4
    RUNTIME_SERVICES_CODE = 5
    RUNTIME_SERVICES_DATA = 6
    CONVENTIONAL = 7
    ACPI_RECLAIM = 9
    ACPI_NVS = 10


class EFIVariableAttribute(Enum):
    """UEFI variable storage attributes."""
    NON_VOLATILE = 0x01
    BOOT_SERVICE_ACCESS = 0x02
    RUNTIME_ACCESS = 0x04
    AUTHENTICATED = 0x10


class BootPhase(Enum):
    """UEFI boot phases."""
    SEC = "Security"
    PEI = "Pre-EFI Initialization"
    DXE = "Driver Execution Environment"
    BDS = "Boot Device Selection"
    TSL = "Transient System Load"
    RT = "Runtime"


class SecureBootState(Enum):
    """Secure boot operational states."""
    SETUP_MODE = "SetupMode"
    USER_MODE = "UserMode"
    AUDIT_MODE = "AuditMode"
    DEPLOYED_MODE = "DeployedMode"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class EFIVariable:
    """UEFI NVRAM variable."""
    name: str
    guid: str
    attributes: int
    data: bytes
    timestamp: float = 0.0


@dataclass
class EFIBootOption:
    """UEFI boot option entry."""
    option_number: int
    description: str
    device_path: str
    active: bool = True
    load_count: int = 0


@dataclass
class EFIDriver:
    """UEFI driver image."""
    name: str
    guid: str
    image_hash: str
    loaded: bool = False
    bound: bool = False
    version: str = "1.0"


@dataclass
class EFIProtocol:
    """UEFI protocol interface."""
    guid: str
    name: str
    handle: int
    interface: Any = None


@dataclass
class MemoryPage:
    """UEFI memory page allocation."""
    base_address: int
    num_pages: int
    memory_type: EFIMemoryType


# ============================================================================
# Variable Store
# ============================================================================

class VariableStore:
    """UEFI non-volatile variable store.

    The variable store persists configuration and state across reboots.
    Variables are identified by a (name, GUID) tuple and can have
    access attributes controlling when they are readable/writable.
    """

    def __init__(self, max_variables: int = MAX_VARIABLES) -> None:
        self._variables: dict[tuple[str, str], EFIVariable] = {}
        self._max_variables = max_variables

    def get_variable(self, name: str, guid: str) -> EFIVariable:
        """Read a variable from the store."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIVariableError

        key = (name, guid)
        if key not in self._variables:
            raise EFIVariableError(name, "variable not found")
        return self._variables[key]

    def set_variable(
        self, name: str, guid: str, data: bytes, attributes: int = 0x07,
    ) -> None:
        """Write a variable to the store."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIVariableError

        if len(data) > MAX_VARIABLE_SIZE:
            raise EFIVariableError(
                name, f"data exceeds maximum size ({len(data)} > {MAX_VARIABLE_SIZE})",
            )

        key = (name, guid)
        if key not in self._variables and len(self._variables) >= self._max_variables:
            raise EFIVariableError(name, "variable store capacity exceeded")

        self._variables[key] = EFIVariable(
            name=name,
            guid=guid,
            attributes=attributes,
            data=data,
            timestamp=time.monotonic(),
        )

    def delete_variable(self, name: str, guid: str) -> None:
        """Delete a variable from the store."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIVariableError

        key = (name, guid)
        if key not in self._variables:
            raise EFIVariableError(name, "variable not found")
        del self._variables[key]

    @property
    def variable_count(self) -> int:
        return len(self._variables)

    def list_variables(self) -> list[tuple[str, str]]:
        return list(self._variables.keys())


# ============================================================================
# Boot Services
# ============================================================================

class BootServices:
    """UEFI Boot Services table.

    Boot services are available only during the boot phase and are
    terminated when ExitBootServices() is called. They provide
    memory allocation, protocol management, and event services.
    """

    def __init__(self) -> None:
        self._protocols: dict[str, EFIProtocol] = {}
        self._memory_map: list[MemoryPage] = []
        self._next_handle = 1
        self._pages_allocated = 0
        self._exited = False

    def allocate_pages(
        self, memory_type: EFIMemoryType, num_pages: int,
    ) -> MemoryPage:
        """Allocate pages of physical memory."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIBootServiceError

        if self._exited:
            raise EFIBootServiceError("AllocatePages", EFI_INVALID_PARAMETER)

        if self._pages_allocated + num_pages > MAX_MEMORY_PAGES:
            raise EFIBootServiceError("AllocatePages", EFI_OUT_OF_RESOURCES)

        base = self._pages_allocated * 4096
        page = MemoryPage(
            base_address=base,
            num_pages=num_pages,
            memory_type=memory_type,
        )
        self._memory_map.append(page)
        self._pages_allocated += num_pages
        return page

    def install_protocol(self, guid: str, name: str, interface: Any = None) -> int:
        """Install a protocol interface."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIProtocolError

        if self._exited:
            raise EFIProtocolError(guid, "boot services have exited")

        if guid in self._protocols:
            raise EFIProtocolError(guid, "protocol already installed")

        handle = self._next_handle
        self._next_handle += 1

        self._protocols[guid] = EFIProtocol(
            guid=guid, name=name, handle=handle, interface=interface,
        )
        return handle

    def locate_protocol(self, guid: str) -> EFIProtocol:
        """Locate a protocol interface by GUID."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIProtocolError

        if guid not in self._protocols:
            raise EFIProtocolError(guid, "protocol not found")
        return self._protocols[guid]

    def exit_boot_services(self) -> None:
        """Terminate boot services."""
        self._exited = True
        logger.info("UEFI Boot Services exited")

    @property
    def is_active(self) -> bool:
        return not self._exited

    @property
    def protocol_count(self) -> int:
        return len(self._protocols)

    @property
    def pages_allocated(self) -> int:
        return self._pages_allocated


# ============================================================================
# Runtime Services
# ============================================================================

class RuntimeServices:
    """UEFI Runtime Services table.

    Runtime services persist after ExitBootServices() and are
    available to the operating system for variable access, time
    services, and system reset.
    """

    def __init__(self, variable_store: VariableStore) -> None:
        self._variable_store = variable_store
        self._boot_time = time.monotonic()

    def get_variable(self, name: str, guid: str) -> bytes:
        """Read a runtime variable."""
        var = self._variable_store.get_variable(name, guid)
        return var.data

    def set_variable(self, name: str, guid: str, data: bytes, attributes: int = 0x07) -> None:
        """Write a runtime variable."""
        self._variable_store.set_variable(name, guid, data, attributes)

    def get_time(self) -> dict:
        """Return the current EFI time."""
        elapsed = time.monotonic() - self._boot_time
        return {
            "elapsed_seconds": elapsed,
            "timestamp": time.monotonic(),
        }

    def reset_system(self) -> str:
        """Perform a system reset."""
        logger.info("UEFI system reset requested")
        return "reset_cold"


# ============================================================================
# Boot Manager
# ============================================================================

class BootManager:
    """UEFI Boot Manager for boot option selection."""

    def __init__(self) -> None:
        self._options: dict[int, EFIBootOption] = {}
        self._boot_order: list[int] = []

    def add_option(self, description: str, device_path: str) -> int:
        """Add a boot option."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIBootManagerError

        if len(self._options) >= MAX_BOOT_OPTIONS:
            raise EFIBootManagerError(description, "maximum boot options reached")

        option_num = len(self._options)
        self._options[option_num] = EFIBootOption(
            option_number=option_num,
            description=description,
            device_path=device_path,
        )
        self._boot_order.append(option_num)
        return option_num

    def select_option(self, option_number: int) -> EFIBootOption:
        """Select and activate a boot option."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIBootManagerError

        if option_number not in self._options:
            raise EFIBootManagerError(
                str(option_number), "boot option not found",
            )

        option = self._options[option_number]
        option.load_count += 1
        return option

    @property
    def option_count(self) -> int:
        return len(self._options)

    @property
    def boot_order(self) -> list[int]:
        return list(self._boot_order)


# ============================================================================
# Driver Loader
# ============================================================================

class DriverLoader:
    """UEFI driver image loader and binding manager."""

    def __init__(self) -> None:
        self._drivers: dict[str, EFIDriver] = {}

    def load_driver(self, name: str, image_data: bytes) -> EFIDriver:
        """Load a UEFI driver image."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIDriverLoadError

        if name in self._drivers:
            raise EFIDriverLoadError(name, "driver already loaded")

        if len(self._drivers) >= MAX_DRIVERS:
            raise EFIDriverLoadError(name, "maximum drivers reached")

        image_hash = hashlib.sha256(image_data).hexdigest()
        driver_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

        driver = EFIDriver(
            name=name,
            guid=driver_guid,
            image_hash=image_hash,
            loaded=True,
        )
        self._drivers[name] = driver
        logger.debug("UEFI driver loaded: %s", name)
        return driver

    def bind_driver(self, name: str) -> None:
        """Bind a loaded driver to its protocol."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIDriverLoadError

        if name not in self._drivers:
            raise EFIDriverLoadError(name, "driver not loaded")

        driver = self._drivers[name]
        if driver.bound:
            raise EFIDriverLoadError(name, "driver already bound")

        driver.bound = True

    @property
    def driver_count(self) -> int:
        return len(self._drivers)

    def get_driver(self, name: str) -> EFIDriver:
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFIDriverLoadError
        if name not in self._drivers:
            raise EFIDriverLoadError(name, "driver not loaded")
        return self._drivers[name]


# ============================================================================
# Secure Boot Validator
# ============================================================================

class SecureBootValidator:
    """UEFI Secure Boot chain verification.

    Validates image signatures against the authorized signature
    database (db) and checks that images are not in the forbidden
    signature database (dbx).
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._state = SecureBootState.USER_MODE if enabled else SecureBootState.SETUP_MODE
        self._authorized_hashes: set[str] = set()
        self._forbidden_hashes: set[str] = set()

    def add_authorized_hash(self, image_hash: str) -> None:
        """Add a hash to the authorized signature database (db)."""
        self._authorized_hashes.add(image_hash)

    def add_forbidden_hash(self, image_hash: str) -> None:
        """Add a hash to the forbidden signature database (dbx)."""
        self._forbidden_hashes.add(image_hash)

    def verify_image(self, image_name: str, image_data: bytes) -> bool:
        """Verify an image against the secure boot databases."""
        from enterprise_fizzbuzz.domain.exceptions.fizzefi import EFISecureBootError

        if not self._enabled:
            return True

        image_hash = hashlib.sha256(image_data).hexdigest()

        if image_hash in self._forbidden_hashes:
            raise EFISecureBootError(
                image_name, "image hash found in forbidden database (dbx)",
            )

        if not self._authorized_hashes:
            # If no authorized hashes configured, allow all non-forbidden
            return True

        if image_hash not in self._authorized_hashes:
            raise EFISecureBootError(
                image_name, "image hash not found in authorized database (db)",
            )

        return True

    @property
    def state(self) -> SecureBootState:
        return self._state

    @property
    def is_enabled(self) -> bool:
        return self._enabled


# ============================================================================
# UEFI Firmware
# ============================================================================

class UEFIFirmware:
    """Top-level UEFI firmware object aggregating all services."""

    def __init__(self, secure_boot: bool = True) -> None:
        self.variable_store = VariableStore()
        self.boot_services = BootServices()
        self.runtime_services = RuntimeServices(self.variable_store)
        self.boot_manager = BootManager()
        self.driver_loader = DriverLoader()
        self.secure_boot = SecureBootValidator(enabled=secure_boot)
        self._phase = BootPhase.SEC

    def advance_phase(self) -> BootPhase:
        """Advance to the next boot phase."""
        phase_order = [
            BootPhase.SEC, BootPhase.PEI, BootPhase.DXE,
            BootPhase.BDS, BootPhase.TSL, BootPhase.RT,
        ]
        idx = phase_order.index(self._phase)
        if idx + 1 < len(phase_order):
            self._phase = phase_order[idx + 1]
        return self._phase

    @property
    def phase(self) -> BootPhase:
        return self._phase

    def get_stats(self) -> dict:
        return {
            "version": FIZZEFI_VERSION,
            "phase": self._phase.value,
            "variables": self.variable_store.variable_count,
            "protocols": self.boot_services.protocol_count,
            "pages_allocated": self.boot_services.pages_allocated,
            "boot_options": self.boot_manager.option_count,
            "drivers": self.driver_loader.driver_count,
            "secure_boot": self.secure_boot.is_enabled,
            "secure_boot_state": self.secure_boot.state.value,
        }


# ============================================================================
# Dashboard
# ============================================================================

class EFIDashboard:
    """ASCII dashboard for UEFI firmware visualization."""

    @staticmethod
    def render(firmware: UEFIFirmware, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzEFI UEFI Firmware Interface Dashboard".center(width))
        lines.append(border)

        stats = firmware.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Boot phase: {stats['phase']}")
        lines.append(f"  Variables: {stats['variables']}")
        lines.append(f"  Protocols: {stats['protocols']}")
        lines.append(f"  Pages allocated: {stats['pages_allocated']}")
        lines.append(f"  Boot options: {stats['boot_options']}")
        lines.append(f"  Drivers: {stats['drivers']}")
        lines.append(f"  Secure boot: {'enabled' if stats['secure_boot'] else 'disabled'}")
        lines.append(f"  Secure boot state: {stats['secure_boot_state']}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class EFIMiddleware(IMiddleware):
    """Middleware that stores FizzBuzz classifications as UEFI runtime variables.

    Each classification result is persisted in the UEFI variable store,
    enabling firmware-level access to FizzBuzz state across reboots.
    """

    FIZZBUZZ_GUID = "12345678-FIZZ-BUZZ-EFI0-000000000001"

    def __init__(self, firmware: UEFIFirmware) -> None:
        self.firmware = firmware
        self.evaluations = 0

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        self.evaluations += 1

        if number % 15 == 0:
            label = "FizzBuzz"
        elif number % 3 == 0:
            label = "Fizz"
        elif number % 5 == 0:
            label = "Buzz"
        else:
            label = str(number)

        # Store classification as UEFI variable
        var_name = f"FizzBuzz_{number}"
        self.firmware.variable_store.set_variable(
            var_name, self.FIZZBUZZ_GUID,
            label.encode("utf-8"),
        )

        context.metadata["efi_classification"] = label
        context.metadata["efi_variable"] = var_name
        context.metadata["efi_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzefi"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzefi_subsystem(
    secure_boot: bool = True,
) -> tuple[UEFIFirmware, EFIMiddleware]:
    """Create and configure the complete FizzEFI subsystem.

    Args:
        secure_boot: Whether to enable UEFI Secure Boot.

    Returns:
        Tuple of (UEFIFirmware, EFIMiddleware).
    """
    firmware = UEFIFirmware(secure_boot=secure_boot)
    middleware = EFIMiddleware(firmware)

    # Install the FizzBuzz protocol during boot services
    firmware.boot_services.install_protocol(
        "FIZZBUZZ-PROTO-0001", "FizzBuzzClassificationProtocol",
    )

    # Add default boot option
    firmware.boot_manager.add_option(
        "Enterprise FizzBuzz Application",
        "PciRoot(0x0)/Pci(0x1F,0x0)/FizzBuzz",
    )

    logger.info(
        "FizzEFI subsystem initialized: secure_boot=%s",
        secure_boot,
    )

    return firmware, middleware
