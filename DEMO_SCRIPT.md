# AstroOps Live Demo Script

## Opening

"GPU clusters usually fail gradually before they fail suddenly. Operators already have dashboards. The hard part is knowing which signal matters, what will happen next, and what action is safest. AstroOps Live turns streaming telemetry into operational decisions."

## Demo Steps

1. Open the app and show the normal live cluster map.
2. Select `Multi-domain cascade`.
3. Let the simulation run until R-3 begins degrading.
4. Point out weak signals across thermal, queue, network, and power.
5. Show the situational model and the +5/+10/+15 minute risk forecast.
6. Show candidate actions considered by the agent.
7. Show the Crusoe or mock structured recommendation.
8. Click `Ask Why`.
9. Click `Accept`.
10. Show risk reduction, J-184 migration, R-3 cordon/power cap effect, and timeline entry.
11. Select `Override learning`.
12. Generate or wait for the recommendation.
13. Click `Override` and submit: `Cooling unit C-2 is under maintenance; avoid cooling escalation.`
14. Show the policy memory and the adapted next recommendation.

## Closing

"This is not monitoring. This is a human-in-the-loop operations agent: live state, prediction, action selection, explanation, approval, and adaptation."
