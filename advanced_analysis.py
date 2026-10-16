"""Advanced educational analysis tools for the Darcy-Weisbach application."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Callable

from darcy_weisbach import AnalysisResult, analyze
from phase_two import PumpCurvePoint, pump_head_at_flow


def hydraulic_diameter(area_m2: float, wetted_perimeter_m: float) -> float:
    """Return hydraulic diameter D_h = 4A/P."""
    if not math.isfinite(area_m2) or area_m2 <= 0:
        raise ValueError("area_m2 must be positive and finite")
    if not math.isfinite(wetted_perimeter_m) or wetted_perimeter_m <= 0:
        raise ValueError("wetted_perimeter_m must be positive and finite")
    return 4 * area_m2 / wetted_perimeter_m


def rectangular_hydraulic_diameter(width_m: float, height_m: float) -> float:
    """Return the hydraulic diameter of a closed rectangular duct."""
    if width_m <= 0 or height_m <= 0:
        raise ValueError("width_m and height_m must be positive")
    return hydraulic_diameter(width_m * height_m, 2 * (width_m + height_m))


@dataclass(frozen=True)
class SensitivityPoint:
    parameter: float
    result: AnalysisResult


def sensitivity_analysis(
    base_kwargs: dict[str, object],
    parameter: str,
    values: list[float] | tuple[float, ...],
) -> tuple[SensitivityPoint, ...]:
    """Recalculate a case for each value of one numeric input."""
    if not values:
        raise ValueError("values must not be empty")
    points = []
    for value in values:
        if not math.isfinite(value):
            raise ValueError("sensitivity values must be finite")
        kwargs = dict(base_kwargs)
        kwargs[parameter] = value
        points.append(SensitivityPoint(value, analyze(**kwargs)))
    return tuple(points)


def monte_carlo_analysis(
    base_kwargs: dict[str, object],
    ranges: dict[str, tuple[float, float]],
    *,
    samples: int = 200,
    seed: int = 0,
) -> tuple[AnalysisResult, ...]:
    """Sample uniformly distributed input ranges and return calculated results."""
    if samples < 1:
        raise ValueError("samples must be >= 1")
    generator = random.Random(seed)
    results = []
    for parameter, bounds in ranges.items():
        if (
            len(bounds) != 2
            or not all(math.isfinite(bound) for bound in bounds)
            or bounds[0] > bounds[1]
        ):
            raise ValueError(f"invalid range for {parameter}")
    for _ in range(samples):
        kwargs = dict(base_kwargs)
        for parameter, (low, high) in ranges.items():
            kwargs[parameter] = generator.uniform(low, high)
        results.append(analyze(**kwargs))
    return tuple(results)


def summarize_results(results: list[AnalysisResult] | tuple[AnalysisResult, ...]) -> dict[str, float]:
    """Return min, mean, max for key output values."""
    if not results:
        raise ValueError("results must not be empty")
    heads = [result.total_head_loss_m for result in results]
    pressures = [result.pressure_loss_pa for result in results]
    return {
        "head_min_m": min(heads),
        "head_mean_m": sum(heads) / len(heads),
        "head_max_m": max(heads),
        "pressure_min_pa": min(pressures),
        "pressure_mean_pa": sum(pressures) / len(pressures),
        "pressure_max_pa": max(pressures),
    }


def combine_pump_curves(
    curves: list[list[PumpCurvePoint] | tuple[PumpCurvePoint, ...]],
    mode: str,
) -> tuple[PumpCurvePoint, ...]:
    """Combine pumps in series or parallel on a common flow grid."""
    if not curves or any(len(curve) < 2 for curve in curves):
        raise ValueError("at least one curve with two points is required")
    if mode not in {"series", "parallel"}:
        raise ValueError("mode must be 'series' or 'parallel'")
    ordered_curves = []
    for curve in curves:
        ordered = tuple(sorted(curve, key=lambda point: point.flow_rate_m3_s))
        if len({point.flow_rate_m3_s for point in ordered}) != len(ordered):
            raise ValueError("pump curve flow rates must be unique")
        for point in ordered:
            if (
                not math.isfinite(point.flow_rate_m3_s)
                or point.flow_rate_m3_s < 0
                or not math.isfinite(point.head_m)
                or point.head_m < 0
            ):
                raise ValueError("pump curve points must be finite and non-negative")
        ordered_curves.append(ordered)
    if mode == "series":
        flows = sorted({point.flow_rate_m3_s for curve in ordered_curves for point in curve})
        return tuple(
            PumpCurvePoint(flow, sum(pump_head_at_flow(flow, curve) for curve in ordered_curves))
            for flow in flows
            if all(
                curve[0].flow_rate_m3_s <= flow <= curve[-1].flow_rate_m3_s
                for curve in ordered_curves
            )
        )
    heads = sorted({point.head_m for curve in curves for point in curve}, reverse=True)
    points = []
    for head in heads:
        flow = 0.0
        for curve in ordered_curves:
            flow += _flow_at_head(head, curve)
        points.append(PumpCurvePoint(flow, head))
    return tuple(sorted(points, key=lambda point: point.flow_rate_m3_s))


def _flow_at_head(head: float, curve: list[PumpCurvePoint] | tuple[PumpCurvePoint, ...]) -> float:
    ordered = sorted(curve, key=lambda point: point.flow_rate_m3_s)
    if head > max(point.head_m for point in ordered):
        return ordered[0].flow_rate_m3_s
    if head < min(point.head_m for point in ordered):
        return ordered[-1].flow_rate_m3_s
    for left, right in zip(ordered, ordered[1:]):
        if (left.head_m >= head >= right.head_m) or (left.head_m <= head <= right.head_m):
            if right.head_m == left.head_m:
                return left.flow_rate_m3_s
            ratio = (head - left.head_m) / (right.head_m - left.head_m)
            return left.flow_rate_m3_s + ratio * (right.flow_rate_m3_s - left.flow_rate_m3_s)
    return ordered[-1].flow_rate_m3_s


@dataclass(frozen=True)
class NetworkEdge:
    name: str
    start: str
    end: str
    resistance: float


@dataclass(frozen=True)
class NetworkResult:
    heads_m: dict[str, float]
    flows_m3_s: dict[str, float]
    iterations: int
    residual: float


def solve_network(
    nodes: dict[str, float | None],
    edges: list[NetworkEdge] | tuple[NetworkEdge, ...],
    demands_m3_s: dict[str, float] | None = None,
    *,
    tolerance: float = 1e-9,
    max_iterations: int = 100,
) -> NetworkResult:
    """Solve a small pressure network using Newton iteration.

    ``nodes`` maps fixed-head nodes to a head value and unknown nodes to ``None``.
    Demand is positive for water withdrawn at a node.
    """
    if not edges:
        raise ValueError("at least one network edge is required")
    if not math.isfinite(tolerance) or tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance must be positive and max_iterations >= 1")
    demands = demands_m3_s or {}
    for name, head in nodes.items():
        if head is not None and not math.isfinite(head):
            raise ValueError("node heads must be finite or None")
    for name, demand in demands.items():
        if name not in nodes or not math.isfinite(demand) or demand < 0:
            raise ValueError("demands must reference nodes and be non-negative and finite")
    unknown = [name for name, head in nodes.items() if head is None]
    if not unknown:
        raise ValueError("at least one node head must be unknown")
    edge_names = [edge.name for edge in edges]
    if len(edge_names) != len(set(edge_names)):
        raise ValueError("network edge names must be unique")
    for edge in edges:
        if (
            edge.start not in nodes
            or edge.end not in nodes
            or not math.isfinite(edge.resistance)
            or edge.resistance <= 0
        ):
            raise ValueError("network edges must reference nodes and use positive resistance")
    fixed_nodes = {name for name, head in nodes.items() if head is not None}
    reachable = set(fixed_nodes)
    while True:
        expanded = {
            edge.end if edge.start in reachable else edge.start
            for edge in edges
            if edge.start in reachable or edge.end in reachable
        }
        updated = reachable | expanded
        if updated == reachable:
            break
        reachable = updated
    if len(reachable) != len(nodes):
        raise ValueError("all network nodes must connect to a fixed-head node")
    heads = {name: (0.0 if value is None else value) for name, value in nodes.items()}

    def flows(current: dict[str, float]) -> dict[str, float]:
        return {
            edge.name: math.copysign(
                math.sqrt(abs(current[edge.start] - current[edge.end]) / edge.resistance),
                current[edge.start] - current[edge.end],
            )
            if current[edge.start] != current[edge.end]
            else 0.0
            for edge in edges
        }

    def residuals(current: dict[str, float]) -> list[float]:
        edge_flows = flows(current)
        result = []
        for node in unknown:
            net_in = 0.0
            for edge in edges:
                flow = edge_flows[edge.name]
                if edge.end == node:
                    net_in += flow
                if edge.start == node:
                    net_in -= flow
            result.append(net_in - demands.get(node, 0.0))
        return result

    for iteration in range(1, max_iterations + 1):
        current = residuals(heads)
        if max(abs(value) for value in current) < tolerance:
            edge_flows = flows(heads)
            return NetworkResult(dict(heads), edge_flows, iteration, max(abs(value) for value in current))
        jacobian = []
        for index in range(len(unknown)):
            row = []
            for node in unknown:
                perturbed = dict(heads)
                delta = max(abs(heads[node]) * 1e-6, 1e-6)
                perturbed[node] += delta
                row.append((residuals(perturbed)[index] - current[index]) / delta)
            jacobian.append(row)
        step = _solve_linear(jacobian, [-value for value in current])
        for node, change in zip(unknown, step):
            heads[node] += change
    raise RuntimeError("network solver did not converge")


def _solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for pivot in range(size):
        best = max(range(pivot, size), key=lambda row: abs(augmented[row][pivot]))
        if abs(augmented[best][pivot]) < 1e-14:
            raise ValueError("network equations are singular")
        augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
        divisor = augmented[pivot][pivot]
        augmented[pivot] = [value / divisor for value in augmented[pivot]]
        for row in range(size):
            if row != pivot:
                factor = augmented[row][pivot]
                augmented[row] = [
                    left - factor * right
                    for left, right in zip(augmented[row], augmented[pivot])
                ]
    return [augmented[row][-1] for row in range(size)]
