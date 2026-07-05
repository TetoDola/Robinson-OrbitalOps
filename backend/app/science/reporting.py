from __future__ import annotations

from .types import ScientificAssessment


def format_scientific_report(assessment: ScientificAssessment) -> str:
    lines = [
        "OrbitOps - Modules de calcul et prediction",
        "=" * 44,
        "",
        f"Horodatage simulation : {assessment.timestamp}",
        f"Heure mission : {assessment.mission_clock}",
        f"Phase orbitale : {assessment.orbit_phase}",
        f"Mode donnees : {assessment.data_mode}",
        f"Echantillons lus : {assessment.samples_used}",
        f"Fenetre de variation : {assessment.trend_window_minutes:.1f} minutes",
        f"Risque global : {assessment.overall_risk_score:.1f}/100 ({assessment.overall_severity.value})",
        f"Risque primaire : {assessment.primary_risk_score:.1f}/100",
        f"Risque compose : {assessment.compound_risk_score:.1f}/100",
        f"Agent principal : {assessment.primary_driver}",
        f"Action globale : {assessment.global_action}",
        "",
        "Resultats des 5 modules",
        "-" * 24,
    ]

    for index, module in enumerate(assessment.modules, start=1):
        lines.extend(
            [
                "",
                f"{index}. {module.module_name}",
                f"   Resultat : {module.result}",
                f"   Evenement predit : {module.predicted_event}",
                f"   Niveau action : {module.action_level}",
                f"   Resume dashboard : {module.dashboard_summary}",
                f"   Risque : {module.risk_score:.1f}/100 ({module.severity.value})",
                f"   Confiance : {module.confidence:.2f}",
                f"   Horizon : {module.prediction_horizon_minutes} minutes",
                f"   Decision recommandee : {module.recommended_decision}",
                f"   Validation humaine requise : {'oui' if module.requires_human_approval else 'non'}",
                "   Preuves :",
            ]
        )
        for key, value in module.evidence.items():
            lines.append(f"   - {key}: {value}")
        lines.extend(
            [
                "   Actions recommandees :",
            ]
        )
        for action in module.recommended_actions:
            approval = "approval" if action.get("approval") else "auto"
            value = f" | value={action.get('value')}" if "value" in action else ""
            target = f" | target={action.get('target')}" if "target" in action else ""
            lines.append(f"   - {action.get('type')} ({approval}){value}{target}: {action.get('reason')}")
        lines.extend(
            [
                "   Mesures calculees :",
            ]
        )
        for metric in module.metrics:
            unit = f" {metric.unit}" if metric.unit else ""
            lines.append(f"   - {metric.name}: {metric.value}{unit} | {metric.interpretation}")
        lines.append("   Formules / raisonnement :")
        for formula in module.formula_summary:
            lines.append(f"   - {formula}")

    lines.extend(
        [
            "",
            "Pourquoi ces calculs ?",
            "-" * 21,
            "Les modules ne cherchent pas a produire une interface : ils transforment la telemetrie brute en scores numeriques,",
            "variations temporelles, predictions courtes et decisions operationnelles. Les formules sont volontairement deterministes",
            "pour etre auditables : on peut relire chaque risque a partir des valeurs physiques mesurees.",
            "",
            "Hypotheses principales",
            "-" * 22,
            "- Le moteur lit une serie de donnees; avec au moins deux points, il calcule des pentes par heure et extrapole l'horizon.",
            "- Avec un seul point, il passe en mode single-sample-hold : pas de tendance inventee.",
            "- Pas de simulation haute-fidelite thermique CFD : on utilise une marge thermique, une resistance thermique observee et une tendance.",
            "- Batterie equivalente : 12 kWh, utilisee seulement comme secours quand aucune pente batterie observee n'existe.",
            "- Les phases orbitales viennent des donnees fournies; elles ne sont pas imposees par le moteur scientifique.",
            "- Downlink : capacite GB = Mbps x secondes / 8192, puis priorisation des artefacts les plus utiles au sol.",
            "- Integrite training : modele de risque type Poisson pour convertir dose/ECC en probabilite d'evenement bit-flip.",
        ]
    )
    return "\n".join(lines) + "\n"
