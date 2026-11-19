import os
import sys
from concurrent import futures

import grpc

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tunisovereign_pb2 as pb2
import tunisovereign_pb2_grpc as pb2_grpc

from agent.langgraph_agent import run_sovereign_agent_loop


class TelemetryIngestServicer(pb2_grpc.TelemetryIngestServiceServicer):

    def StreamTelemetry(self, request_iterator, context):
        accepted = 0
        anomaly_triggered = False
        thread_id = ""

        for packet in request_iterator:
            accepted += 1

            if packet.metric_type == "MOISTURE" and packet.value < 35.0:
                anomaly_triggered = True
                thread_id = f"grpc-auto-{packet.node_code}-{accepted}"

                run_sovereign_agent_loop({
                    "thread_id": thread_id,
                    "node_code": packet.node_code,
                    "darja_input": (
                        f"Automated gRPC alert in {packet.governorate}: "
                        f"moisture dropped to {packet.value}%"
                    ),
                    "moisture_pct": float(packet.value),
                    "temp_c": 36.5,
                    "flow_l_min": 180.0,
                    "parsed_intent": {},
                    "anomaly_report": {},
                    "mcp_allocation": {},
                    "zk_receipt": {},
                    "skills_trace": [],
                    "final_explanation": "",
                })

        return pb2.IngestAck(
            accepted_count=accepted,
            anomaly_triggered=anomaly_triggered,
            agent_thread_id=thread_id,
        )

    def TriggerUrgentAudit(self, request, context):
        thread_id = f"grpc-urgent-{request.node_code}"

        res = run_sovereign_agent_loop({
            "thread_id": thread_id,
            "node_code": request.node_code,
            "darja_input": request.reason,
            "moisture_pct": 27.5,
            "temp_c": 37.8,
            "flow_l_min": 185.0,
            "parsed_intent": {},
            "anomaly_report": {},
            "mcp_allocation": {},
            "zk_receipt": {},
            "skills_trace": [],
            "final_explanation": "",
        })

        return pb2.AuditResponse(
            status="VERIFIED_AND_ANCHORED",
            tx_hash=res["zk_receipt"]["tx_hash"],
        )


def serve(port: int = 50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))

    pb2_grpc.add_TelemetryIngestServiceServicer_to_server(
        TelemetryIngestServicer(), server
    )

    server.add_insecure_port(f"[::]:{port}")
    print(f"[TuniSovereign-AI gRPC Server] Listening on port {port}...")

    server.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()