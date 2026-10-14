import math
import tempfile
import unittest
from pathlib import Path

from darcy_weisbach import (
    analyze,
    calculate_friction_factor,
    calculate_head_loss,
    calculate_reynolds_number,
    save_report,
)


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


if __name__ == "__main__":
    unittest.main()
