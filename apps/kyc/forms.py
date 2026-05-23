from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date

from .models import KYCSubmission

# ── Helpers ───────────────────────────────────────────────────────────────────

ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")
ALLOWED_VIDEO_TYPES = ("video/webm", "video/mp4", "video/ogg")
MAX_IMAGE_SIZE_MB = 10
MAX_VIDEO_SIZE_MB = 50


def _check_file_size(file, max_mb):
    if file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"File size must not exceed {max_mb} MB.")


def _check_content_type(file, allowed):
    ct = getattr(file, "content_type", "")
    if ct and ct not in allowed:
        raise ValidationError(
            f"Invalid file type '{ct}'. Allowed: {', '.join(allowed)}."
        )


# ── Step 1: Personal information ──────────────────────────────────────────────

class PersonalInfoForm(forms.ModelForm):
    class Meta:
        model = KYCSubmission
        fields = ["first_name", "last_name", "date_of_birth", "nationality", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "As on ID"}),
            "last_name": forms.TextInput(attrs={"placeholder": "As on ID"}),
            "date_of_birth": forms.DateInput(
                attrs={"type": "date", "max": str(date.today())}
            ),
            "nationality": forms.Select(
                choices=[
                    ("", "Select country"),
                    ("Australia", "Australia"),
                    ("Canada", "Canada"),
                    ("France", "France"),
                    ("Germany", "Germany"),
                    ("India", "India"),
                    ("Japan", "Japan"),
                    ("Singapore", "Singapore"),
                    ("United Kingdom", "United Kingdom"),
                    ("United States", "United States"),
                    ("Other", "Other"),
                ]
            ),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com"}),
        }

    def clean_first_name(self):
        value = self.cleaned_data["first_name"].strip()
        if len(value) < 2:
            raise ValidationError("First name must be at least 2 characters.")
        return value.title()

    def clean_last_name(self):
        value = self.cleaned_data["last_name"].strip()
        if len(value) < 2:
            raise ValidationError("Last name must be at least 2 characters.")
        return value.title()

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            raise ValidationError("You must be at least 18 years old.")
        if dob > today:
            raise ValidationError("Date of birth cannot be in the future.")
        return dob


# ── Step 2: ID document ───────────────────────────────────────────────────────

class IDDocumentForm(forms.ModelForm):
    class Meta:
        model = KYCSubmission
        fields = ["id_type", "id_number", "id_expiry", "id_front", "id_back"]
        widgets = {
            "id_type": forms.Select(
                choices=[("", "Select document type")] + list(KYCSubmission.IDType.choices)
            ),
            "id_number": forms.TextInput(attrs={"placeholder": "e.g. P12345678"}),
            "id_expiry": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_id_number(self):
        value = self.cleaned_data["id_number"].strip().upper()
        if len(value) < 4:
            raise ValidationError("Document number must be at least 4 characters.")
        return value

    def clean_id_expiry(self):
        expiry = self.cleaned_data["id_expiry"]
        if expiry < date.today():
            raise ValidationError("This ID document has expired.")
        return expiry

    def clean_id_front(self):
        f = self.cleaned_data.get("id_front")
        if f:
            _check_content_type(f, ALLOWED_IMAGE_TYPES)
            _check_file_size(f, MAX_IMAGE_SIZE_MB)
        return f

    def clean_id_back(self):
        f = self.cleaned_data.get("id_back")
        if f:
            _check_content_type(f, ALLOWED_IMAGE_TYPES)
            _check_file_size(f, MAX_IMAGE_SIZE_MB)
        return f


# ── Step 3: Liveness video ────────────────────────────────────────────────────

class LivenessVideoForm(forms.ModelForm):
    class Meta:
        model = KYCSubmission
        fields = ["liveness_video"]
        widgets = {
            "liveness_video": forms.FileInput(
                attrs={"accept": "video/webm,video/mp4,video/ogg"}
            ),
        }

    def clean_liveness_video(self):
        f = self.cleaned_data.get("liveness_video")
        if not f:
            raise ValidationError("Liveness video is required.")
        _check_content_type(f, ALLOWED_VIDEO_TYPES)
        _check_file_size(f, MAX_VIDEO_SIZE_MB)
        return f
