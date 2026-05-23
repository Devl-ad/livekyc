from django.urls import path
from . import views

app_name = "kyc"

urlpatterns = [
    path("",          views.KYCStep1View.as_view(), name="step1"),
    path("step/2/",   views.KYCStep2View.as_view(), name="step2"),
    path("step/3/",   views.KYCStep3View.as_view(), name="step3"),
    path("success/<uuid:pk>/", views.KYCSuccessView.as_view(), name="success"),
]
