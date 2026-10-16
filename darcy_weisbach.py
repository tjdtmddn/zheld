"""Darcy-Weisbach friction-factor and pipe-loss analyzer."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path


MATERIAL_ROUGHNESS_M = {
    "pvc": 0.0015e-3,
    "commercial-steel": 0.045e-3,
    "cast-iron": 0.26e-3,
    "concrete": 1.5e-3,
    "glass": 0.001e-3,
}
FLUID_PRESETS = {
    "water": (998.0, 1.002e-3),
    "air": (1.204, 1.825e-5),
}


@dataclass(frozen=True)
class AnalysisResult:
    flow_rate_m3_s: float
    area_m2: float
    velocity_m_s: float
    reynolds_number: float
    relative_roughness: float
    flow_regime: str
    friction_factor: float
    major_head_loss_m: float
    minor_head_loss_m: float
    total_head_loss_m: float
    static_head_m: float
    required_pump_head_m: float
    pressure_loss_pa: float
    pump_power_w: float | None
    iterations: int
    warning: str | None = None
    equations: tuple[str, ...] = ()
    diameter_m: float = 0.0
    pipe_length_m: float = 0.0
    absolute_roughness_m: float = 0.0
    transitional_policy: str = "warn"
    fluid: str = "water"
    density_kg_m3: float = 998.0
    dynamic_viscosity_pa_s: float = 1.002e-3

    @property
    def head_loss_m(self) -> float:
        """Backward-compatible alias for total head loss."""
        return self.total_head_loss_m


def configure_matplotlib_korean() -> None:
    """Configure a Windows Korean font when available."""
    try:
        import matplotlib
    except ImportError:
        return

    font_candidates = (
        ("Malgun Gothic", Path("C:/Windows/Fonts/malgun.ttf")),
        ("맑은 고딕", Path("C:/Windows/Fonts/malgun.ttf")),
        ("Gulim", Path("C:/Windows/Fonts/gulim.ttc")),
        ("굴림", Path("C:/Windows/Fonts/gulim.ttc")),
    )
    for family, font_path in font_candidates:
        if font_path.exists():
            matplotlib.rcParams["font.family"] = family
            matplotlib.rcParams["axes.unicode_minus"] = False
            return


def water_properties(temperature_c: float) -> tuple[float, float]:
    """Return approximate water density and dynamic viscosity."""
    _require_finite("temperature_c", temperature_c)
    if not 0.0 <= temperature_c <= 100.0:
        raise ValueError("temperature_c must be between 0 and 100 °C")
    density = (
        999.842594
        + 0.06793952 * temperature_c
        - 0.00909529 * temperature_c**2
        + 0.0001001683 * temperature_c**3
        - 1.120083e-6 * temperature_c**4
        + 6.536332e-9 * temperature_c**5
    )
    viscosity = 1.792e-3 / (
        1.0 + 0.0337 * temperature_c + 0.000221 * temperature_c**2
    )
    return density, viscosity


def fluid_properties(
    fluid: str,
    *,
    temperature_c: float | None = None,
    density_kg_m3: float | None = None,
    dynamic_viscosity_pa_s: float | None = None,
) -> tuple[float, float]:
    """Return density and dynamic viscosity for a preset or custom fluid."""
    name = fluid.strip().lower()
    if name == "water" and temperature_c is not None:
        return water_properties(temperature_c)
    if name not in FLUID_PRESETS and (
        density_kg_m3 is None or dynamic_viscosity_pa_s is None
    ):
        raise ValueError("unknown fluid requires custom density and viscosity")
    density, viscosity = FLUID_PRESETS.get(name, (density_kg_m3, dynamic_viscosity_pa_s))
    if density_kg_m3 is not None:
        density = density_kg_m3
    if dynamic_viscosity_pa_s is not None:
        viscosity = dynamic_viscosity_pa_s
    _require_positive("density_kg_m3", density)
    _require_positive("dynamic_viscosity_pa_s", viscosity)
    return density, viscosity


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
    """Return Darcy friction factor, regime, and iteration count."""
    _require_positive("reynolds_number", reynolds_number)
    if not math.isfinite(relative_roughness) or relative_roughness < 0:
        raise ValueError("relative_roughness must be non-negative")
    if not math.isfinite(tolerance) or tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance must be positive and max_iterations must be >= 1")

    if reynolds_number < 2300:
        return 64.0 / reynolds_number, "laminar", 0
    if reynolds_number < 4000:
        return 64.0 / reynolds_number, "transitional", 0

    def residual(factor: float) -> float:
        return 1.0 / math.sqrt(factor) + 2.0 * math.log10(
            relative_roughness / 3.7
            + 2.51 / (reynolds_number * math.sqrt(factor))
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


def calculate_minor_head_loss(
    loss_coefficient: float,
    velocity_m_s: float,
    *,
    gravity_m_s2: float = 9.80665,
) -> float:
    """Calculate minor loss from the sum of fitting loss coefficients."""
    _require_positive("loss_coefficient", loss_coefficient, allow_zero=True)
    _require_positive("velocity_m_s", velocity_m_s)
    _require_positive("gravity_m_s2", gravity_m_s2)
    return loss_coefficient * velocity_m_s**2 / (2.0 * gravity_m_s2)


def calculate_component_loss_coefficients(
    components: dict[str, tuple[int, float]],
) -> tuple[float, dict[str, float]]:
    """Return total K and each component's contribution."""
    total = 0.0
    contributions: dict[str, float] = {}
    for name, (count, coefficient) in components.items():
        if count < 1 or coefficient < 0:
            raise ValueError("component count must be >= 1 and K must be non-negative")
        contribution = count * coefficient
        contributions[name] = contribution
        total += contribution
    return total, contributions


def analyze(
    *,
    velocity_m_s: float | None = None,
    flow_rate_m3_s: float | None = None,
    diameter_m: float,
    pipe_length_m: float,
    absolute_roughness_m: float | None = None,
    material: str | None = None,
    density_kg_m3: float | None = None,
    dynamic_viscosity_pa_s: float | None = None,
    fluid: str = "water",
    temperature_c: float | None = None,
    minor_loss_coefficient: float = 0.0,
    minor_loss_components: dict[str, tuple[int, float]] | None = None,
    static_head_m: float = 0.0,
    gravity_m_s2: float = 9.80665,
    pump_efficiency: float | None = None,
    transitional_policy: str = "warn",
) -> AnalysisResult:
    if (velocity_m_s is None) == (flow_rate_m3_s is None):
        raise ValueError("provide exactly one of velocity_m_s or flow_rate_m3_s")
    _require_positive("diameter_m", diameter_m)
    _require_positive("pipe_length_m", pipe_length_m)
    _require_positive("minor_loss_coefficient", minor_loss_coefficient, allow_zero=True)
    _require_positive("static_head_m", static_head_m, allow_zero=True)
    _require_positive("gravity_m_s2", gravity_m_s2)
    if transitional_policy not in {"warn", "stop"}:
        raise ValueError("transitional_policy must be 'warn' or 'stop'")
    if minor_loss_components:
        minor_loss_coefficient, _ = calculate_component_loss_coefficients(
            minor_loss_components
        )
        _require_positive(
            "minor_loss_coefficient", minor_loss_coefficient, allow_zero=True
        )

    density_kg_m3, dynamic_viscosity_pa_s = fluid_properties(
        fluid,
        temperature_c=temperature_c,
        density_kg_m3=density_kg_m3,
        dynamic_viscosity_pa_s=dynamic_viscosity_pa_s,
    )

    if material is not None:
        try:
            material_roughness = MATERIAL_ROUGHNESS_M[material.lower()]
        except KeyError as exc:
            choices = ", ".join(sorted(MATERIAL_ROUGHNESS_M))
            raise ValueError(f"unknown material; choose one of: {choices}") from exc
        if absolute_roughness_m is not None:
            raise ValueError("provide only one of absolute_roughness_m or material")
        absolute_roughness_m = material_roughness
    if absolute_roughness_m is None:
        absolute_roughness_m = MATERIAL_ROUGHNESS_M["commercial-steel"]
    _require_positive("absolute_roughness_m", absolute_roughness_m, allow_zero=True)

    area = math.pi * diameter_m**2 / 4.0
    if flow_rate_m3_s is not None:
        _require_positive("flow_rate_m3_s", flow_rate_m3_s)
        velocity_m_s = flow_rate_m3_s / area
    else:
        _require_positive("velocity_m_s", velocity_m_s)
        flow_rate_m3_s = velocity_m_s * area

    if pump_efficiency is not None and not 0 < pump_efficiency <= 1:
        raise ValueError("pump_efficiency must be greater than 0 and at most 1")

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
    if regime == "transitional" and transitional_policy == "stop":
        raise ValueError(
            "Reynolds 수가 천이영역(2300 이상 4000 미만)이므로 계산을 중단했습니다."
        )
    major_head_loss = calculate_head_loss(
        friction_factor,
        pipe_length_m,
        diameter_m,
        velocity_m_s,
        gravity_m_s2=gravity_m_s2,
    )
    minor_head_loss = calculate_minor_head_loss(
        minor_loss_coefficient, velocity_m_s, gravity_m_s2=gravity_m_s2
    )
    total_head_loss = major_head_loss + minor_head_loss
    required_pump_head = total_head_loss + static_head_m
    pressure_loss = density_kg_m3 * gravity_m_s2 * total_head_loss
    pump_power = None
    if pump_efficiency is not None:
        pump_power = (
            density_kg_m3
            * gravity_m_s2
            * flow_rate_m3_s
            * required_pump_head
            / pump_efficiency
        )
    warnings: list[str] = []
    if regime == "transitional":
        warnings.append("천이영역에서는 마찰계수와 손실 예측의 불확실성이 큽니다.")
    if relative_roughness > 0.05:
        warnings.append("상대조도 epsilon/D가 매우 커 입력값을 확인하세요.")
    warning = " ".join(warnings) or None
    equations = (
        f"A = pi D^2 / 4 = {area:.6g} m^2",
        f"V = Q / A = {flow_rate_m3_s:.6g} / {area:.6g} = {velocity_m_s:.6g} m/s",
        f"Re = rho V D / mu = {reynolds:.6g}",
        f"epsilon/D = {relative_roughness:.6g}",
        f"h_major = f(L/D)V^2/(2g) = {major_head_loss:.6g} m",
        f"h_minor = K V^2/(2g), K = {minor_loss_coefficient:.6g} = {minor_head_loss:.6g} m",
        f"H_pump = h_total + static_head = {required_pump_head:.6g} m",
    )
    return AnalysisResult(
        flow_rate_m3_s,
        area,
        velocity_m_s,
        reynolds,
        relative_roughness,
        regime,
        friction_factor,
        major_head_loss,
        minor_head_loss,
        total_head_loss,
        static_head_m,
        required_pump_head,
        pressure_loss,
        pump_power,
        iterations,
        warning,
        equations,
        diameter_m,
        pipe_length_m,
        absolute_roughness_m,
        transitional_policy,
        fluid,
        density_kg_m3,
        dynamic_viscosity_pa_s,
    )


def save_report(result: AnalysisResult, path: Path) -> None:
    """Write a human-readable report as UTF-8 text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    report = (
        "Darcy-Weisbach 관로 손실 분석 결과\n"
        "================================\n"
        f"레이놀즈 수 (Re): {result.reynolds_number:.6g}\n"
        f"상대조도 (epsilon/D): {result.relative_roughness:.6g}\n"
        f"유동 구간: {result.flow_regime}\n"
        f"Darcy 마찰계수 (f): {result.friction_factor:.10f}\n"
        f"유량 (m³/s): {result.flow_rate_m3_s:.6g}\n"
        f"단면적 (m²): {result.area_m2:.6g}\n"
        f"평균 유속 (m/s): {result.velocity_m_s:.6f}\n"
        f"주손실수두 (m): {result.major_head_loss_m:.6f}\n"
        f"부차적 손실수두 (m): {result.minor_head_loss_m:.6f}\n"
        f"전체 손실수두 (m): {result.total_head_loss_m:.6f}\n"
        f"정수두 (m): {result.static_head_m:.6f}\n"
        f"필요 펌프수두 (m): {result.required_pump_head_m:.6f}\n"
        f"압력손실 (kPa): {result.pressure_loss_pa / 1000:.6f}\n"
    )
    if result.pump_power_w is not None:
        report += f"필요 펌프동력 (kW): {result.pump_power_w / 1000:.6f}\n"
    if result.equations:
        report += "\n계산식 및 중간값\n"
        report += "\n".join(result.equations) + "\n"
    if result.warning:
        report += f"경고: {result.warning}\n"
    path.write_text(report, encoding="utf-8")


def save_plot(result: AnalysisResult, path: Path) -> None:
    """Save a result graph. Matplotlib is imported only when plotting."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "그래프 저장에는 matplotlib이 필요합니다. "
            "`pip install -r requirements.txt`를 실행하세요."
        ) from exc

    configure_matplotlib_korean()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(["Re"], [result.reynolds_number], color="#4472C4")
    axes[0].set_yscale("log")
    axes[0].set_title(f"Flow regime: {result.flow_regime}")
    axes[0].set_ylabel("Reynolds number (log scale)")
    axes[1].bar(
        ["Major loss", "Minor loss", "Static head", "Pump head"],
        [
            result.major_head_loss_m,
            result.minor_head_loss_m,
            result.static_head_m,
            result.required_pump_head_m,
        ],
        color=["#70AD47", "#ED7D31", "#5B9BD5", "#A5A5A5"],
    )
    axes[1].set_yscale("log")
    axes[1].set_title("Head loss")
    axes[1].set_ylabel("Head loss (m, log scale)")
    fig.suptitle("Darcy-Weisbach Analysis")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _require_positive(name: str, value: float, *, allow_zero: bool = False) -> None:
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be {comparator} and finite")


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def main() -> None:
    parser = argparse.ArgumentParser(description="Darcy-Weisbach 관로 분석기")
    flow_group = parser.add_mutually_exclusive_group(required=True)
    flow_group.add_argument("--velocity", type=float, help="평균 유속 V (m/s)")
    flow_group.add_argument("--flow-rate", type=float, help="유량 Q (m3/s)")
    parser.add_argument("--diameter", type=float, required=True, help="관경 D (m)")
    parser.add_argument("--length", type=float, required=True, help="관 길이 L (m)")
    roughness_group = parser.add_mutually_exclusive_group()
    roughness_group.add_argument("--roughness", type=float, help="절대조도 epsilon (m)")
    roughness_group.add_argument(
        "--material", choices=sorted(MATERIAL_ROUGHNESS_M), help="관 재질"
    )
    parser.add_argument("--fluid", choices=sorted(FLUID_PRESETS), default="water")
    parser.add_argument("--density", type=float, help="사용자 밀도 rho (kg/m3)")
    parser.add_argument("--viscosity", type=float, help="사용자 동적 점성계수 (Pa.s)")
    parser.add_argument("--temperature", type=float, help="물 온도 (°C, 0~100)")
    parser.add_argument("--minor-k", type=float, default=0.0, help="부차적 손실계수 합")
    parser.add_argument("--static-head", type=float, default=0.0, help="정수두 또는 높이차 (m)")
    parser.add_argument("--pump-efficiency", type=float, help="펌프 효율 (0~1)")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    result = analyze(
        velocity_m_s=args.velocity,
        flow_rate_m3_s=args.flow_rate,
        diameter_m=args.diameter,
        pipe_length_m=args.length,
        absolute_roughness_m=args.roughness,
        material=args.material,
        density_kg_m3=args.density,
        dynamic_viscosity_pa_s=args.viscosity,
        fluid=args.fluid,
        temperature_c=args.temperature,
        minor_loss_coefficient=args.minor_k,
        static_head_m=args.static_head,
        pump_efficiency=args.pump_efficiency,
    )
    output_dir = args.output_dir
    save_report(result, output_dir / "darcy_weisbach_report.txt")
    save_plot(result, output_dir / "darcy_weisbach_analysis.png")
    print(f"분석 완료: {output_dir / 'darcy_weisbach_report.txt'}")
    print(f"그래프 저장: {output_dir / 'darcy_weisbach_analysis.png'}")


if __name__ == "__main__":
    main()
