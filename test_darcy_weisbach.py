import math
import tempfile
import unittest
from pathlib import Path

from darcy_weisbach import (
    analyze,
    calculate_friction_factor,
    calculate_head_loss,
    calculate_minor_head_loss,
    calculate_component_loss_coefficients,
    calculate_reynolds_number,
    save_report,
    configure_matplotlib_korean,
    water_properties,
)
from phase_two import (
    PumpCurvePoint,
    find_operating_point,
    parallel_branch_flows,
    parallel_resistance,
    pump_head_at_flow,
    series_resistance,
)
from advanced_analysis import (
    NetworkEdge,
    combine_pump_curves,
    monte_carlo_analysis,
    rectangular_hydraulic_diameter,
    sensitivity_analysis,
    solve_network,
    summarize_results,
)
from darcy_weisbach_gui import DarcyWeisbachApp


class DarcyWeisbachTests(unittest.TestCase):
    def test_reynolds_number(self):
        self.assertAlmostEqual(calculate_reynolds_number(1.0, 0.1), 99600.7984, places=2)

    def test_laminar_factor(self):
        factor, regime, iterations = calculate_friction_factor(1000, 0.001)
        self.assertEqual((regime, iterations), ("laminar", 0))
        self.assertAlmostEqual(factor, 0.064)

    def test_turbulent_colebrook_solution(self):
        factor, regime, iterations = calculate_friction_factor(100000, 0.0001)
        self.assertEqual(regime, "turbulent")
        self.assertGreater(iterations, 0)
        self.assertTrue(math.isclose(factor, 0.0185139, rel_tol=1e-5))

    def test_invalid_finite_values_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_friction_factor(10000, math.nan)
        with self.assertRaises(ValueError):
            parallel_resistance([math.nan])
        with self.assertRaises(ValueError):
            find_operating_point([], 0, 1)
        with self.assertRaises(ValueError):
            pump_head_at_flow(
                0.01,
                [PumpCurvePoint(0, 20), PumpCurvePoint(0, 15)],
            )

    def test_head_loss_and_report(self):
        result = analyze(
            velocity_m_s=2.0,
            diameter_m=0.1,
            pipe_length_m=20.0,
            absolute_roughness_m=0.000045,
        )
        self.assertGreater(result.head_loss_m, 0)
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "result.txt"
            save_report(result, report)
            self.assertIn("레이놀즈 수", report.read_text(encoding="utf-8"))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            calculate_head_loss(0, 1, 1, 1)

    def test_component_minor_losses(self):
        total, contributions = calculate_component_loss_coefficients(
            {"elbow": (4, 0.3), "entrance": (1, 0.5)}
        )
        self.assertAlmostEqual(total, 1.7)
        self.assertAlmostEqual(contributions["elbow"], 1.2)
        result = analyze(
            velocity_m_s=2.0,
            diameter_m=0.1,
            pipe_length_m=20.0,
            absolute_roughness_m=0.000045,
            minor_loss_components={"elbow": (4, 0.3), "entrance": (1, 0.5)},
        )
        self.assertAlmostEqual(
            result.minor_head_loss_m,
            calculate_minor_head_loss(1.7, 2.0),
        )
        self.assertTrue(result.equations)

    def test_flow_rate_minor_loss_and_pressure_loss(self):
        result = analyze(
            flow_rate_m3_s=0.01,
            diameter_m=0.1,
            pipe_length_m=20.0,
            material="pvc",
            minor_loss_coefficient=2.0,
            temperature_c=20.0,
            static_head_m=5.0,
            pump_efficiency=0.8,
        )
        self.assertAlmostEqual(result.flow_rate_m3_s, 0.01)
        self.assertGreater(result.velocity_m_s, 0)
        self.assertGreater(result.minor_head_loss_m, 0)
        self.assertGreater(result.pressure_loss_pa, 0)
        self.assertGreater(result.pump_power_w, 0)
        self.assertAlmostEqual(
            result.required_pump_head_m,
            result.total_head_loss_m + 5.0,
        )
        self.assertAlmostEqual(
            result.minor_head_loss_m,
            calculate_minor_head_loss(2.0, result.velocity_m_s),
        )

    def test_transitional_flow_has_warning(self):
        result = analyze(
            velocity_m_s=0.03,
            diameter_m=0.1,
            pipe_length_m=10.0,
            absolute_roughness_m=0,
        )
        self.assertEqual(result.flow_regime, "transitional")
        self.assertIsNotNone(result.warning)
        with self.assertRaises(ValueError):
            analyze(
                velocity_m_s=0.03,
                diameter_m=0.1,
                pipe_length_m=10.0,
                absolute_roughness_m=0,
                transitional_policy="stop",
            )

    def test_pump_curve_operating_point(self):
        point = find_operating_point(
            [PumpCurvePoint(0, 30), PumpCurvePoint(0.01, 25), PumpCurvePoint(0.02, 15)],
            static_head_m=5,
            resistance_m_per_flow2=50000,
        )
        self.assertGreater(point.flow_rate_m3_s, 0)
        self.assertAlmostEqual(point.pump_head_m, point.system_head_m, places=6)

    def test_series_and_parallel_networks(self):
        self.assertEqual(series_resistance([1, 2, 3]), 6)
        equivalent = parallel_resistance([1000, 1000])
        self.assertAlmostEqual(equivalent, 250)
        flows = parallel_branch_flows(0.02, [1000, 4000])
        self.assertAlmostEqual(sum(flows), 0.02)
        self.assertGreater(flows[0], flows[1])

    def test_advanced_analysis_tools(self):
        self.assertAlmostEqual(rectangular_hydraulic_diameter(1, 1), 1)
        kwargs = {
            "flow_rate_m3_s": 0.01,
            "diameter_m": 0.1,
            "pipe_length_m": 20,
            "material": "pvc",
        }
        points = sensitivity_analysis(kwargs, "flow_rate_m3_s", [0.005, 0.01])
        self.assertEqual(len(points), 2)
        samples = monte_carlo_analysis(
            kwargs, {"flow_rate_m3_s": (0.009, 0.011)}, samples=5
        )
        summary = summarize_results(samples)
        self.assertLessEqual(summary["head_min_m"], summary["head_mean_m"])
        combined = combine_pump_curves(
            [[PumpCurvePoint(0, 20), PumpCurvePoint(0.02, 10)]],
            "series",
        )
        self.assertEqual(len(combined), 2)
        unsorted = [PumpCurvePoint(0.02, 10), PumpCurvePoint(0, 30)]
        combined_unsorted = combine_pump_curves([unsorted, unsorted], "series")
        self.assertEqual(len(combined_unsorted), 2)

    def test_multi_node_network_solver(self):
        result = solve_network(
            {"source": 10.0, "junction": None, "sink": 0.0},
            [
                NetworkEdge("inlet", "source", "junction", 1000),
                NetworkEdge("outlet", "junction", "sink", 1000),
            ],
        )
        self.assertAlmostEqual(result.heads_m["junction"], 5.0, places=5)
        self.assertAlmostEqual(result.flows_m3_s["inlet"], result.flows_m3_s["outlet"], places=7)
        with self.assertRaises(ValueError):
            solve_network(
                {"source": 10.0, "junction": None, "sink": 0.0},
                [
                    NetworkEdge("same", "source", "junction", 1000),
                    NetworkEdge("same", "junction", "sink", 1000),
                ],
            )

    def test_water_properties_are_reasonable(self):
        density, viscosity = water_properties(20.0)
        self.assertAlmostEqual(density, 998.2, delta=0.3)
        self.assertAlmostEqual(viscosity, 1.002e-3, delta=0.02e-3)

    def test_matplotlib_korean_configuration_is_safe(self):
        configure_matplotlib_korean()

    def test_csv_row_unit_conversion_and_validation(self):
        row = DarcyWeisbachApp._normalise_csv_row(
            {
                "flow_rate": "15",
                "flow_unit": "L/s",
                "diameter": "100",
                "diameter_unit": "mm",
                "pipe_length": "2",
                "length_unit": "km",
                "material": "pvc",
                "temperature_c": "20",
            },
            2,
        )
        self.assertAlmostEqual(float(row["flow_rate_m3_s"]), 0.015)
        self.assertAlmostEqual(float(row["diameter_m"]), 0.1)
        self.assertAlmostEqual(float(row["pipe_length_m"]), 2000)
        result = DarcyWeisbachApp.__new__(DarcyWeisbachApp)._row_to_result(row, 2)
        self.assertAlmostEqual(result.flow_rate_m3_s, 0.015)

        with self.assertRaises(ValueError):
            DarcyWeisbachApp._validate_csv_headers(["flow_rate_m3_s"])
        with self.assertRaises(ValueError):
            DarcyWeisbachApp._normalise_csv_row(
                {
                    "flow_rate_m3_s": "0.01",
                    "diameter_m": "0.1",
                    "pipe_length_m": "20",
                    "material": "pvc",
                    "timestamp": "not-a-date",
                },
                3,
            )


if __name__ == "__main__":
    unittest.main()
