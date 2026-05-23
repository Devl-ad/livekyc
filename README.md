# VerifyID — Django KYC Verification App

A production-ready, multi-step Know Your Customer (KYC) identity verification app built with Django. Users complete three steps — personal information, ID document upload, and a live video liveness check — before a single database record is committed.

---

## Features

- **3-step wizard** with session-backed state (no partial DB writes until all steps pass)
- **Personal info validation** — age check (18+), name normalisation, email format
- **ID document upload** — front and back images, type/expiry validation, 10 MB file size limit
- **Live video liveness check** — browser `MediaRecorder` captures a 5-second clip with guided face prompts; blob is injected into a hidden file input and POSTed normally
- **Automatic reference ID** generation (`KYC-XXXXXXXX`) on submission
- **Django Admin** panel with search, filter, and status management
- **Step guards** — users are redirected back if they try to skip steps
- **Temp file cleanup** — uploaded images are staged in `kyc/temp/` and moved to permanent storage only on final successful submission

---

## Requirements

- Python 3.10+
- Django 4.2+
- Pillow (for `ImageField`)

```
pip install django pillow
```

---

## Project Structure

```
kyc_project/
├── kyc_app/
│   ├── __init__.py
│   ├── admin.py              # Admin panel registration
│   ├── forms.py              # PersonalInfoForm, IDDocumentForm, LivenessVideoForm
│   ├── models.py             # KYCSubmission model
│   ├── urls.py               # App URL patterns (namespace: kyc)
│   ├── views.py              # Class-based views for each step
│   ├── migrations/
│   └── templates/kyc/
│       ├── base.html         # Shared layout, styles, header
│       ├── _steps_bar.html   # Reusable progress bar partial
│       ├── step1_personal_info.html
│       ├── step2_id_document.html
│       ├── step3_liveness.html
│       └── success.html
├── settings_snippet.py       # Settings you need to add/merge
└── project_urls.py           # How to wire the app into your project urls.py
```

---

## Installation

**1. Copy `kyc_app/` into your Django project.**

**2. Add to `INSTALLED_APPS` in `settings.py`:**

```python
INSTALLED_APPS = [
    # ...existing apps...
    "kyc_app",
]
```

**3. Add media file settings to `settings.py`:**

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

**4. Configure sessions in `settings.py`:**

```python
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 3600       # 1 hour to complete the flow
SESSION_SAVE_EVERY_REQUEST = True
```

**5. Wire the URLs into your project's `urls.py`:**

```python
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("verify/", include("kyc_app.urls", namespace="kyc")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**6. Run migrations:**

```bash
python manage.py makemigrations kyc_app
python manage.py migrate
```

**7. Create a superuser (optional, for admin access):**

```bash
python manage.py createsuperuser
```

**8. Start the development server:**

```bash
python manage.py runserver
```

---

## URL Routes

| URL                       | View             | Name          |
| ------------------------- | ---------------- | ------------- |
| `/verify/`                | `KYCStep1View`   | `kyc:step1`   |
| `/verify/step/2/`         | `KYCStep2View`   | `kyc:step2`   |
| `/verify/step/3/`         | `KYCStep3View`   | `kyc:step3`   |
| `/verify/success/<uuid>/` | `KYCSuccessView` | `kyc:success` |

---

## Model Reference

### `KYCSubmission`

| Field            | Type            | Notes                                                                     |
| ---------------- | --------------- | ------------------------------------------------------------------------- |
| `id`             | `UUIDField`     | Primary key, auto-generated                                               |
| `reference_id`   | `CharField`     | Unique human-readable ID, e.g. `KYC-A3F9X2BQ`                             |
| `first_name`     | `CharField`     | Normalised to title case                                                  |
| `last_name`      | `CharField`     | Normalised to title case                                                  |
| `date_of_birth`  | `DateField`     | Must be 18+ years ago                                                     |
| `nationality`    | `CharField`     | Country name string                                                       |
| `email`          | `EmailField`    |                                                                           |
| `id_type`        | `CharField`     | Choices: `passport`, `national_id`, `drivers_licence`, `residence_permit` |
| `id_number`      | `CharField`     | Uppercased, min 4 chars                                                   |
| `id_expiry`      | `DateField`     | Must not be in the past                                                   |
| `id_front`       | `ImageField`    | Stored at `kyc/id_documents/front/`                                       |
| `id_back`        | `ImageField`    | Optional; stored at `kyc/id_documents/back/`                              |
| `liveness_video` | `FileField`     | Stored at `kyc/liveness_videos/`                                          |
| `status`         | `CharField`     | `pending` / `approved` / `rejected` / `resubmit`                          |
| `reviewer_notes` | `TextField`     | Free-text notes for admin reviewers                                       |
| `submitted_at`   | `DateTimeField` | Auto-set on creation                                                      |
| `updated_at`     | `DateTimeField` | Auto-updated on save                                                      |

---

## Form Validation

### `PersonalInfoForm`

- First/last name minimum 2 characters, normalised to title case
- Date of birth must be in the past and result in age ≥ 18
- Email validated by Django's built-in `EmailField`

### `IDDocumentForm`

- Document number uppercased, minimum 4 characters
- Expiry date must be today or in the future
- Images validated for content type (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`) and file size (max 10 MB)

### `LivenessVideoForm`

- Video required; no silent empty submissions
- Accepted types: `video/webm`, `video/mp4`, `video/ogg`
- Max file size: 50 MB

---

## How the Session Flow Works

```
Browser                         Django
  |                               |
  |── POST step 1 ──────────────► KYCStep1View
  |                               | saves data to session["kyc_step1_data"]
  |◄── redirect /step/2/ ─────────|
  |                               |
  |── POST step 2 ──────────────► KYCStep2View
  |   (includes file uploads)     | saves files to kyc/temp/
  |                               | saves paths to session["kyc_step2_front"]
  |◄── redirect /step/3/ ─────────|
  |                               |
  |── POST step 3 ──────────────► KYCStep3View
  |   (includes video blob)       | reads all session data
  |                               | moves temp files to permanent storage
  |                               | creates KYCSubmission in DB
  |                               | clears session keys
  |◄── redirect /success/<uuid>/ ─|
```

If the user navigates to step 2 or 3 directly without completing prior steps, they are redirected back to the earliest incomplete step with a warning message.

---

## Liveness Video (Frontend)

The browser captures video using the `MediaRecorder` API. On completion, the recorded `Blob` is converted to a `File` object and injected into a hidden `<input type="file">` via `DataTransfer`, so the form POSTs it as a standard multipart upload — no JavaScript fetch or AJAX required.

```
startCamera()  →  getUserMedia({ video: true })
startRecording()  →  MediaRecorder records 5 seconds
onRecordingComplete()  →  Blob → File → DataTransfer → input.files
form.submit()  →  standard POST with enctype="multipart/form-data"
```

---

## Admin Panel

The `KYCSubmission` model is registered with a customised admin view at `/admin/`.

- **Search** by name, email, reference ID, or document number
- **Filter** by status, ID type, or nationality
- **Update status** (`pending → approved / rejected / resubmit`) and add reviewer notes
- All file upload fields link directly to the stored media

---

## Production Checklist

- [ ] Set `DEBUG = False` and configure `ALLOWED_HOSTS`
- [ ] Replace the default file storage backend with S3 or similar (e.g. `django-storages`) — never serve uploaded ID documents from your web server directly
- [ ] Enforce HTTPS — liveness check requires a secure context (`getUserMedia` is blocked on HTTP)
- [ ] Set `SESSION_COOKIE_SECURE = True` and `SESSION_COOKIE_HTTPONLY = True`
- [ ] Add `Pillow` to `requirements.txt` for `ImageField` support
- [ ] Restrict `/media/kyc/` from public access — uploaded documents should only be accessible to authenticated reviewers
- [ ] Consider encrypting stored documents at rest
- [ ] Add rate limiting to the KYC endpoints to prevent abuse

---

## License

MIT — use freely, modify as needed.
