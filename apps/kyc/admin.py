from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

from .models import KYCSubmission

# ── Email helper ──────────────────────────────────────────────────────────────


def _send_kyc_email(submission: KYCSubmission, action: str) -> None:
    """
    Send a status-update email to the applicant.
    `action` is one of: 'approved', 'rejected', 'resubmit'
    """
    subject_map = {
        "approved": f"[VerifyID] Your KYC verification has been approved — {submission.reference_id}",
        "rejected": f"[VerifyID] Your KYC verification was not successful — {submission.reference_id}",
        "resubmit": f"[VerifyID] Action required: please resubmit your KYC — {submission.reference_id}",
    }

    context = {
        "submission": submission,
        "action": action,
        "support_email": getattr(
            settings, "KYC_SUPPORT_EMAIL", "support@verificationslink.org"
        ),
    }

    html_body = render_to_string(f"kyc/emails/kyc_{action}.html", context)
    text_body = render_to_string(f"kyc/emails/kyc_{action}.txt", context)

    send_mail(
        subject=subject_map[action],
        message=text_body,
        html_message=html_body,
        from_email=getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@verificationslink.org"
        ),
        recipient_list=[submission.email],
        fail_silently=False,
    )


# ── Bulk actions (list view checkboxes) ───────────────────────────────────────


def _bulk_action(action: str, status: str):
    def bulk(modeladmin, request, queryset):
        updated, errors = 0, []
        for obj in queryset:
            try:
                obj.status = status
                obj.save(update_fields=["status", "updated_at"])
                _send_kyc_email(obj, action)
                updated += 1
            except Exception as exc:
                errors.append(f"{obj.reference_id}: {exc}")
        if updated:
            modeladmin.message_user(
                request,
                f"{updated} submission(s) marked as '{status}' and notified by email.",
                messages.SUCCESS,
            )
        for err in errors:
            modeladmin.message_user(request, f"Email error — {err}", messages.WARNING)

    bulk.short_description = {
        "approved": "✅  Approve selected  (sends approval email)",
        "rejected": "❌  Reject selected   (sends rejection email)",
        "resubmit": "🔄  Request resubmission (sends resubmit email)",
    }[action]
    bulk.__name__ = f"bulk_{action}"
    return bulk


bulk_approve = _bulk_action("approved", KYCSubmission.Status.APPROVED)
bulk_reject = _bulk_action("rejected", KYCSubmission.Status.REJECTED)
bulk_resubmit = _bulk_action("resubmit", KYCSubmission.Status.REQUIRES_RESUBMISSION)


# ── Admin class ───────────────────────────────────────────────────────────────


@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):

    list_display = (
        "reference_id",
        "full_name",
        "email",
        "id_type",
        "status_badge",
        "submitted_at",
        "action_buttons",
    )
    list_filter = ("status", "id_type", "nationality")
    search_fields = ("first_name", "last_name", "email", "reference_id", "id_number")
    ordering = ("-submitted_at",)
    actions = [bulk_approve, bulk_reject, bulk_resubmit]

    readonly_fields = (
        "id",
        "reference_id",
        "submitted_at",
        "updated_at",
        "id_front_preview",
        "id_back_preview",
        "liveness_video_player",
    )

    # Points to our custom change-form template that injects the action buttons
    change_form_template = "admin/kyc_app/kycsubmission/change_form.html"

    fieldsets = (
        (
            "Review Decision",
            {
                "fields": ("status", "reviewer_notes"),
                "description": (
                    "Use the Approve / Reject / Resubmit buttons at the top of this page. "
                    "The applicant will receive an email automatically on each action. "
                    "You may also change 'Status' manually here and save without sending an email."
                ),
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "date_of_birth",
                    "nationality",
                    "email",
                )
            },
        ),
        (
            "ID Document",
            {
                "fields": (
                    "id_type",
                    "id_number",
                    "id_expiry",
                    "id_front",
                    "id_front_preview",
                    "id_back",
                    "id_back_preview",
                )
            },
        ),
        (
            "Liveness Video",
            {"fields": ("liveness_video", "liveness_video_player")},
        ),
        (
            "Identifiers & Timestamps",
            {
                "fields": ("id", "reference_id", "submitted_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # ── Custom URLs for per-object action endpoints ───────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<uuid:pk>/approve/",
                self.admin_site.admin_view(self.approve_view),
                name="kyc_kycsubmission_approve",
            ),
            path(
                "<uuid:pk>/reject/",
                self.admin_site.admin_view(self.reject_view),
                name="kyc_kycsubmission_reject",
            ),
            path(
                "<uuid:pk>/resubmit/",
                self.admin_site.admin_view(self.resubmit_view),
                name="kyc_kycsubmission_resubmit",
            ),
        ]
        return custom + urls  # custom BEFORE default so <uuid> doesn't clash

    # ── Per-object action views ───────────────────────────────────────────────

    def _handle_action(self, request, pk, new_status, action, success_msg):
        obj = KYCSubmission.objects.get(pk=pk)
        obj.status = new_status
        obj.save(update_fields=["status", "updated_at"])
        try:
            _send_kyc_email(obj, action)
            self.message_user(request, success_msg, messages.SUCCESS)
        except Exception as exc:
            self.message_user(
                request,
                f"Status updated but email failed: {exc}",
                messages.WARNING,
            )
        return HttpResponseRedirect(
            reverse("admin:kyc_app_kycsubmission_change", args=[pk])
        )

    def approve_view(self, request, pk):
        return self._handle_action(
            request,
            pk,
            KYCSubmission.Status.APPROVED,
            "approved",
            "✅ Submission approved — approval email sent to applicant.",
        )

    def reject_view(self, request, pk):
        return self._handle_action(
            request,
            pk,
            KYCSubmission.Status.REJECTED,
            "rejected",
            "❌ Submission rejected — rejection email sent to applicant.",
        )

    def resubmit_view(self, request, pk):
        return self._handle_action(
            request,
            pk,
            KYCSubmission.Status.REQUIRES_RESUBMISSION,
            "resubmit",
            "🔄 Resubmission requested — notification email sent to applicant.",
        )

    # ── List-view columns ─────────────────────────────────────────────────────

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "pending": ("#ffb020", "#2a1f00"),
            "approved": ("#00d084", "#001a0e"),
            "rejected": ("#ff4757", "#1a0005"),
            "resubmit": ("#2e7fff", "#00103a"),
        }
        bg, fg = colours.get(obj.status, ("#888", "#fff"))
        return format_html(
            '<span style="background:{};color:{};padding:3px 12px;border-radius:100px;'
            'font-size:11px;font-weight:700;letter-spacing:.06em;white-space:nowrap">{}</span>',
            bg,
            fg,
            obj.get_status_display(),
        )

    @admin.display(description="Quick Actions")
    def action_buttons(self, obj):
        approve_url = reverse("admin:kyc_kycsubmission_approve", args=[obj.pk])
        reject_url = reverse("admin:kyc_kycsubmission_reject", args=[obj.pk])
        resubmit_url = reverse("admin:kyc_kycsubmission_resubmit", args=[obj.pk])
        s = (
            "display:inline-block;padding:3px 10px;border-radius:6px;"
            "font-size:11px;font-weight:600;text-decoration:none;margin:1px;cursor:pointer;"
        )
        return format_html(
            '<a href="{}" style="{}background:#00d08422;color:#00d084;border:1px solid #00d08455">✓ Approve</a>'
            '<a href="{}" style="{}background:#ff475722;color:#ff4757;border:1px solid #ff475755">✕ Reject</a>'
            '<a href="{}" style="{}background:#2e7fff22;color:#2e7fff;border:1px solid #2e7fff55">↺ Resubmit</a>',
            approve_url,
            s,
            reject_url,
            s,
            resubmit_url,
            s,
        )

    # ── Detail-view previews ──────────────────────────────────────────────────

    @admin.display(description="Front Image Preview")
    def id_front_preview(self, obj):
        if obj.id_front:
            return format_html(
                '<img src="{}" style="max-width:420px;max-height:280px;'
                'border-radius:8px;border:1px solid #444;margin-top:6px">',
                obj.id_front.url,
            )
        return "—"

    @admin.display(description="Back Image Preview")
    def id_back_preview(self, obj):
        if obj.id_back:
            return format_html(
                '<img src="{}" style="max-width:420px;max-height:280px;'
                'border-radius:8px;border:1px solid #444;margin-top:6px">',
                obj.id_back.url,
            )
        return "—"

    @admin.display(description="Video Player")
    def liveness_video_player(self, obj):
        if obj.liveness_video:
            return format_html(
                '<video controls style="max-width:420px;border-radius:8px;'
                'border:1px solid #444;margin-top:6px">'
                '<source src="{}"></video>',
                obj.liveness_video.url,
            )
        return "—"

    # ── Pass button URLs to the change-form template context ─────────────────

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["approve_url"] = reverse(
            "admin:kyc_kycsubmission_approve", args=[object_id]
        )
        extra_context["reject_url"] = reverse(
            "admin:kyc_kycsubmission_reject", args=[object_id]
        )
        extra_context["resubmit_url"] = reverse(
            "admin:kyc_kycsubmission_resubmit", args=[object_id]
        )
        return super().change_view(request, object_id, form_url, extra_context)
