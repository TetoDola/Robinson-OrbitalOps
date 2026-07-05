from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from app.models import TelemetrySnapshot
from app.science.calculation_modules import ScientificPredictionEngine
from app.science.reporting import format_scientific_report
from export_science_module_documents import master_document, module_document, validate_payload


def load_samples(path: Path) -> tuple[list[TelemetrySnapshot], int]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        raw_samples = payload
        elapsed_minutes = 0
    else:
        raw_samples = payload["samples"]
        elapsed_minutes = int(payload.get("elapsed_minutes") or 0)
    samples = [TelemetrySnapshot.model_validate(item) for item in raw_samples]
    if not samples:
        raise ValueError("Telemetry file must contain at least one sample.")
    return samples, elapsed_minutes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OrbitOps science modules on an arbitrary telemetry time series.")
    parser.add_argument("--input", required=True, help="JSON file containing either a list of TelemetrySnapshot objects or {samples, elapsed_minutes}.")
    parser.add_argument("--out-dir", required=True, help="Directory where result files will be written.")
    args = parser.parse_args()

    samples, elapsed_minutes = load_samples(Path(args.input))
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    modules_dir = output_dir / "science_modules_data_driven"
    modules_dir.mkdir(parents=True, exist_ok=True)

    assessment = ScientificPredictionEngine().assess(samples[-1], elapsed_minutes, samples)
    payload = assessment.model_dump(mode="json")
    checks = validate_payload(payload)

    (output_dir / "orbitops_data_driven_results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "orbitops_data_driven_report.txt").write_text(format_scientific_report(assessment), encoding="utf-8")
    (output_dir / "orbitops_data_driven_coherence.txt").write_text(master_document(payload, checks), encoding="utf-8")
    for module in payload["modules"]:
        module_id = str(module["module_id"])
        (modules_dir / f"{module_id}.txt").write_text(module_document(payload, module), encoding="utf-8")

    print(output_dir / "orbitops_data_driven_results.json")
    print(output_dir / "orbitops_data_driven_report.txt")
    print(output_dir / "orbitops_data_driven_coherence.txt")
    for module in payload["modules"]:
        print(modules_dir / f"{module['module_id']}.txt")


if __name__ == "__main__":
    main()
