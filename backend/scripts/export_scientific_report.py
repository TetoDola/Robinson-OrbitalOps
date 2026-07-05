from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.science.calculation_modules import ScientificPredictionEngine
from app.science.reporting import format_scientific_report
from app.simulator.scenarios import build_24h_snapshot


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    output_file = project_root.parent / "orbitops_calculs_predictions.txt"
    elapsed_minutes = 390
    assessment = ScientificPredictionEngine().assess(build_24h_snapshot(elapsed_minutes), elapsed_minutes)
    output_file.write_text(format_scientific_report(assessment), encoding="utf-8")
    print(output_file)


if __name__ == "__main__":
    main()
