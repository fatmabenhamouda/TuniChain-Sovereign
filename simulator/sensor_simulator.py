"""
Simulateur de capteurs TunicChain-Sovereign (Track 1: eau / agriculture).

- Cycle jour/nuit pour la temperature, l'humidite du sol et le debit.
- Anomalies injectees de facon reproductible (meme --seed = memes anomalies).
- Sortie CSV avec les colonnes is_anomaly et anomaly_type (pour le ML de P3).
- Envoi optionnel au serveur gRPC (--send).

Unites: MOISTURE en %, TEMP en degres C, FLOW en L/min, timestamps en UTC ISO 8601.
"""
import argparse
import csv
import math
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

NODES = [
    ("NODE-001", "Kasserine"),
    ("NODE-002", "Kasserine"),
    ("NODE-003", "Sidi Bouzid"),
]
STEP_MIN = 30                      # une mesure toutes les 30 minutes
STEPS_PER_DAY = 24 * 60 // STEP_MIN
UNITS = {"MOISTURE": "%", "TEMP": "C", "FLOW": "L/min"}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def generate(seed, days, start):
    """Retourne la liste des lignes (dict) triees par date puis par capteur."""
    rng = random.Random(seed)          # generateur local: resultat reproductible
    steps = days * STEPS_PER_DAY
    rows = []

    for node_code, governorate in NODES:
        base_moisture = 55 + rng.uniform(-3, 3)
        moisture, temp, flow = [], [], []

        # 1) Donnees normales avec cycle jour/nuit (pic de chaleur vers 15h)
        for i in range(steps):
            t = start + timedelta(minutes=i * STEP_MIN)
            h = t.hour + t.minute / 60
            wave = math.sin(2 * math.pi * (h - 9) / 24)
            temp.append(26 + 9 * wave + rng.gauss(0, 0.4))
            moisture.append(base_moisture - 7 * max(0.0, wave) + rng.gauss(0, 0.5))
            pumping = (6 <= h < 10) or (18 <= h < 20)
            flow.append((6.0 if pumping else 0.3) + rng.gauss(0, 0.2))

        # 2) Injection d'anomalies: au plus une par jour et par capteur
        labels = [""] * steps
        for day in range(days):
            if rng.random() > 0.7:
                continue
            first = day * STEPS_PER_DAY + rng.randint(20, 34)   # entre 10h et 17h
            kind = rng.choice(["MOISTURE_DROP", "HEAT_STRESS"])
            for k in range(6):                                  # 6 pas = 3 heures
                i = first + k
                ramp = min(1.0, (k + 1) / 4)                    # descente sur 2 heures
                if kind == "MOISTURE_DROP":                     # fuite ou vol d'eau
                    moisture[i] -= rng.uniform(14, 20) * ramp
                    flow[i] += rng.uniform(5, 9)
                else:                                           # chaleur (sirocco)
                    temp[i] += 9
                    moisture[i] -= rng.uniform(22, 26) * ramp
                labels[i] = kind

        # 3) Mise en lignes
        for i in range(steps):
            ts = (start + timedelta(minutes=i * STEP_MIN)).isoformat()
            for metric, series in (("MOISTURE", moisture), ("TEMP", temp), ("FLOW", flow)):
                value = series[i]
                if metric == "MOISTURE":
                    value = clamp(value, 0.0, 100.0)
                if metric == "FLOW":
                    value = max(0.0, value)
                rows.append({
                    "node_code": node_code,
                    "governorate": governorate,
                    "timestamp": ts,
                    "metric_type": metric,
                    "value": round(value, 2),
                    "unit": UNITS[metric],
                    "is_anomaly": 1 if labels[i] else 0,
                    "anomaly_type": labels[i],
                })

    rows.sort(key=lambda r: (r["timestamp"], r["node_code"], r["metric_type"]))
    return rows


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def send_grpc(rows, address, delay):
    """Envoie les lignes au serveur gRPC (StreamTelemetry)."""
    import grpc
    sys.path.append(str(Path(__file__).resolve().parent.parent / "grpc_service"))
    import tunisovereign_pb2 as pb2
    import tunisovereign_pb2_grpc as pb2_grpc

    def packets():
        for r in rows:
            yield pb2.TelemetryPacket(
                node_code=r["node_code"],
                governorate=r["governorate"],
                metric_type=r["metric_type"],
                value=r["value"],
                iso_timestamp=r["timestamp"],
                signature_hmac="simulator",
            )
            if delay:
                time.sleep(delay)

    with grpc.insecure_channel(address) as channel:
        stub = pb2_grpc.TelemetryIngestServiceStub(channel)
        return stub.StreamTelemetry(packets())


def main():
    parser = argparse.ArgumentParser(description="Simulateur de capteurs TunicChain")
    parser.add_argument("--seed", type=int, default=42, help="graine (reproductibilite)")
    parser.add_argument("--days", type=int, default=3, help="nombre de jours simules")
    parser.add_argument("--out", default="simulator/output/simulated_telemetry.csv")
    parser.add_argument("--send", action="store_true", help="envoyer au serveur gRPC")
    parser.add_argument("--addr", default="127.0.0.1:50051")
    parser.add_argument("--delay", type=float, default=0.0, help="pause entre paquets (s)")
    parser.add_argument("--limit", type=int, default=0, help="envoyer seulement N paquets (0 = tous)")
    args = parser.parse_args()

    start = datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc)
    rows = generate(args.seed, args.days, start)
    write_csv(rows, args.out)

    anomaly_rows = [r for r in rows if r["is_anomaly"]]
    kinds = Counter(r["anomaly_type"] for r in anomaly_rows)
    print(f"{len(rows)} mesures ecrites dans {args.out} (seed={args.seed}, jours={args.days})")
    print(f"Mesures en anomalie: {len(anomaly_rows)} ({dict(kinds)})")

    if args.send:
        to_send = rows[: args.limit] if args.limit else rows
        ack = send_grpc(to_send, args.addr, args.delay)
        print(f"Envoi gRPC termine: {len(to_send)} paquets envoyes")
        print("Reponse du serveur:")
        print(ack)


if __name__ == "__main__":
    main()