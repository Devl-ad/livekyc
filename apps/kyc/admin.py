from django.contrib import admin
from .models import KYCSubmission


@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "reference_id",
        "full_name",
        "email",
        "id_type",
        "status",
        "submitted_at",
    )
    list_filter = ("status", "id_type", "nationality")
    search_fields = ("first_name", "last_name", "email", "reference_id", "id_number")
    readonly_fields = ("id", "reference_id", "submitted_at", "updated_at")
    ordering = ("-submitted_at",)

    fieldsets = (
        ("Reference", {"fields": ("id", "reference_id", "status", "reviewer_notes")}),
        (
            "Personal Information",
            {"fields": ("first_name", "last_name", "date_of_birth", "nationality", "email")},
        ),
        (
            "ID Document",
            {"fields": ("id_type", "id_number", "id_expiry", "id_front", "id_back")},
        ),
        ("Liveness", {"fields": ("liveness_video",)}),
        ("Timestamps", {"fields": ("submitted_at", "updated_at"), "classes": ("collapse",)}),
    )
