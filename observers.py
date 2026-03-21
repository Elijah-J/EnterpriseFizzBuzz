"""
Enterprise FizzBuzz Platform - Observer/Event System Module

Implements the Observer pattern with a thread-safe event bus for
decoupled communication between FizzBuzz pipeline components.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from exceptions import ObserverError
from interfaces import IEventBus, IObserver
from models import (
    Event,
    EventType,
    FizzBuzzResult,
    FizzBuzzSessionSummary,
)

logger = logging.getLogger(__name__)


class EventBus(IEventBus):
    """Thread-safe event bus implementing publish/subscribe pattern.

    Ensures that all observers are notified of events in a deterministic
    order, with full error isolation between observers.
    """

    def __init__(self) -> None:
        self._observers: list[IObserver] = []
        self._lock = threading.Lock()
        self._event_history: list[Event] = []

    def subscribe(self, observer: IObserver) -> None:
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)
                logger.debug("Observer '%s' subscribed", observer.get_name())

    def unsubscribe(self, observer: IObserver) -> None:
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)
                logger.debug("Observer '%s' unsubscribed", observer.get_name())

    def publish(self, event: Event) -> None:
        with self._lock:
            self._event_history.append(event)
            observers_snapshot = list(self._observers)

        for observer in observers_snapshot:
            try:
                observer.on_event(event)
            except Exception as e:
                logger.error(
                    "Observer '%s' failed on event '%s': %s",
                    observer.get_name(),
                    event.event_type.name,
                    e,
                )

    def get_event_history(self) -> list[Event]:
        """Return a copy of the full event history."""
        with self._lock:
            return list(self._event_history)

    def clear_history(self) -> None:
        """Clear the event history."""
        with self._lock:
            self._event_history.clear()


class ConsoleObserver(IObserver):
    """Observer that prints events to the console in real-time.

    Useful for debugging and development environments.
    """

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose

    def on_event(self, event: Event) -> None:
        if self._verbose or event.event_type in (
            EventType.FIZZ_DETECTED,
            EventType.BUZZ_DETECTED,
            EventType.FIZZBUZZ_DETECTED,
            EventType.ERROR_OCCURRED,
        ):
            timestamp = event.timestamp.strftime("%H:%M:%S.%f")[:-3]
            print(
                f"  [{timestamp}] EVENT: {event.event_type.name} "
                f"| Source: {event.source} "
                f"| Payload: {event.payload}"
            )

    def get_name(self) -> str:
        return "ConsoleObserver"


class StatisticsObserver(IObserver):
    """Observer that collects statistics during FizzBuzz processing.

    Maintains running counts and timing data for session summary generation.
    """

    def __init__(self) -> None:
        self._fizz_count = 0
        self._buzz_count = 0
        self._fizzbuzz_count = 0
        self._plain_count = 0
        self._total_count = 0
        self._errors: list[str] = []
        self._lock = threading.Lock()

    def on_event(self, event: Event) -> None:
        with self._lock:
            if event.event_type == EventType.FIZZ_DETECTED:
                self._fizz_count += 1
            elif event.event_type == EventType.BUZZ_DETECTED:
                self._buzz_count += 1
            elif event.event_type == EventType.FIZZBUZZ_DETECTED:
                self._fizzbuzz_count += 1
            elif event.event_type == EventType.PLAIN_NUMBER_DETECTED:
                self._plain_count += 1
            elif event.event_type == EventType.NUMBER_PROCESSED:
                self._total_count += 1
            elif event.event_type == EventType.ERROR_OCCURRED:
                self._errors.append(str(event.payload.get("error", "Unknown")))

    def get_name(self) -> str:
        return "StatisticsObserver"

    def get_summary_data(self) -> dict:
        """Return collected statistics as a dictionary."""
        with self._lock:
            return {
                "fizz_count": self._fizz_count,
                "buzz_count": self._buzz_count,
                "fizzbuzz_count": self._fizzbuzz_count,
                "plain_count": self._plain_count,
                "total_count": self._total_count,
                "errors": list(self._errors),
            }

    def reset(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self._fizz_count = 0
            self._buzz_count = 0
            self._fizzbuzz_count = 0
            self._plain_count = 0
            self._total_count = 0
            self._errors.clear()
