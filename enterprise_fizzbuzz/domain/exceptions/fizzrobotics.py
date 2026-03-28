"""
Enterprise FizzBuzz Platform - FizzRobotics Exceptions (EFP-ROB00 through EFP-ROB09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzRoboticsError(FizzBuzzError):
    """Base exception for the FizzRobotics robot motion planning subsystem.

    The FizzRobotics engine computes collision-free trajectories for a
    robotic manipulator tasked with physically arranging FizzBuzz output
    tokens. Motion planning involves solving the inverse kinematics of
    a serial-link robot arm, generating RRT paths through configuration
    space, and applying PID control for trajectory tracking. Each of
    these computational stages can fail under kinematic or geometric
    constraints.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ROB00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InverseKinematicsError(FizzRoboticsError):
    """Raised when inverse kinematics has no solution for the target pose.

    The inverse kinematics problem maps a desired end-effector position
    and orientation to joint angles. When the target lies outside the
    reachable workspace of the manipulator, no solution exists. This
    can occur when FizzBuzz tokens are placed beyond the robot's
    maximum reach envelope.
    """

    def __init__(self, target_position: tuple, reason: str) -> None:
        super().__init__(
            f"Inverse kinematics failed for target {target_position}: {reason}",
            error_code="EFP-ROB01",
            context={"target_position": target_position, "reason": reason},
        )


class PathPlanningError(FizzRoboticsError):
    """Raised when the RRT path planner fails to find a collision-free path.

    The Rapidly-exploring Random Tree (RRT) algorithm builds a tree in
    configuration space by random sampling. If the maximum number of
    iterations is reached without connecting the start and goal
    configurations, the planner reports failure. This typically indicates
    that the obstacle configuration is too dense for the sampling budget.
    """

    def __init__(self, start: tuple, goal: tuple, max_iterations: int) -> None:
        super().__init__(
            f"RRT path planning failed from {start} to {goal} "
            f"after {max_iterations} iterations",
            error_code="EFP-ROB02",
            context={
                "start": start,
                "goal": goal,
                "max_iterations": max_iterations,
            },
        )


class PIDControlError(FizzRoboticsError):
    """Raised when PID controller output exceeds actuator limits.

    PID controllers compute a control signal proportional to the error,
    its integral, and its derivative. If the accumulated integral term
    causes windup, the output may exceed the physical torque limits of
    the actuator, requiring anti-windup measures.
    """

    def __init__(self, joint_id: int, output: float, limit: float) -> None:
        super().__init__(
            f"PID output {output:.3f} exceeds actuator limit {limit:.3f} "
            f"on joint {joint_id}",
            error_code="EFP-ROB03",
            context={"joint_id": joint_id, "output": output, "limit": limit},
        )


class CollisionError(FizzRoboticsError):
    """Raised when a collision is detected along a planned trajectory.

    Collision detection verifies that the robot's swept volume does not
    intersect with obstacles or self-collide during motion. A detected
    collision invalidates the planned trajectory and requires replanning.
    """

    def __init__(self, joint_id: int, obstacle_id: str) -> None:
        super().__init__(
            f"Collision detected: joint {joint_id} intersects obstacle '{obstacle_id}'",
            error_code="EFP-ROB04",
            context={"joint_id": joint_id, "obstacle_id": obstacle_id},
        )


class JointLimitError(FizzRoboticsError):
    """Raised when a joint angle exceeds its mechanical limits.

    Each rotational joint has a minimum and maximum angle defined by the
    robot's mechanical design. Commanding a joint beyond these limits
    risks physical damage to the actuator or linkage.
    """

    def __init__(self, joint_id: int, angle: float, min_angle: float, max_angle: float) -> None:
        super().__init__(
            f"Joint {joint_id} angle {angle:.3f} rad exceeds limits "
            f"[{min_angle:.3f}, {max_angle:.3f}]",
            error_code="EFP-ROB05",
            context={
                "joint_id": joint_id,
                "angle": angle,
                "min_angle": min_angle,
                "max_angle": max_angle,
            },
        )


class RoboticsMiddlewareError(FizzRoboticsError):
    """Raised when the FizzRobotics middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzRobotics middleware error: {reason}",
            error_code="EFP-ROB06",
            context={"reason": reason},
        )
