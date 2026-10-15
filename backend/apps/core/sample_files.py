"""Generates small but genuine PDF / JPEG files for demo seeding and automated tests."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile


def pdf_bytes(title="Sample document", lines=()):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, 780, title)
    c.setFont("Helvetica", 11)
    y = 750
    for line in lines or ["Demo document generated for the Insurance Claims platform."]:
        c.drawString(60, y, str(line))
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def jpeg_bytes(label="Photo", color=(70, 90, 120), size=(640, 420)):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, size[0] - 20, size[1] - 20], outline=(255, 255, 255), width=4)
    d.text((40, 40), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def upload_pdf(name="document.pdf", title="Sample document", lines=()):
    return SimpleUploadedFile(name, pdf_bytes(title, lines), content_type="application/pdf")


def upload_jpeg(name="photo.jpg", label="Photo", color=(70, 90, 120)):
    return SimpleUploadedFile(name, jpeg_bytes(label, color), content_type="image/jpeg")
