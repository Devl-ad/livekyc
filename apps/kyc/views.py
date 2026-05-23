import os
import uuid
import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .forms import IDDocumentForm, LivenessVideoForm, PersonalInfoForm
from .models import KYCSubmission

logger = logging.getLogger(__name__)

# Temp upload prefix used while the session is in progress
TEMP_PREFIX = "kyc/temp"


def _save_temp_file(uploaded_file, session_key):
    """Save an uploaded file to a temp location; return the storage path."""
    ext = Path(uploaded_file.name).suffix.lower()
    tmp_name = f"{TEMP_PREFIX}/{session_key}_{uuid.uuid4().hex}{ext}"
    path = default_storage.save(tmp_name, ContentFile(uploaded_file.read()))
    uploaded_file.seek(0)  # rewind in case the form re-reads it
    return path


def _delete_temp_file(path):
    """Silently remove a temp file from storage."""
    try:
        if path and default_storage.exists(path):
            default_storage.delete(path)
    except Exception:
        pass


# ── Step 1 ────────────────────────────────────────────────────────────────────


class KYCStep1View(View):
    template_name = "kyc/step1_personal_info.html"

    def get(self, request):
        initial = request.session.get("kyc_step1_data", {})
        form = PersonalInfoForm(initial=initial)
        return render(request, self.template_name, {"form": form, "step": 1})

    def post(self, request):
        form = PersonalInfoForm(request.POST)
        if form.is_valid():
            # Persist serialisable data to session
            request.session["kyc_step1_data"] = {
                "first_name": form.cleaned_data["first_name"],
                "last_name": form.cleaned_data["last_name"],
                "date_of_birth": str(form.cleaned_data["date_of_birth"]),
                "nationality": form.cleaned_data["nationality"],
                "email": form.cleaned_data["email"],
            }
            return redirect(reverse("kyc:step2"))
        return render(request, self.template_name, {"form": form, "step": 1})


# ── Step 2 ────────────────────────────────────────────────────────────────────


class KYCStep2View(View):
    template_name = "kyc/step2_id_document.html"

    def _guard(self, request):
        """Redirect to step 1 if prior step data is missing."""
        if "kyc_step1_data" not in request.session:
            messages.warning(request, "Please complete step 1 first.")
            return redirect(reverse("kyc:step1"))
        return None

    def get(self, request):
        guard = self._guard(request)
        if guard:
            return guard
        initial = request.session.get("kyc_step2_data", {})
        form = IDDocumentForm(initial=initial)
        return render(request, self.template_name, {"form": form, "step": 2})

    def post(self, request):
        guard = self._guard(request)
        if guard:
            return guard

        form = IDDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            # Delete previously uploaded temp files for this session
            _delete_temp_file(request.session.pop("kyc_step2_front", None))
            _delete_temp_file(request.session.pop("kyc_step2_back", None))

            # Save new temp files and record paths in session
            front_path = _save_temp_file(form.cleaned_data["id_front"], "front")
            request.session["kyc_step2_front"] = front_path

            if form.cleaned_data.get("id_back"):
                back_path = _save_temp_file(form.cleaned_data["id_back"], "back")
                request.session["kyc_step2_back"] = back_path

            request.session["kyc_step2_data"] = {
                "id_type": form.cleaned_data["id_type"],
                "id_number": form.cleaned_data["id_number"],
                "id_expiry": str(form.cleaned_data["id_expiry"]),
            }
            return redirect(reverse("kyc:step3"))
        return render(request, self.template_name, {"form": form, "step": 2})


# ── Step 3 ────────────────────────────────────────────────────────────────────


class KYCStep3View(View):
    template_name = "kyc/step3_liveness.html"

    def _guard(self, request):
        if "kyc_step1_data" not in request.session:
            messages.warning(request, "Please complete step 1 first.")
            return redirect(reverse("kyc:step1"))
        if "kyc_step2_data" not in request.session:
            messages.warning(request, "Please complete step 2 first.")
            return redirect(reverse("kyc:step2"))
        return None

    def get(self, request):
        guard = self._guard(request)
        if guard:
            return guard
        form = LivenessVideoForm()
        return render(request, self.template_name, {"form": form, "step": 3})

    def post(self, request):
        guard = self._guard(request)
        if guard:
            return guard

        form = LivenessVideoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                submission = self._build_submission(request, form)
                self._clear_session(request)
                return redirect(reverse("kyc:success", args=[submission.pk]))
            except Exception as exc:
                logger.exception("Failed to create KYC submission: %s", exc)
                messages.error(
                    request,
                    "An error occurred while saving your submission. Please try again.",
                )
        return render(request, self.template_name, {"form": form, "step": 3})

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_submission(self, request, form):
        """Assemble all session data + uploaded files into a KYCSubmission."""
        from django.core.files import File
        from datetime import date

        step1 = request.session["kyc_step1_data"]
        step2 = request.session["kyc_step2_data"]

        submission = KYCSubmission(
            # Step 1
            first_name=step1["first_name"],
            last_name=step1["last_name"],
            date_of_birth=step1["date_of_birth"],
            nationality=step1["nationality"],
            email=step1["email"],
            # Step 2 text fields
            id_type=step2["id_type"],
            id_number=step2["id_number"],
            id_expiry=step2["id_expiry"],
        )

        # Attach front ID image from temp storage
        front_path = request.session.get("kyc_step2_front")
        if front_path and default_storage.exists(front_path):
            with default_storage.open(front_path) as fh:
                fname = os.path.basename(front_path)
                submission.id_front.save(fname, File(fh), save=False)

        # Attach back ID image from temp storage (optional)
        back_path = request.session.get("kyc_step2_back")
        if back_path and default_storage.exists(back_path):
            with default_storage.open(back_path) as fh:
                fname = os.path.basename(back_path)
                submission.id_back.save(fname, File(fh), save=False)

        # Attach liveness video directly from the current upload
        video_file = form.cleaned_data["liveness_video"]
        submission.liveness_video.save(video_file.name, video_file, save=False)

        submission.save()

        # Clean up temp files after successful save
        _delete_temp_file(front_path)
        _delete_temp_file(back_path)

        return submission

    def _clear_session(self, request):
        for key in (
            "kyc_step1_data",
            "kyc_step2_data",
            "kyc_step2_front",
            "kyc_step2_back",
        ):
            request.session.pop(key, None)


# ── Success ───────────────────────────────────────────────────────────────────


class KYCSuccessView(View):
    template_name = "kyc/success.html"

    def get(self, request, pk):
        try:
            submission = KYCSubmission.objects.get(pk=pk)
        except KYCSubmission.DoesNotExist:
            messages.error(request, "Submission not found.")
            return redirect(reverse("kyc:step1"))
        return render(request, self.template_name, {"submission": submission})
