from django.db import models
import uuid


class KYCSubmission(models.Model):
    """
    Stores a full KYC verification submission across all three steps.
    """

    class IDType(models.TextChoices):
        PASSPORT = "passport", "Passport"
        NATIONAL_ID = "national_id", "National ID Card"
        DRIVERS_LICENCE = "drivers_licence", "Driver's Licence"
        RESIDENCE_PERMIT = "residence_permit", "Residence Permit"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REQUIRES_RESUBMISSION = "resubmit", "Requires Resubmission"

    # ── Identifiers ──────────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_id = models.CharField(max_length=32, unique=True, editable=False)

    # ── Step 1: Personal information ─────────────────────────────────────────
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    nationality = models.CharField(max_length=100)
    email = models.EmailField()

    # ── Step 2: ID document details ───────────────────────────────────────────
    id_type = models.CharField(max_length=30, choices=IDType.choices)
    id_number = models.CharField(max_length=50)
    id_expiry = models.DateField()
    id_front = models.ImageField(upload_to="kyc/id_documents/front/")
    id_back = models.ImageField(
        upload_to="kyc/id_documents/back/",
        blank=True,
        null=True,
        help_text="Optional for passports",
    )

    # ── Step 3: Liveness video ────────────────────────────────────────────────
    liveness_video = models.FileField(upload_to="kyc/liveness_videos/")

    # ── Status & timestamps ───────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    reviewer_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "KYC Submission"
        verbose_name_plural = "KYC Submissions"

    def __str__(self):
        return f"{self.full_name} — {self.reference_id} ({self.get_status_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.reference_id:
            self.reference_id = self._generate_reference_id()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference_id():
        import random, string
        chars = string.ascii_uppercase + string.digits
        suffix = "".join(random.choices(chars, k=8))
        return f"KYC-{suffix}"
