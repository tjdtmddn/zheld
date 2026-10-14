"""Darcy-Weisbach friction-factor and head-loss analyzer.

The friction factor returned by this module is the Darcy (not Fanning)
friction factor.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalysisResult:
    reynolds_number: float
    relative_roughness: float
    flow_regime: str
    friction_factor: float
    head_loss_m: float
    iterations: int


def calculate_reynolds_number(
    velocity_m_s: float,
    diameter_m: float,
    *,
    density_kg_m3: float = 998.0,
    dynamic_viscosity_pa_s: float = 1.002e-3,
) -> float:
    """Calculate Reynolds number from velocity and fluid properties."""
    _require_positive("velocity_m_s", velocity_m_s)
    _require_positive("diameter_m", diameter_m)
    _require_positive("density_kg_m3", density_kg_m3)
    _require_positive("dynamic_viscosity_pa_s", dynamic_viscosity_pa_s)
    return density_kg_m3 * velocity_m_s * diameter_m / dynamic_viscosity_pa_s


def calculate_friction_factor(
    reynolds_number: float,
    relative_roughness: float,
    *,
    tolerance: float = 1e-12,
    max_iterations: int = 100,
) -> tuple[float, str, int]:
    """Return Darcy friction factor, regime, and iterations.

    Laminar flow uses the exact relation f=64/Re. Turbulent flow solves the
    Colebrook-White equation with a bracketed bisection method, avoiding the
    convergence failures that can occur with an unconstrained Newton step.
    """
    _require_positive("reynolds_number", reynolds_number)
    if relative_roughness < 0:
        raise ValueError("relative_roughness must be non-negative")
    if tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance must be positive and max_iterations must be >= 1")

    if reynolds_number < 2300:
        return 64.0 / reynolds_number, "laminar", 0
    if reynolds_number < 4000:
        # Colebrook is not defined as a reliable model in the transition zone.
        return 64.0 / reynolds_number, "transitional", 0

    def residual(factor: float) -> float:
        return (
            1.0 / math.sqrt(factor)
            + 2.0
            * math.log10(
                relative_roughness / 3.7
                + 2.51 / (reynolds_number * math.sqrt(factor))
            )
        )

    lower, upper = 1e-6, 1.0
    lower_value, upper_value = residual(lower), residual(upper)
    if lower_value * upper_value > 0:
        raise RuntimeError("Could not bracket the Colebrook-White solution")

    for iteration in range(1, max_iterations + 1):
        midpoint = (lower + upper) / 2.0
        midpoint_value = residual(midpoint)
        if abs(midpoint_value) < tolerance or (upper - lower) / 2.0 < tolerance:
            return midpoint, "turbulent", iteration
        if lower_value * midpoint_value > 0:
            lower, lower_value = midpoint, midpoint_value
        else:
            upper = midpoint
    return (lower + upper) / 2.0, "turbulent", max_iterations


def calculate_head_loss(
    friction_factor: float,
    pipe_length_m: float,
    diameter_m: float,
    velocity_m_s: float,
    *,
    gravity_m_s2: float = 9.80665,
) -> float:
    """Calculate major head loss using the Darcy-Weisbach equation."""
    _require_positive("friction_factor", friction_factor)
    _require_positive("pipe_length_m", pipe_length_m)
    _require_positive("diameter_m", diameter_m)
    _require_positive("velocity_m_s", velocity_m_s)
    _require_positive("gravity_m_s2", gravity_m_s2)
    return friction_factor * pipe_length_m / diameter_m * velocity_m_s**2 / (
        2.0 * gravity_m_s2
    )


def analyze(
    *,
    velocity_m_s: float,
    diameter_m: float,
    pipe_length_m: float,
    absolute_roughness_m: float,
    density_kg_m3: float = 998.0,
    dynamic_viscosity_pa_s: float = 1.002e-3,
) -> AnalysisResult:
    _require_positive("absolute_roughness_m", absolute_roughness_m, allow_zero=True)
    reynolds = calculate_reynolds_number(
        velocity_m_s,
        diameter_m,
        density_kg_m3=density_kg_m3,
        dynamic_viscosity_pa_s=dynamic_viscosity_pa_s,
    )
    relative_roughness = absolute_roughness_m / diameter_m
    friction_factor, regime, iterations = calculate_friction_factor(
        reynolds, relative_roughness
    )
    head_loss = calculate_head_loss(
        friction_factor, pipe_length_m, diameter_m, velocity_m_s
    )
    return AnalysisResult(
        reynolds, relative_roughness, regime, friction_factor, head_loss, iterations
    )


def save_report(result: AnalysisResult, path: Path) -> None:
    """Write a human-readable report as UTF-8 text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    report = (
        "Darcy-Weisbach 마찰계수 및 손실수두 분석 결과\n"
        "============================================\n"
        f"레이놀즈 수 (Re): {result.reynolds_number:.6g}\n"
        f"상대조도 (epsilon/D): {result.relative_roughness:.6g}\n"
        f"유동 구간: {result.flow_regime}\n"
        f"Darcy 마찰계수 (f): {result.friction_factor:.10f}\n"
        f"손실수두 (m): {result.head_loss_m:.6f}\n"
        f"Colebrook 반복 횟수: {result.iterations}\n"
    )
    path.write_text(report, encoding="utf-8")


def save_plot(result: AnalysisResult, path: Path) -> None:
    """Save a compact result graph. Matplotlib is imported only when plotting."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "그래프 저장에는 matplotlib이 필요합니다. `pip install -r requirements.txt`를 실행하세요."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    labels = ["Re", "epsilon/D", "f", "head loss (m)"]
    values = [
        result.reynolds_number,
        result.relative_roughness,
        result.friction_factor,
        result.head_loss_m,
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(["Re"], [result.reynolds_number], color="#4472C4")
    axes[0].set_yscale("log")
    axes[0].set_title(f"Flow regime: {result.flow_regime}")
    axes[0].set_ylabel("Reynolds number (log scale)")
    axes[1].bar(labels[1:], values[1:], color=["#70AD47", "#ED7D31", "#A5A5A5"])
    axes[1].set_yscale("log")
    axes[1].set_title("Roughness, friction factor, head loss")
    axes[1].set_ylabel("Value (log scale)")
    fig.suptitle("Darcy-Weisbach Analysis")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _require_positive(name: str, value: float, *, allow_zero: bool = False) -> None:
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be {comparator} and finite")


def main() -> None:
    parser = argparse.ArgumentParser(description="Darcy-Weisbach 관수로 분석기")
    parser.add_argument("--velocity", type=float, required=True, help="평균 유속 V (m/s)")
    parser.add_argument("--diameter", type=float, required=True, help="관경 D (m)")
    parser.add_argument("--length", type=float, required=True, help="관 길이 L (m)")
    parser.add_argument("--roughness", type=float, required=True, help="절대조도 epsilon (m)")
    parser.add_argument("--density", type=float, default=998.0, help="밀도 rho (kg/m3)")
    parser.add_argument("--viscosity", type=float, default=1.002e-3, help="점성계수 mu (Pa.s)")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    result = analyze(
        velocity_m_s=args.velocity,
        diameter_m=args.diameter,
        pipe_length_m=args.length,
        absolute_roughness_m=args.roughness,
        density_kg_m3=args.density,
        dynamic_viscosity_pa_s=args.viscosity,
    )
    output_dir = args.output_dir
    save_report(result, output_dir / "darcy_weisbach_report.txt")
    save_plot(result, output_dir / "darcy_weisbach_analysis.png")
    print(f"분석 완료: {output_dir / 'darcy_weisbach_report.txt'}")
    print(f"그래프 저장: {output_dir / 'darcy_weisbach_analysis.png'}")


if __name__ == "__main__":
    main()
