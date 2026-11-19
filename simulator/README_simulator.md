# Simulateur de capteurs (P2)

Génère des mesures fictives mais réalistes pour 3 capteurs (Kasserine, Sidi Bouzid).

- Cycle jour/nuit : température (pic vers 15h), humidité du sol, débit (pompage 6h-10h et 18h-20h)
- Anomalies injectées avec une graine fixe (`--seed`) : résultat reproductible
  - `MOISTURE_DROP` : chute d'humidité de 14 à 20 points en 2 h (fuite ou vol d'eau)
  - `HEAT_STRESS` : température +9 °C et humidité sous 33 %
- Unités : MOISTURE en %, TEMP en °C, FLOW en L/min, timestamps en UTC ISO 8601

## Commandes

```powershell
# Générer le CSV (3 jours, graine 42)
.\.venv\Scripts\python.exe simulator\sensor_simulator.py

# Autre graine ou durée
.\.venv\Scripts\python.exe simulator\sensor_simulator.py --seed 7 --days 5

# Envoyer au serveur gRPC (lancer d'abord grpc_service\server_demo.py)
.\.venv\Scripts\python.exe simulator\sensor_simulator.py --send --limit 30 --delay 0.1
```

## Colonnes du CSV

`node_code, governorate, timestamp, metric_type, value, unit, is_anomaly, anomaly_type`

La colonne `is_anomaly` (0 ou 1) sert à calculer Precision, Recall et F1 pour le ML (P3).