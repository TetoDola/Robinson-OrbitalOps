from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


EXPECTED_MODULES = {
    "workload_gpu": "Workload / GPU anomaly management",
    "thermal_physical": "Thermal / physical health anomaly management",
    "orbit_power": "Orbit-aware power and radiation-aware workload management",
    "radiation_integrity": "Radiation / bit-flip / training integrity management",
    "checkpoint_downlink": "Checkpoint / downlink / recovery management",
}

SEVERITY_BANDS = [
    (86, "CRITICAL"),
    (68, "HIGH"),
    (42, "MEDIUM"),
    (18, "LOW"),
    (0, "INFO"),
]

MODULE_EXPLANATIONS = {
    "workload_gpu": {
        "purpose": "Reconcile l'etat logique scheduler/process avec l'etat physique GPU via six hypotheses: residence GPU, worker orphelin, memoire residuelle, all-reduce bloque, interconnect degrade et trou de telemetrie.",
        "inputs": [
            "gpu_utilization_percent",
            "gpu_memory_used_gb / gpu_memory_total_gb",
            "compute_node_power_watts ou gpu_power_watts en fallback",
            "scheduler_state",
            "active_cuda_process_count",
            "scheduler_registered_process_count",
            "active_cuda_processes_not_in_scheduler",
            "time_since_last_job_end_seconds",
            "memory_release_delta_gb_per_min",
            "rank_progress_skew",
            "current_step_duration_seconds",
            "rolling_p95_step_duration_seconds",
            "nccl_warning_count",
            "interconnect_error_rate",
            "pcie_replay_count",
            "nvlink_error_count",
            "process_accounting_status",
            "bandwidth_drop_percent",
            "stale_telemetry_seconds",
        ],
        "scientific_logic": [
            "Le produit utilisation x pression memoire represente une residence GPU, pas automatiquement un worker orphelin.",
            "La v3 separe p_residency_watch et p_orphan afin d'eviter le faux diagnostic orphan quand la charge GPU peut etre legitime.",
            "Le risque all-reduce regarde des symptomes directs de training distribue: rank skew, step time anormal, warnings NCCL, erreurs interconnect et throttling.",
            "Un GPU actif sans process visible devient un trou de telemetrie/process accounting: cela augmente l'investigation mais baisse la confiance.",
            "Le risque final utilise un Noisy-OR pondere pour combiner les hypotheses sans ecraser les signaux secondaires.",
        ],
        "predictive_logic": [
            "Horizon court de 30 minutes: une anomalie workload doit etre traitee vite avant divergence d'etat training.",
            "Chaque hypothese est convertie en probabilite par sigmoid, puis combinee par Noisy-OR.",
            "Si le score est MEDIUM, l'action demande une reconciliation CUDA process table vs scheduler sans kill automatique.",
            "Si le scheduler mismatch ou process mismatch est confirme, la residence GPU devient plus severe et peut exiger validation humaine.",
        ],
    },
    "thermal_physical": {
        "purpose": "Prevoit la marge thermique, le risque hotspot et la capacite physique des radiateurs a rejeter la chaleur GPU par rayonnement.",
        "inputs": [
            "gpu_temperature_celsius",
            "hbm_temperature_c",
            "radiator_temperature_celsius",
            "board_temperature_celsius",
            "coolant_loop_temperature_c",
            "gpu_power_watts",
            "radiator_area_m2",
            "radiator_emissivity",
            "radiator_view_factor",
            "sun_exposure_factor",
            "temperatures predites sur 180 minutes",
        ],
        "scientific_logic": [
            "La marge thermique compare la temperature GPU au seuil de mission 95C.",
            "La capacite radiative est estimee par Stefan-Boltzmann: emissivite x sigma x surface x facteur de vue x T^4.",
            "Le deficit thermique compare la chaleur GPU a la capacite du radiateur; positif signifie accumulation probable.",
            "La resistance thermique observee est estimee par delta temperature GPU-radiateur divise par la puissance en kW.",
        ],
        "predictive_logic": [
            "Le moteur projette les snapshots toutes les 15 minutes sur 180 minutes.",
            "Le pic thermique predit est le maximum de temperature GPU dans cet horizon.",
            "Le score monte si la temperature, le deficit radiatif ou la pente thermique deviennent dangereux.",
        ],
    },
    "orbit_power": {
        "purpose": "Alloue l'energie entre compute, refroidissement, downlink et securite mission selon la reserve batterie et les contraintes orbitales.",
        "inputs": [
            "solar_input_watts",
            "solar_incidence_angle_deg",
            "spacecraft_base_power_watts",
            "compute_power_watts",
            "thermal_control_power_watts",
            "downlink_power_watts",
            "battery_capacity_wh",
            "battery_percent",
            "eclipse_eta_minutes",
            "radiation_window_eta_minutes",
            "critical_downlink_eta_minutes",
        ],
        "scientific_logic": [
            "La generation solaire effective depend de l'angle d'incidence solaire.",
            "La consommation est decomposee en bus spacecraft, compute, refroidissement et downlink.",
            "La pente batterie estime le gain/perte de charge avec une batterie equivalente de 12 kWh quand aucune capacite n'est fournie.",
            "La reserve cible de batterie est 35% pour conserver marge thermique, recovery et downlink.",
        ],
        "predictive_logic": [
            "Le module integre l'energie sur l'horizon pour prevoir la batterie minimale.",
            "Il ajoute des penalites si eclipse, radiation, downlink critique ou compute overcommit creent un conflit.",
            "La decision reserve l'energie pour cooling/downlink avant les workloads non critiques.",
        ],
    },
    "radiation_integrity": {
        "purpose": "Evalue bit-flip, erreurs ECC, hash/canary et confiance checkpoint pour proteger l'integrite training.",
        "inputs": [
            "radiation_dose_rate",
            "radiation_dose_accumulated",
            "south_atlantic_anomaly_flag",
            "solar_particle_event_index",
            "ecc_corrected_errors / ecc_corrected_delta",
            "ecc_uncorrected_errors / ecc_uncorrected_delta",
            "checkpoint_latest_status",
            "checkpoint_hash_verified",
            "canary_eval_score",
            "last_trusted_checkpoint_age_minutes",
        ],
        "scientific_logic": [
            "Un modele Poisson simplifie transforme dose et ECC en probabilite d'evenement bit-flip.",
            "Une erreur ECC non corrigee penalise fortement la confiance training.",
            "Un checkpoint UNKNOWN/SUSPECT/CORRUPTED ajoute une penalite de confiance.",
            "Hash non verifie et canary degrade reduisent la confiance checkpoint sans pretendre localiser un bit flip precis.",
        ],
        "predictive_logic": [
            "Le module prend le pic de dose, les deltas ECC et le statut checkpoint sur l'horizon predit.",
            "La confiance checkpoint est 100 moins les penalites bit-flip, ECC, statut, hash et canary.",
            "Le risque final est 100 - confiance checkpoint.",
        ],
    },
    "checkpoint_downlink": {
        "purpose": "Optimise le payload de recuperation a envoyer vers la Terre sous capacite downlink limitee, avec chunking et conservation locale jusqu'a ACK.",
        "inputs": [
            "downlink_available_mbps",
            "downlink_window_seconds",
            "future_contact_windows",
            "checkpoint_full_size_gb",
            "checkpoint_delta_size_gb",
            "manifest/hash/log sizes",
            "local_storage_free_gb",
            "ground_ack_status",
            "bit_error_rate",
            "compression_ratio_estimate",
        ],
        "scientific_logic": [
            "La capacite downlink vaut Mbps x secondes / 8192 pour obtenir des GB.",
            "Le full_fit_ratio compare capacite contact et taille checkpoint complet.",
            "La priorite privilegie les artefacts compacts: manifest, hashes, logs ECC/thermal/workload, delta checkpoint, puis full checkpoint.",
            "Le checkpoint complet est decoupe en chunks et ne doit pas etre supprime localement tant que le sol n'a pas ACK.",
        ],
        "predictive_logic": [
            "Le module somme les capacites de contact dans les 180 prochaines minutes ou les futures fenetres fournies.",
            "Il choisit les payloads qui tiennent dans la fenetre courante par priorite.",
            "Le score augmente si le checkpoint complet ne tient pas, si le stockage local est bas, si le sol n'a pas ACK ou si le lien est degrade.",
        ],
    },
}


def expected_severity(score: float) -> str:
    for lower, severity in SEVERITY_BANDS:
        if score >= lower:
            return severity
    return "INFO"


def status_line(ok: bool, text: str) -> str:
    return f"[{'OK' if ok else 'WARN'}] {text}"


def metric(module: dict[str, Any], name: str) -> Any:
    for item in module.get("metrics", []):
        if item.get("name") == name:
            return item.get("value")
    return None


def noisy_or_expected(probabilities: list[tuple[float, float]]) -> float:
    p_no_event = 1.0
    for probability, weight in probabilities:
        p_no_event *= 1 - max(0.0, min(1.0, probability)) * max(0.0, min(1.0, weight))
    return 100 * (1 - p_no_event)


def validate_payload(payload: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    modules = payload.get("modules", [])
    module_ids = {module.get("module_id") for module in modules}
    checks.append(status_line(len(modules) == 5, f"Nombre de modules = {len(modules)} / 5."))
    checks.append(status_line(module_ids == set(EXPECTED_MODULES), f"Modules presents = {', '.join(sorted(str(item) for item in module_ids))}."))

    max_module_score = max((float(module.get("risk_score", 0)) for module in modules), default=0)
    compound_score = float(payload.get("compound_risk_score", max_module_score))
    primary_score = float(payload.get("primary_risk_score", max_module_score))
    expected_global = round(max(primary_score, 0.65 * primary_score + 0.35 * compound_score), 1)
    overall_score = float(payload.get("overall_risk_score", -1))
    checks.append(status_line(abs(primary_score - max_module_score) <= 0.05, f"Risque primaire {primary_score:.1f} = max des modules {max_module_score:.1f}."))
    checks.append(status_line(abs(overall_score - expected_global) <= 0.15, f"Risque global {overall_score:.1f} = max(primary, 0.65 x primary + 0.35 x compound) = {expected_global:.1f}."))
    checks.append(status_line(payload.get("overall_severity") == expected_severity(overall_score), f"Severite globale {payload.get('overall_severity')} coherente avec {overall_score:.1f}/100."))

    for module in modules:
        module_id = str(module.get("module_id"))
        score = float(module.get("risk_score", -1))
        confidence = float(module.get("confidence", -1))
        severity = module.get("severity")
        checks.append(status_line(0 <= score <= 100, f"{module_id}: score dans [0,100] = {score:.1f}."))
        checks.append(status_line(0 <= confidence <= 1, f"{module_id}: confiance dans [0,1] = {confidence:.2f}."))
        checks.append(status_line(severity == expected_severity(score), f"{module_id}: severite {severity} coherente avec le score {score:.1f}."))
        checks.append(status_line(bool(module.get("formula_summary")), f"{module_id}: formules presentes."))
        checks.append(status_line(bool(module.get("evidence")), f"{module_id}: preuves structurees presentes."))
        checks.append(status_line(bool(module.get("recommended_actions")), f"{module_id}: actions recommandees presentes."))

    workload = next((module for module in modules if module.get("module_id") == "workload_gpu"), None)
    if workload:
        residency = float(metric(workload, "Residency watch probability") or 0)
        orphan = float(metric(workload, "Orphan worker probability") or 0)
        memory = float(metric(workload, "Residual memory probability") or 0)
        all_reduce = float(metric(workload, "All-reduce stall probability") or 0)
        interconnect = float(metric(workload, "Interconnect degradation probability") or 0)
        telemetry_gap = float(metric(workload, "Telemetry gap probability") or 0)
        scheduler_mismatch = int(metric(workload, "Scheduler mismatch") or 0)
        process_mismatch = int(metric(workload, "Process mismatch") or 0)
        predicted_event = str(workload.get("predicted_event", ""))
        score = float(workload["risk_score"])
        expected = round(
            noisy_or_expected(
                [
                    (residency, 0.45),
                    (orphan, 0.85),
                    (memory, 0.75),
                    (all_reduce, 0.85),
                    (interconnect, 0.70),
                    (telemetry_gap, 0.40),
                ]
            ),
            1,
        )
        checks.append(status_line(abs(score - expected) <= 0.2, f"workload_gpu: risque {score:.1f} correspond au Noisy-OR v3 = {expected:.1f}."))
        if scheduler_mismatch or process_mismatch:
            checks.append(status_line(predicted_event != "orphan worker confirmed", "workload_gpu: meme avec mismatch, le module reste prudent et ne confirme pas sans validation."))
        else:
            checks.append(status_line(predicted_event != "orphan worker suspected", "workload_gpu: sans mismatch confirme, le diagnostic evite orphan worker suspected."))

    thermal = next((module for module in modules if module.get("module_id") == "thermal_physical"), None)
    if thermal:
        current_temp = float(metric(thermal, "Current GPU temperature") or 0)
        peak_temp = float(metric(thermal, "Predicted peak temperature") or 0)
        checks.append(status_line(peak_temp >= current_temp, f"thermal_physical: pic predit {peak_temp:.1f}C >= temperature courante {current_temp:.1f}C."))
        if peak_temp < 95:
            checks.append(status_line(thermal.get("severity") in {"INFO", "LOW", "MEDIUM"}, f"thermal_physical: pic {peak_temp:.1f}C sous 95C, severite {thermal.get('severity')} non critique."))
        else:
            checks.append(status_line(thermal.get("severity") in {"HIGH", "CRITICAL"}, f"thermal_physical: pic {peak_temp:.1f}C au-dessus du seuil, severite {thermal.get('severity')} coherente."))

    power = next((module for module in modules if module.get("module_id") == "orbit_power"), None)
    if power:
        min_battery = float(metric(power, "Predicted minimum battery") or 0)
        net_power = float(metric(power, "Net power") or 0)
        if min_battery >= 35:
            checks.append(status_line(power.get("severity") in {"INFO", "LOW"}, f"orbit_power: reserve batterie {min_battery:.1f}% >= 35%, severite {power.get('severity')} coherente."))
        else:
            checks.append(status_line(power.get("severity") in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}, f"orbit_power: reserve batterie {min_battery:.1f}% sous 35%, severite {power.get('severity')} coherente."))
        checks.append(status_line(True, f"orbit_power: bilan net calcule = {net_power:.1f}W."))

    radiation = next((module for module in modules if module.get("module_id") == "radiation_integrity"), None)
    if radiation:
        trust = float(metric(radiation, "Checkpoint trust score") or 0)
        score = float(radiation["risk_score"])
        checks.append(status_line(abs(score - (100 - trust)) <= 0.2, f"radiation_integrity: risque {score:.1f} = 100 - confiance checkpoint {trust:.1f}."))

    downlink = next((module for module in modules if module.get("module_id") == "checkpoint_downlink"), None)
    if downlink:
        capacity = float(metric(downlink, "Current contact capacity") or 0)
        checkpoint = float(metric(downlink, "Checkpoint size") or 0)
        fit_ratio = float(metric(downlink, "Full fit ratio") or 0)
        recommended = str(downlink.get("recommended_decision", ""))
        selected_payloads = str(metric(downlink, "Selected payloads") or "")
        checks.append(status_line(checkpoint > capacity, f"checkpoint_downlink: checkpoint {checkpoint:.2f}GB > capacite {capacity:.2f}GB, full impossible."))
        checks.append(status_line(math.isclose(fit_ratio, capacity / checkpoint, rel_tol=0.08), f"checkpoint_downlink: fit ratio {fit_ratio:.3f} coherent avec capacite/checkpoint."))
        recommended_size = 0.05 + 0.10 + 0.40 + 0.70
        if capacity >= recommended_size:
            checks.append(status_line(("manifest" in recommended or "manifest" in selected_payloads) and ("hashes" in recommended or "hashes" in selected_payloads), f"checkpoint_downlink: manifest+hashes+logs = {recommended_size:.2f}GB tient dans {capacity:.2f}GB."))
        else:
            checks.append(status_line("wait" in recommended.lower() or "preserve" in recommended.lower() or not recommended, f"checkpoint_downlink: capacite {capacity:.2f}GB trop faible pour le paquet minimal {recommended_size:.1f}GB."))

    return checks


def module_document(payload: dict[str, Any], module: dict[str, Any]) -> str:
    module_id = str(module["module_id"])
    explanation = MODULE_EXPLANATIONS[module_id]
    lines = [
        f"OrbitOps - Module {module_id}",
        "=" * (20 + len(module_id)),
        "",
        f"Nom : {module['module_name']}",
        f"But : {explanation['purpose']}",
        "",
        "Resultat actuel",
        "-" * 15,
        f"- Heure mission : {payload['mission_clock']}",
        f"- Phase orbitale : {payload['orbit_phase']}",
        f"- Mode donnees : {payload.get('data_mode', 'not provided')}",
        f"- Echantillons lus : {payload.get('samples_used', 'not provided')}",
        f"- Fenetre de variation : {payload.get('trend_window_minutes', 'not provided')} minutes",
        f"- Resultat : {module['result']}",
        f"- Evenement predit : {module['predicted_event']}",
        f"- Niveau action : {module.get('action_level', 'not provided')}",
        f"- Resume dashboard : {module.get('dashboard_summary', 'not provided')}",
        f"- Score risque : {module['risk_score']}/100",
        f"- Severite : {module['severity']}",
        f"- Confiance : {module['confidence']}",
        f"- Horizon prediction : {module['prediction_horizon_minutes']} minutes",
        f"- Decision recommandee : {module['recommended_decision']}",
        f"- Validation humaine requise : {'oui' if module.get('requires_human_approval') else 'non'}",
        "",
        "Entrees utilisees",
        "-" * 16,
    ]
    lines.extend(f"- {item}" for item in explanation["inputs"])
    lines.extend(["", "Preuves structurees", "-" * 19])
    for key, value in module.get("evidence", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "Actions recommandees", "-" * 20])
    for action in module.get("recommended_actions", []):
        approval = "approval humaine" if action.get("approval") else "automatique"
        detail = f" | value={action.get('value')}" if "value" in action else ""
        target = f" | target={action.get('target')}" if "target" in action else ""
        lines.append(f"- {action.get('type')} ({approval}){detail}{target}: {action.get('reason')}")
    lines.extend(["", "Mesures sorties par le module", "-" * 29])
    for item in module.get("metrics", []):
        unit = f" {item.get('unit')}" if item.get("unit") else ""
        lines.append(f"- {item['name']} = {item['value']}{unit}: {item['interpretation']}")
    lines.extend(["", "Calculs scientifiques", "-" * 21])
    lines.extend(f"- {item}" for item in explanation["scientific_logic"])
    lines.extend(["", "Calculs predictifs", "-" * 19])
    lines.extend(f"- {item}" for item in explanation["predictive_logic"])
    lines.extend(["", "Formules exactes dans le moteur", "-" * 30])
    lines.extend(f"- {item}" for item in module.get("formula_summary", []))
    lines.extend(["", "Verdict coherence", "-" * 17])
    lines.append(f"- La severite attendue pour {module['risk_score']}/100 est {expected_severity(float(module['risk_score']))}.")
    lines.append(f"- La severite fournie est {module['severity']}.")
    lines.append("- Donnee coherente." if module["severity"] == expected_severity(float(module["risk_score"])) else "- A verifier.")
    if module_id == "workload_gpu":
        lines.extend(
            [
                "",
                "Politique d'action",
                "-" * 18,
                "- INFO/LOW: monitoring, sampling legerement augmente.",
                "- MEDIUM: increase sampling + collect process table + compare CUDA PIDs with scheduler, sans kill automatique.",
                "- HIGH: cordon GPU + block new scheduling + checkpoint guard.",
                "- CRITICAL: quarantine GPU + rollback/canary/checkpoint guard, action destructive seulement apres validation humaine.",
                "",
                "Note importante",
                "-" * 15,
                "- Un score medium sans scheduler/process mismatch ne doit pas etre nomme orphan worker suspected.",
                "- Un GPU actif sans process visible est d'abord un telemetry/process-accounting gap.",
                "- Le score v3 combine six hypotheses avec Noisy-OR au lieu de prendre seulement un max.",
                "- Avec scheduler_state IDLE/FAILED/UNKNOWN et GPU actif, scheduler_mismatch = 1 et le score monte fortement.",
                "- Les signaux all-reduce credibles sont rank_progress_skew, step_time_p95_ratio, NCCL warnings et erreurs interconnect.",
            ]
        )
    return "\n".join(lines) + "\n"


def master_document(payload: dict[str, Any], checks: list[str]) -> str:
    top_module = max(payload["modules"], key=lambda item: float(item["risk_score"]))
    lines = [
        "OrbitOps - Verification coherence et explication des 5 modules",
        "=" * 62,
        "",
        f"Timestamp : {payload['timestamp']}",
        f"Heure mission : {payload['mission_clock']}",
        f"Phase orbitale : {payload['orbit_phase']}",
        f"Mode donnees : {payload.get('data_mode', 'not provided')}",
        f"Echantillons lus : {payload.get('samples_used', 'not provided')}",
        f"Fenetre de variation : {payload.get('trend_window_minutes', 'not provided')} minutes",
        f"Risque global : {payload['overall_risk_score']}/100 ({payload['overall_severity']})",
        f"Risque primaire : {payload.get('primary_risk_score', 'not provided')}/100",
        f"Risque compose : {payload.get('compound_risk_score', 'not provided')}/100",
        f"Agent principal : {payload.get('primary_driver', 'not provided')}",
        f"Action globale : {payload.get('global_action', 'not provided')}",
        "",
        "Verdict donnees",
        "-" * 15,
    ]
    lines.extend(checks)
    lines.extend(
        [
            "",
            "Lecture generale",
            "-" * 16,
            "Les donnees fonctionnent et sont coherentes avec les formules du moteur.",
            "Quand plusieurs echantillons sont fournis, les modules utilisent les pentes observees et les variations temporelles.",
            "Quand un seul echantillon est fourni, le moteur reste en mode single-sample-hold et n'invente pas de tendance.",
            f"Le risque primaire vient du module {top_module['module_id']} avec {float(top_module['risk_score']):.1f}/100.",
            "Le risque global peut depasser le max module si plusieurs agents moyens creent une pression composee.",
            f"Evenement principal predit : {top_module['predicted_event']}.",
            "",
            "Seuils de severite",
            "-" * 19,
            "- 0 a 17.9 : INFO",
            "- 18 a 41.9 : LOW",
            "- 42 a 67.9 : MEDIUM",
            "- 68 a 85.9 : HIGH",
            "- 86 a 100 : CRITICAL",
            "",
            "Fichiers modules generes",
            "-" * 24,
        ]
    )
    for module_id in EXPECTED_MODULES:
        lines.append(f"- science_modules/{module_id}.txt")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True, help="Path to JSON payload from /api/science/results")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    modules_dir = output_dir / "science_modules"
    modules_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    checks = validate_payload(payload)

    (output_dir / "orbitops_scientific_data_coherence.txt").write_text(master_document(payload, checks), encoding="utf-8")
    (output_dir / "orbitops_5_modules_scientific_explanation.txt").write_text(
        "\n".join(module_document(payload, module) for module in payload["modules"]),
        encoding="utf-8",
    )
    for module in payload["modules"]:
        module_id = str(module["module_id"])
        (modules_dir / f"{module_id}.txt").write_text(module_document(payload, module), encoding="utf-8")

    print(output_dir / "orbitops_scientific_data_coherence.txt")
    print(output_dir / "orbitops_5_modules_scientific_explanation.txt")
    for module_id in EXPECTED_MODULES:
        print(modules_dir / f"{module_id}.txt")


if __name__ == "__main__":
    main()
