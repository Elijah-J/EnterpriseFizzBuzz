"""Feature descriptor for the FizzRobotics robot motion planning engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzRoboticsFeature(FeatureDescriptor):
    name = "fizzrobotics"
    description = "Robot motion planning with RRT path planning, inverse kinematics, PID control, and collision avoidance"
    middleware_priority = 284
    cli_flags = [
        ("--fizzrobotics", {"action": "store_true", "default": False,
                            "help": "Enable FizzRobotics: robotic token placement with motion planning"}),
        ("--fizzrobotics-num-links", {"type": int, "metavar": "N", "default": None,
                                       "help": "Number of robot arm links (default: 3)"}),
        ("--fizzrobotics-link-length", {"type": float, "metavar": "M", "default": None,
                                         "help": "Length of each link in meters (default: 1.0)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzrobotics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzrobotics import (
            RobotArm,
            RoboticsMiddleware,
        )

        num_links = getattr(args, "fizzrobotics_num_links", None) or config.fizzrobotics_num_links
        link_length = getattr(args, "fizzrobotics_link_length", None) or config.fizzrobotics_link_length
        seed = config.fizzrobotics_seed

        middleware = RoboticsMiddleware(
            num_links=num_links,
            link_length=link_length,
            seed=seed,
        )

        return middleware.robot, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZROBOTICS: ROBOT MOTION PLANNING ENGINE               |\n"
            "  |   RRT path planning in configuration space               |\n"
            "  |   Jacobian-based inverse kinematics                      |\n"
            "  |   PID trajectory tracking with anti-windup               |\n"
            "  +---------------------------------------------------------+"
        )
