"""
Enterprise FizzBuzz Platform - FizzRobotics: Robot Motion Planning Engine

Implements a complete robotic motion planning pipeline for a serial-link
manipulator arm tasked with physically arranging FizzBuzz output tokens.
The engine computes collision-free trajectories through configuration space
using Rapidly-exploring Random Trees (RRT), solves inverse kinematics for
target end-effector poses, applies PID control for trajectory tracking,
and performs collision detection against environmental obstacles.

The robotic manipulator model is a planar N-link serial chain with
revolute joints. Each joint has configurable angle limits, and the
forward kinematics are computed using homogeneous transformation matrices
(Denavit-Hartenberg convention). Inverse kinematics uses an iterative
Jacobian-based solver with damped least squares for singularity avoidance.

The RRT path planner builds a tree in joint configuration space by random
sampling, connecting new nodes to the nearest existing node via
straight-line interpolation. The tree is grown until the goal
configuration is within a threshold distance, at which point the path
is extracted by backtracking through parent pointers.

PID control computes joint torques to track the planned trajectory
with configurable proportional, integral, and derivative gains. An
anti-windup mechanism limits the integral accumulator to prevent
actuator saturation.

Physical justification: Automated token placement ensures consistent
spatial arrangement of FizzBuzz outputs, reducing human operator
fatigue and improving classification throughput by an estimated 340%.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_NUM_LINKS = 3
DEFAULT_LINK_LENGTH = 1.0  # meters
DEFAULT_JOINT_LIMIT = math.pi  # radians (+/-)
RRT_MAX_ITERATIONS = 5000
RRT_STEP_SIZE = 0.1  # radians
RRT_GOAL_THRESHOLD = 0.2  # radians
PID_DEFAULT_KP = 10.0
PID_DEFAULT_KI = 0.5
PID_DEFAULT_KD = 1.0
PID_MAX_OUTPUT = 100.0  # Nm
COLLISION_RADIUS = 0.1  # meters


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class JointConfig:
    """Configuration for a single revolute joint."""
    angle: float = 0.0
    min_angle: float = -DEFAULT_JOINT_LIMIT
    max_angle: float = DEFAULT_JOINT_LIMIT
    link_length: float = DEFAULT_LINK_LENGTH

    @property
    def is_within_limits(self) -> bool:
        return self.min_angle <= self.angle <= self.max_angle


@dataclass
class Pose2D:
    """A 2D position and orientation."""
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    def distance_to(self, other: Pose2D) -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass
class Obstacle:
    """A circular obstacle in the workspace."""
    x: float
    y: float
    radius: float
    obstacle_id: str = ""


@dataclass
class RRTNode:
    """A node in the Rapidly-exploring Random Tree."""
    config: list[float]
    parent: Optional[RRTNode] = None


@dataclass
class Trajectory:
    """A sequence of joint configurations representing a planned path."""
    waypoints: list[list[float]] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.waypoints)

    @property
    def total_distance(self) -> float:
        total = 0.0
        for i in range(1, len(self.waypoints)):
            total += config_distance(self.waypoints[i - 1], self.waypoints[i])
        return total


@dataclass
class PIDState:
    """State of a PID controller for a single joint."""
    joint_id: int
    kp: float = PID_DEFAULT_KP
    ki: float = PID_DEFAULT_KI
    kd: float = PID_DEFAULT_KD
    integral: float = 0.0
    prev_error: float = 0.0
    max_output: float = PID_MAX_OUTPUT

    def compute(self, error: float, dt: float) -> float:
        """Compute PID control output."""
        from enterprise_fizzbuzz.domain.exceptions.fizzrobotics import PIDControlError

        self.integral += error * dt
        # Anti-windup clamp
        max_integral = self.max_output / max(self.ki, 1e-6)
        self.integral = max(-max_integral, min(self.integral, max_integral))

        derivative = (error - self.prev_error) / max(dt, 1e-6)
        self.prev_error = error

        output = self.kp * error + self.ki * self.integral + self.kd * derivative

        if abs(output) > self.max_output:
            raise PIDControlError(self.joint_id, output, self.max_output)

        return output


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def config_distance(c1: list[float], c2: list[float]) -> float:
    """Compute the L2 distance between two joint configurations."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def interpolate_config(
    c1: list[float], c2: list[float], t: float,
) -> list[float]:
    """Linearly interpolate between two configurations."""
    return [a + t * (b - a) for a, b in zip(c1, c2)]


def clamp_angle(angle: float, min_a: float, max_a: float) -> float:
    """Clamp an angle to the given joint limits."""
    return max(min_a, min(angle, max_a))


# ---------------------------------------------------------------------------
# Forward Kinematics
# ---------------------------------------------------------------------------

class ForwardKinematics:
    """Computes end-effector pose from joint angles using DH parameters.

    For a planar N-link manipulator, the forward kinematics chain is:

        x = sum(L_i * cos(sum(theta_1..theta_i)))
        y = sum(L_i * sin(sum(theta_1..theta_i)))
        theta = sum(theta_1..theta_n)
    """

    def __init__(self, joints: list[JointConfig]) -> None:
        self._joints = joints

    @property
    def num_joints(self) -> int:
        return len(self._joints)

    def compute(self, angles: Optional[list[float]] = None) -> Pose2D:
        """Compute the end-effector pose."""
        if angles is None:
            angles = [j.angle for j in self._joints]

        x = 0.0
        y = 0.0
        cumulative_angle = 0.0

        for i, joint in enumerate(self._joints):
            cumulative_angle += angles[i]
            x += joint.link_length * math.cos(cumulative_angle)
            y += joint.link_length * math.sin(cumulative_angle)

        return Pose2D(x=x, y=y, theta=cumulative_angle)

    def compute_all_positions(self, angles: Optional[list[float]] = None) -> list[Pose2D]:
        """Compute positions of all joint centers (for collision checking)."""
        if angles is None:
            angles = [j.angle for j in self._joints]

        positions = [Pose2D(0.0, 0.0, 0.0)]
        x = 0.0
        y = 0.0
        cumulative = 0.0

        for i, joint in enumerate(self._joints):
            cumulative += angles[i]
            x += joint.link_length * math.cos(cumulative)
            y += joint.link_length * math.sin(cumulative)
            positions.append(Pose2D(x=x, y=y, theta=cumulative))

        return positions

    @property
    def max_reach(self) -> float:
        return sum(j.link_length for j in self._joints)


# ---------------------------------------------------------------------------
# Inverse Kinematics
# ---------------------------------------------------------------------------

class InverseKinematics:
    """Iterative Jacobian-based inverse kinematics solver.

    Uses the Jacobian transpose method with damped least squares for
    singularity robustness. Iterates until the end-effector is within
    the position tolerance of the target or the maximum iterations
    are reached.
    """

    def __init__(
        self,
        fk: ForwardKinematics,
        max_iterations: int = 100,
        tolerance: float = 0.01,
        damping: float = 0.1,
    ) -> None:
        self._fk = fk
        self._max_iterations = max_iterations
        self._tolerance = tolerance
        self._damping = damping

    def solve(self, target: Pose2D, initial_angles: Optional[list[float]] = None) -> list[float]:
        """Solve IK for the given target position."""
        from enterprise_fizzbuzz.domain.exceptions.fizzrobotics import InverseKinematicsError

        n = self._fk.num_joints
        angles = list(initial_angles) if initial_angles else [0.0] * n

        for iteration in range(self._max_iterations):
            current = self._fk.compute(angles)
            dx = target.x - current.x
            dy = target.y - current.y
            error = math.sqrt(dx * dx + dy * dy)

            if error < self._tolerance:
                return angles

            # Compute Jacobian
            jacobian = self._compute_jacobian(angles)

            # Jacobian transpose step with damping
            for i in range(n):
                jx, jy = jacobian[i]
                delta = self._damping * (jx * dx + jy * dy)
                angles[i] += delta
                # Clamp to joint limits
                joint = self._fk._joints[i]
                angles[i] = clamp_angle(angles[i], joint.min_angle, joint.max_angle)

        raise InverseKinematicsError(
            (target.x, target.y),
            f"Did not converge after {self._max_iterations} iterations",
        )

    def _compute_jacobian(self, angles: list[float]) -> list[Tuple[float, float]]:
        """Compute the 2xN Jacobian matrix columns."""
        n = self._fk.num_joints
        joints = self._fk._joints
        jacobian: list[Tuple[float, float]] = []

        for i in range(n):
            cumulative = sum(angles[:i + 1])
            # Remaining link contributions
            jx = 0.0
            jy = 0.0
            angle_sum = sum(angles[:i + 1])
            for j in range(i, n):
                if j > i:
                    angle_sum += angles[j]
                jx += -joints[j].link_length * math.sin(angle_sum)
                jy += joints[j].link_length * math.cos(angle_sum)

            jacobian.append((jx, jy))

        return jacobian


# ---------------------------------------------------------------------------
# Collision Detector
# ---------------------------------------------------------------------------

class CollisionDetector:
    """Checks for collisions between robot links and obstacles."""

    def __init__(self, obstacles: Optional[list[Obstacle]] = None) -> None:
        self._obstacles = obstacles or []

    @property
    def obstacles(self) -> list[Obstacle]:
        return list(self._obstacles)

    def add_obstacle(self, obstacle: Obstacle) -> None:
        self._obstacles.append(obstacle)

    def check_config(
        self, fk: ForwardKinematics, angles: list[float],
    ) -> bool:
        """Return True if the configuration is collision-free."""
        positions = fk.compute_all_positions(angles)

        for pos in positions:
            for obs in self._obstacles:
                dist = math.sqrt((pos.x - obs.x) ** 2 + (pos.y - obs.y) ** 2)
                if dist < obs.radius + COLLISION_RADIUS:
                    return False

        return True

    def find_collision(
        self, fk: ForwardKinematics, angles: list[float],
    ) -> Optional[Tuple[int, str]]:
        """Find the first collision and return (joint_id, obstacle_id)."""
        positions = fk.compute_all_positions(angles)

        for i, pos in enumerate(positions):
            for obs in self._obstacles:
                dist = math.sqrt((pos.x - obs.x) ** 2 + (pos.y - obs.y) ** 2)
                if dist < obs.radius + COLLISION_RADIUS:
                    return (i, obs.obstacle_id)

        return None


# ---------------------------------------------------------------------------
# RRT Path Planner
# ---------------------------------------------------------------------------

class RRTPlanner:
    """Rapidly-exploring Random Tree path planner.

    Grows a tree in configuration space by random sampling and
    nearest-neighbor extension. The tree connects the start
    configuration to the goal configuration through a sequence
    of collision-free intermediate configurations.
    """

    def __init__(
        self,
        fk: ForwardKinematics,
        collision_detector: CollisionDetector,
        max_iterations: int = RRT_MAX_ITERATIONS,
        step_size: float = RRT_STEP_SIZE,
        goal_threshold: float = RRT_GOAL_THRESHOLD,
        seed: Optional[int] = None,
    ) -> None:
        self._fk = fk
        self._collision = collision_detector
        self._max_iterations = max_iterations
        self._step_size = step_size
        self._goal_threshold = goal_threshold
        self._rng = random.Random(seed)

    def plan(self, start: list[float], goal: list[float]) -> Trajectory:
        """Plan a collision-free path from start to goal."""
        from enterprise_fizzbuzz.domain.exceptions.fizzrobotics import PathPlanningError

        root = RRTNode(config=list(start))
        tree = [root]
        joints = self._fk._joints

        for iteration in range(self._max_iterations):
            # Random sample (with goal bias)
            if self._rng.random() < 0.1:
                sample = list(goal)
            else:
                sample = [
                    self._rng.uniform(j.min_angle, j.max_angle)
                    for j in joints
                ]

            # Find nearest node
            nearest = min(tree, key=lambda n: config_distance(n.config, sample))

            # Steer toward sample
            dist = config_distance(nearest.config, sample)
            if dist < 1e-6:
                continue

            t = min(self._step_size / dist, 1.0)
            new_config = interpolate_config(nearest.config, sample, t)

            # Collision check
            if not self._collision.check_config(self._fk, new_config):
                continue

            new_node = RRTNode(config=new_config, parent=nearest)
            tree.append(new_node)

            # Check if goal reached
            if config_distance(new_config, goal) < self._goal_threshold:
                return self._extract_path(new_node)

        raise PathPlanningError(
            tuple(start), tuple(goal), self._max_iterations,
        )

    def _extract_path(self, node: RRTNode) -> Trajectory:
        """Extract the path from the tree by backtracking parent pointers."""
        waypoints: list[list[float]] = []
        current: Optional[RRTNode] = node
        while current is not None:
            waypoints.append(current.config)
            current = current.parent
        waypoints.reverse()
        return Trajectory(waypoints=waypoints)


# ---------------------------------------------------------------------------
# PID Controller Array
# ---------------------------------------------------------------------------

class PIDControllerArray:
    """Array of PID controllers, one per joint."""

    def __init__(
        self,
        num_joints: int,
        kp: float = PID_DEFAULT_KP,
        ki: float = PID_DEFAULT_KI,
        kd: float = PID_DEFAULT_KD,
    ) -> None:
        self._controllers = [
            PIDState(joint_id=i, kp=kp, ki=ki, kd=kd)
            for i in range(num_joints)
        ]

    def compute(
        self, target: list[float], current: list[float], dt: float,
    ) -> list[float]:
        """Compute control outputs for all joints."""
        outputs: list[float] = []
        for i, ctrl in enumerate(self._controllers):
            error = target[i] - current[i]
            output = ctrl.compute(error, dt)
            outputs.append(output)
        return outputs

    def reset(self) -> None:
        for ctrl in self._controllers:
            ctrl.integral = 0.0
            ctrl.prev_error = 0.0


# ---------------------------------------------------------------------------
# Robot Arm
# ---------------------------------------------------------------------------

class RobotArm:
    """A planar serial-link robotic manipulator.

    Combines forward/inverse kinematics, collision detection, path
    planning, and PID control into a unified robot controller.
    """

    def __init__(
        self,
        num_links: int = DEFAULT_NUM_LINKS,
        link_length: float = DEFAULT_LINK_LENGTH,
        seed: Optional[int] = None,
    ) -> None:
        self._joints = [
            JointConfig(
                angle=0.0,
                link_length=link_length,
                min_angle=-DEFAULT_JOINT_LIMIT,
                max_angle=DEFAULT_JOINT_LIMIT,
            )
            for _ in range(num_links)
        ]
        self._fk = ForwardKinematics(self._joints)
        self._collision = CollisionDetector()
        self._ik = InverseKinematics(self._fk)
        self._planner = RRTPlanner(
            self._fk, self._collision, seed=seed,
        )
        self._pid = PIDControllerArray(num_links)
        self._current_angles = [0.0] * num_links

    @property
    def num_joints(self) -> int:
        return len(self._joints)

    @property
    def current_angles(self) -> list[float]:
        return list(self._current_angles)

    @property
    def end_effector(self) -> Pose2D:
        return self._fk.compute(self._current_angles)

    @property
    def max_reach(self) -> float:
        return self._fk.max_reach

    def add_obstacle(self, obstacle: Obstacle) -> None:
        self._collision.add_obstacle(obstacle)

    def move_to(self, target: Pose2D) -> Trajectory:
        """Plan and execute a move to the target position."""
        goal_angles = self._ik.solve(target, self._current_angles)
        trajectory = self._planner.plan(self._current_angles, goal_angles)

        # Simulate trajectory execution
        for waypoint in trajectory.waypoints:
            self._current_angles = list(waypoint)
            for i, joint in enumerate(self._joints):
                joint.angle = waypoint[i]

        return trajectory

    def get_joint_positions(self) -> list[Pose2D]:
        return self._fk.compute_all_positions(self._current_angles)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RoboticsMiddleware(IMiddleware):
    """Middleware that plans robot motions for FizzBuzz token placement.

    Each evaluated number generates a target position for the robotic
    manipulator based on its classification. The robot plans a
    collision-free trajectory to the target and the motion data is
    attached to the processing context.

    Priority 284 positions this middleware in the physical actuation tier.
    """

    def __init__(
        self,
        num_links: int = DEFAULT_NUM_LINKS,
        link_length: float = DEFAULT_LINK_LENGTH,
        seed: Optional[int] = None,
    ) -> None:
        self._robot = RobotArm(
            num_links=num_links,
            link_length=link_length,
            seed=seed,
        )
        self._move_count = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        # Map number to target position within reach
        max_r = self._robot.max_reach * 0.7
        angle = (number * 0.5) % (2 * math.pi)
        target_x = max_r * math.cos(angle)
        target_y = max_r * math.sin(angle)

        target = Pose2D(x=target_x, y=target_y)

        try:
            trajectory = self._robot.move_to(target)
            self._move_count += 1

            result.metadata["robotics_target_x"] = target_x
            result.metadata["robotics_target_y"] = target_y
            result.metadata["robotics_waypoints"] = trajectory.length
            result.metadata["robotics_path_length"] = trajectory.total_distance
            ee = self._robot.end_effector
            result.metadata["robotics_ee_x"] = ee.x
            result.metadata["robotics_ee_y"] = ee.y
        except Exception as e:
            logger.warning("Robotics motion planning failed for number %d: %s", number, e)
            result.metadata["robotics_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "RoboticsMiddleware"

    def get_priority(self) -> int:
        return 284

    @property
    def robot(self) -> RobotArm:
        return self._robot

    @property
    def move_count(self) -> int:
        return self._move_count
