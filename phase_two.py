"""Educational pump-curve and simple pipe-network calculations."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PumpCurvePoint:
    flow_rate_m3_s: float
    head_m: float


@dataclass(frozen=True)
class OperatingPoint:
    flow_rate_m3_s: float
    pump_head_m: float
    system_head_m: float
    residual_m: float


def _positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def _nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be non-negative and finite")


def pump_head_at_flow(
    flow_rate_m3_s: float,
    points: list[PumpCurvePoint] | tuple[PumpCurvePoint, ...],
) -> float:
    """Linearly interpolate a pump curve and reject flows outside its range."""
    _nonnegative(flow_rate_m3_s, "flow_rate_m3_s")
    if len(points) < 2:
        raise ValueError("pump curve requires at least two points")
    ordered = tuple(sorted(points, key=lambda point: point.flow_rate_m3_s))
    if len({point.flow_rate_m3_s for point in ordered}) != len(ordered):
        raise ValueError("pump curve flow rates must be unique")
    for point in ordered:
        _nonnegative(point.flow_rate_m3_s, "pump flow")
        _nonnegative(point.head_m, "pump head")
    if flow_rate_m3_s < ordered[0].flow_rate_m3_s or flow_rate_m3_s > ordered[-1].flow_rate_m3_s:
        raise ValueError("flow rate is outside the pump curve range")
    for left, right in zip(ordered, ordered[1:]):
        if left.flow_rate_m3_s <= flow_rate_m3_s <= right.flow_rate_m3_s:
            if right.flow_rate_m3_s == left.flow_rate_m3_s:
                return left.head_m
            ratio = (flow_rate_m3_s - left.flow_rate_m3_s) / (
                right.flow_rate_m3_s - left.flow_rate_m3_s
            )
            return left.head_m + ratio * (right.head_m - left.head_m)
    return ordered[-1].head_m


def system_head(
    flow_rate_m3_s: float,
    static_head_m: float,
    resistance_m_per_flow2: float,
) -> float:
    """Return H_system = H_static + R Q²."""
    _nonnegative(flow_rate_m3_s, "flow_rate_m3_s")
    _nonnegative(static_head_m, "static_head_m")
    _nonnegative(resistance_m_per_flow2, "resistance_m_per_flow2")
    return static_head_m + resistance_m_per_flow2 * flow_rate_m3_s**2


def find_operating_point(
    points: list[PumpCurvePoint] | tuple[PumpCurvePoint, ...],
    static_head_m: float,
    resistance_m_per_flow2: float,
    *,
    tolerance_m: float = 1e-9,
    max_iterations: int = 100,
) -> OperatingPoint:
    """Find the pump/system intersection using bisection."""
    if not points:
        raise ValueError("pump curve requires at least two points")
    if not math.isfinite(tolerance_m) or tolerance_m <= 0 or max_iterations < 1:
        raise ValueError("tolerance_m must be positive and max_iterations >= 1")
    ordered = tuple(sorted(points, key=lambda point: point.flow_rate_m3_s))
    if len({point.flow_rate_m3_s for point in ordered}) != len(ordered):
        raise ValueError("pump curve flow rates must be unique")
    _positive(ordered[-1].flow_rate_m3_s, "maximum pump flow")
    low, high = ordered[0].flow_rate_m3_s, ordered[-1].flow_rate_m3_s

    def residual(flow: float) -> float:
        return pump_head_at_flow(flow, ordered) - system_head(
            flow, static_head_m, resistance_m_per_flow2
        )

    low_value, high_value = residual(low), residual(high)
    if low_value * high_value > 0:
        raise ValueError("펌프 곡선과 시스템 곡선의 교점이 범위 안에 없습니다.")
    for _ in range(max_iterations):
        midpoint = (low + high) / 2
        midpoint_value = residual(midpoint)
        if abs(midpoint_value) <= tolerance_m or (high - low) <= tolerance_m:
            pump_head = pump_head_at_flow(midpoint, ordered)
            return OperatingPoint(
                midpoint, pump_head,
                system_head(midpoint, static_head_m, resistance_m_per_flow2),
                midpoint_value,
            )
        if low_value * midpoint_value <= 0:
            high, high_value = midpoint, midpoint_value
        else:
            low, low_value = midpoint, midpoint_value
    midpoint = (low + high) / 2
    pump_head = pump_head_at_flow(midpoint, ordered)
    return OperatingPoint(
        midpoint, pump_head,
        system_head(midpoint, static_head_m, resistance_m_per_flow2),
        residual(midpoint),
    )


def series_resistance(resistances: list[float] | tuple[float, ...]) -> float:
    """Equivalent R for pipes in series: R_eq = sum(R_i)."""
    if not resistances:
        raise ValueError("at least one resistance is required")
    for resistance in resistances:
        _nonnegative(resistance, "resistance")
    return sum(resistances)


def parallel_resistance(resistances: list[float] | tuple[float, ...]) -> float:
    """Equivalent R for parallel branches: 1/sqrt(R_eq)=sum(1/sqrt(R_i))."""
    if not resistances:
        raise ValueError("parallel resistances must be positive")
    for resistance in resistances:
        _positive(resistance, "resistance")
    return 1 / sum(1 / math.sqrt(resistance) for resistance in resistances) ** 2


def parallel_branch_flows(
    total_flow_m3_s: float,
    resistances: list[float] | tuple[float, ...],
) -> tuple[float, ...]:
    """Split a total flow among parallel branches with H_loss = R Q²."""
    _positive(total_flow_m3_s, "total_flow_m3_s")
    equivalent = parallel_resistance(resistances)
    common_head = equivalent * total_flow_m3_s**2
    flows = tuple(math.sqrt(common_head / resistance) for resistance in resistances)
    scale = total_flow_m3_s / sum(flows)
    return tuple(flow * scale for flow in flows)
