"""
Upload validation (REQ-DOC-002/003, REQ-SEC-014).

Three independent checks — a renamed .exe fails the signature test even with a .pdf extension:
1. extension ∈ {pdf, jpg, jpeg}
2. size ≤ 10 MB (and not empty)
3. file *content* begins with the real PDF / JPEG signature ("magic bytes")
Signature sniffing is done in pure Python so it works identically on Windows, macOS and Linux.
"""
import hashlib

from django.conf import settings

from apps.core.exceptions import BusinessRuleError

ALLOWED = {
    "pdf": ("application/pdf", [b"%PDF-"]),
    "jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    "jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
}


def _fail(message, code):
    raise BusinessRuleError(message, code=code, fields={"file": [message]})


def validate_upload(uploaded):
    name = getattr(uploaded, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        _fail("Unsupported file type. Only PDF, JPG and JPEG files are accepted.", "unsupported_file_type")
    size = uploaded.size or 0
    if size == 0:
        _fail("The file is empty.", "empty_file")
    if size > settings.MAX_UPLOAD_SIZE_BYTES:
        _fail(f"File is too large ({size / 1024 / 1024:.1f} MB). The maximum is "
              f"{settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.", "file_too_large")
    mime, signatures = ALLOWED[ext]
    uploaded.seek(0)
    head = uploaded.read(8)
    uploaded.seek(0)
    # Some PDF writers emit a few bytes (e.g. BOM/whitespace) before the header; the spec allows it within 1 KB.
    if ext == "pdf":
        head_kb = uploaded.read(1024)
        uploaded.seek(0)
        ok = b"%PDF-" in head_kb
    else:
        ok = any(head.startswith(sig) for sig in signatures)
    if not ok:
        _fail("The file content does not match its extension (it is not a genuine PDF/JPEG).", "file_content_mismatch")
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return {"extension": ext, "content_type": mime, "size": size, "sha256": digest.hexdigest(),
            "original_filename": name[-255:]}
