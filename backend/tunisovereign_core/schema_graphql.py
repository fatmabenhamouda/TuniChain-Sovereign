
import strawberry
from typing import List, Optional
from strawberry.dataloader import DataLoader
from strawberry.types import Info
from asgiref.sync import sync_to_async

from tunisovereign_core.models import (
    CooperativeUnit,
    AgentLoopExecution,
)


@strawberry.type
class ZKReceiptType:
    zk_commitment_hash: str
    tx_hash: str
    block_number: int
    network_name: str
    is_verified_on_chain: bool


@strawberry.type
class AgentExecutionType:
    thread_id: str
    trigger_source: str
    darja_transcript: str
    final_recommendation: str
    confidence_score: float
    zk_receipt: Optional[ZKReceiptType]


@strawberry.type
class GovernorateCoopGraphType:
    name: str
    governorate: str
    track_domain: str
    daily_quota_limit: float
    recent_agent_executions: List[AgentExecutionType]


@sync_to_async
def batch_load_executions(coop_ids: List[str]):
    executions = (
    AgentLoopExecution.objects
        .filter(coop_id__in=coop_ids)
        .select_related("zk_receipt")
        .order_by("-created_at")
    )
        
    results = {str(coop_id): [] for coop_id in coop_ids}

    for execution in executions:
        receipt = getattr(execution, "zk_receipt", None)

        receipt_data = None
        if receipt:
            receipt_data = ZKReceiptType(
                zk_commitment_hash=receipt.zk_commitment_hash,
                tx_hash=receipt.tx_hash,
                block_number=receipt.block_number,
                network_name=receipt.network_name,
                is_verified_on_chain=receipt.is_verified_on_chain,
            )

        results[str(execution.coop_id)].append(
            AgentExecutionType(
                thread_id=execution.thread_id,
                trigger_source=execution.trigger_source,
                darja_transcript=execution.darja_transcript,
                final_recommendation=execution.final_recommendation,
                confidence_score=execution.confidence_score,
                zk_receipt=receipt_data,
            )
        )

    return [results[str(coop_id)] for coop_id in coop_ids]


@strawberry.type
class Query:

    @strawberry.field
    async def governorate_cooperatives(
        self,
        info: Info,
        governorate: Optional[str] = None,
    ) -> List[GovernorateCoopGraphType]:

        cooperatives = await sync_to_async(
            lambda: list(
                CooperativeUnit.objects.filter(
                    **({"governorate__iexact": governorate} if governorate else {})
                )
            )
        )()

        loader = DataLoader(load_fn=batch_load_executions)

        executions_by_coop = await loader.load_many(
            [str(coop.id) for coop in cooperatives]
        )

        return [
            GovernorateCoopGraphType(
                name=coop.name,
                governorate=coop.governorate,
                track_domain=coop.track_domain,
                daily_quota_limit=coop.daily_quota_limit,
                recent_agent_executions=executions,
            )
            for coop, executions in zip(cooperatives, executions_by_coop)
        ]


schema = strawberry.Schema(query=Query)
