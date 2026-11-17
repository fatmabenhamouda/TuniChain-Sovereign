"""
URL configuration for tunisovereign_config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from tunisovereign_core.api_rest import (
    SovereignTokenObtainPairView,
    CooperativeUnitViewSet,
    TelemetryReadingViewSet,
    AnomalyAndForecastEventViewSet,
    OnChainZKReceiptViewSet,
    darja_intent_webhook,
)

# Router REST API
router = DefaultRouter()
router.register("cooperatives", CooperativeUnitViewSet, basename="cooperative")
router.register("telemetry", TelemetryReadingViewSet, basename="telemetry")
router.register("anomalies", AnomalyAndForecastEventViewSet, basename="anomaly")
router.register("zk-receipts", OnChainZKReceiptViewSet, basename="zk-receipt")

urlpatterns = [
    path("admin/", admin.site.urls),

    # JWT Authentication
    path("api/auth/login/", SovereignTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # REST API
    path("api/v1/", include(router.urls)),

    # AI Agent - Tunisian Darja
    path("api/v1/darja-intent/", darja_intent_webhook, name="darja_intent"),
]

