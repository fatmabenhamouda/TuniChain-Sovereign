"""
Django 6 REST API Layer (Django REST Framework + SimpleJWT)
Exposes:
- POST /api/auth/register/ and POST /api/auth/login/ (Custom JWT claims: role, governorate, wallet_address)
- GET/POST /api/v1/cooperatives/, /api/v1/telemetry/, /api/v1/anomalies/, /api/v1/zk-receipts/
- POST /api/v1/darja-intent/ (Ingests Tunisian Darja voice transcript or text and triggers LangGraph loop)
"""
from rest_framework import serializers, viewsets, permissions, status, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    StakeholderUser,
    CooperativeUnit,
    ResourceNodePlot,
    TelemetryReading,
    AnomalyAndForecastEvent,
    AgentLoopExecution,
    OnChainZKReceipt,
)
from agent.langgraph_agent import run_sovereign_agent_loop

# ============================================================================
# 0. User Registration Serializer
# ============================================================================
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8
    )

    class Meta:
        model = StakeholderUser
        fields = ("username", "email", "password")

    def create(self, validated_data):
        user = StakeholderUser(
            username=validated_data["username"],
            email=validated_data["email"],
            role=StakeholderUser.Role.COOP_MEMBER,
        )
        user.set_password(validated_data["password"])
        user.save()
        return user

# ============================================================================
# 0. User Registration View
# ============================================================================
class RegisterView(generics.CreateAPIView):
    queryset = StakeholderUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

# ============================================================================
# 1. Custom SimpleJWT Claims Serializer (Role, Governorate & Wallet Address)
# ============================================================================
class SovereignTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user: StakeholderUser):
        token = super().get_token(user)
        token["role"] = user.role
        token["governorate"] = user.governorate
        token["wallet_address"] = user.wallet_address or ""
        token["preferred_dialect"] = user.preferred_dialect
        return token


class SovereignTokenObtainPairView(TokenObtainPairView):
    serializer_class = SovereignTokenObtainPairSerializer


# ============================================================================
# 2. Role-Based Permission Classes
# ============================================================================
class IsCoopMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)



class IsRegionalAuditor(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role in ("REGIONAL_AUDITOR", "NATIONAL_ADMIN")
            and request.method in permissions.SAFE_METHODS
        )



class IsNationalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "NATIONAL_ADMIN"
        )

class ZKReceiptPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role in (
                "COOP_MEMBER",
                "REGIONAL_AUDITOR",
                "NATIONAL_ADMIN",
            )
            and request.method in permissions.SAFE_METHODS
        )

class CooperativeUnitPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.role == "NATIONAL_ADMIN":
            return True

        if user.role in ("COOP_MEMBER", "REGIONAL_AUDITOR"):
            return request.method in permissions.SAFE_METHODS

        return False

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role == "NATIONAL_ADMIN":
            return True

        if user.role == "COOP_MEMBER":
            return obj.memberships.filter(
                user=user,
                is_active=True
            ).exists()

        if user.role == "REGIONAL_AUDITOR":
            return obj.governorate == user.governorate

        return False


class TelemetryReadingPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.role in (
            "COOP_MEMBER",
            "REGIONAL_AUDITOR",
            "NATIONAL_ADMIN",
        ):
            return request.method in permissions.SAFE_METHODS

        return False



# ============================================================================
# 3. Model Serializers
# ============================================================================
class CooperativeUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CooperativeUnit
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class ResourceNodePlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceNodePlot
        fields = "__all__"
        read_only_fields = ("id", "owner", "coop")


class TelemetryReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryReading
        fields = "__all__"
        read_only_fields = ("id", "timestamp", "value", "ingestion_protocol")


class AnomalyAndForecastEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnomalyAndForecastEvent
        fields = "__all__"
        read_only_fields = (
            "id",
            "node",
            "detected_at",
            "anomaly_type",
            "severity",
            "isolation_forest_score",
            "forecasted_deficit_24h",
        )


class OnChainZKReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnChainZKReceipt
        fields = "__all__"
        read_only_fields = (
            "id",
            "agent_execution",
            "zk_commitment_hash",
            "public_inputs_json",
            "tx_hash",
            "block_number",
            "network_name",
            "is_verified_on_chain",
        )


class AgentLoopExecutionSerializer(serializers.ModelSerializer):
    zk_receipt = OnChainZKReceiptSerializer(read_only=True)

    class Meta:
        model = AgentLoopExecution
        fields = "__all__"
        read_only_fields = (
            "id",
            "coop",
            "node",
            "thread_id",
            "trigger_source",
            "darja_transcript",
            "parsed_intent_json",
            "mcp_tools_invoked",
            "skills_executed",
            "final_recommendation",
            "confidence_score",
            "created_at",
        )



# ============================================================================
# 4. DRF ViewSets & Darja Intent Webhook
# ============================================================================

class CooperativeUnitViewSet(viewsets.ModelViewSet):
    serializer_class = CooperativeUnitSerializer
    permission_classes = [CooperativeUnitPermission]

    def get_queryset(self):
        user = self.request.user

        if user.role == "NATIONAL_ADMIN":
            return CooperativeUnit.objects.all().order_by("-created_at")

        if user.role == "COOP_MEMBER":
            return CooperativeUnit.objects.filter(
                memberships__user=user,
                memberships__is_active=True
            ).distinct().order_by("-created_at")

        if user.role == "REGIONAL_AUDITOR":
            return CooperativeUnit.objects.filter(
                governorate=user.governorate
            ).order_by("-created_at")

        return CooperativeUnit.objects.none()




class TelemetryReadingViewSet(viewsets.ModelViewSet):
    serializer_class = TelemetryReadingSerializer
    permission_classes = [TelemetryReadingPermission]

    def get_queryset(self):
        user = self.request.user

        queryset = TelemetryReading.objects.select_related(
            "node",
            "node__coop",
        ).order_by("-timestamp")

        if user.role == "NATIONAL_ADMIN":
            return queryset

        if user.role == "COOP_MEMBER":
            return queryset.filter(
                node__coop__memberships__user=user,
                node__coop__memberships__is_active=True,
            ).distinct()

        if user.role == "REGIONAL_AUDITOR":
            return queryset.filter(
                node__coop__governorate=user.governorate
            )

        return queryset.none()



class AnomalyAndForecastEventViewSet(viewsets.ModelViewSet):
    serializer_class = AnomalyAndForecastEventSerializer
    permission_classes = [IsRegionalAuditor]

    def get_queryset(self):
        user = self.request.user

        queryset = AnomalyAndForecastEvent.objects.select_related(
            "node",
            "node__coop",
        ).order_by("-detected_at")

        if user.role == "NATIONAL_ADMIN":
            return queryset

        if user.role == "REGIONAL_AUDITOR":
            return queryset.filter(
                node__coop__governorate=user.governorate
            )

        return queryset.none()



class OnChainZKReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OnChainZKReceiptSerializer
    permission_classes = [ZKReceiptPermission]

    def get_queryset(self):
        user = self.request.user

        queryset = OnChainZKReceipt.objects.select_related(
            "agent_execution",
            "agent_execution__coop",
        ).order_by("-block_number")

        if user.role == "NATIONAL_ADMIN":
            return queryset

        if user.role == "COOP_MEMBER":
            return queryset.filter(
                agent_execution__coop__memberships__user=user,
                agent_execution__coop__memberships__is_active=True,
            ).distinct()

        if user.role == "REGIONAL_AUDITOR":
            return queryset.filter(
                agent_execution__coop__governorate=user.governorate
            )

        return queryset.none()


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def darja_intent_webhook(request):
    """
    POST /api/v1/darja-intent/
    Accepts a Tunisian Darja transcript and sensor telemetry snapshot,
    executes the stateful LangGraph loop + FastMCP tool + ZK settlement skill,
    and returns the structured execution trace and on-chain receipt.
    """
    payload = request.data
    state_out = run_sovereign_agent_loop({
        "thread_id": payload.get("thread_id", "drf-darja-webhook-001"),
        "node_code": payload.get("node_code", "KAS-SBEITLA-PLOT-04"),
        "darja_input": payload.get(
            "darja_input",
            "Ya khouya fi Kasserine el sonda habtet 28% wel skhana 37 darja, lazmenna maa urgent!",
        ),
        "moisture_pct": float(payload.get("moisture_pct", 28.4)),
        "temp_c": float(payload.get("temp_c", 37.2)),
        "flow_l_min": float(payload.get("flow_l_min", 182.0)),
        "parsed_intent": {},
        "anomaly_report": {},
        "mcp_allocation": {},
        "zk_receipt": {},
        "skills_trace": [],
        "final_explanation": "",
    })
    return Response(state_out, status=status.HTTP_200_OK)
