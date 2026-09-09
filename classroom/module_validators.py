from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB


def validate_size(upload):
    if upload.size > MAX_UPLOAD_SIZE:
        raise ValidationError("The maximum file size is 20 MB.")


def validate_pdf(upload):
    validate_size(upload)

    if Path(upload.name).suffix.lower() != ".pdf":
        raise ValidationError("Please upload a PDF file.")

    try:
        upload.seek(0)

        if upload.read(5) != b"%PDF-":
            raise ValidationError("This does not appear to be a PDF.")

        upload.seek(0)
        reader = PdfReader(upload)

        if reader.is_encrypted:
            raise ValidationError(
                "Password-protected PDFs are not supported."
            )

        if not 1 <= len(reader.pages) <= 200:
            raise ValidationError(
                "The PDF must contain between 1 and 200 pages."
            )

    except (PdfReadError, ValueError, OSError):
        raise ValidationError("The PDF could not be read.")

    finally:
        upload.seek(0)


def validate_answer_file(upload):
    extension = Path(upload.name).suffix.lower()

    if extension == ".pdf":
        validate_pdf(upload)
        return

    validate_size(upload)

    if extension not in [".jpg", ".jpeg", ".png"]:
        raise ValidationError(
            "Upload a PDF, JPG, or PNG file."
        )

    try:
        upload.seek(0)
        image = Image.open(upload)

        expected_format = (
            "PNG" if extension == ".png" else "JPEG"
        )

        if image.format != expected_format:
            raise ValidationError(
                "The image contents do not match its extension."
            )

        if image.width * image.height > 16000000:
            raise ValidationError(
                "Please use an image smaller than 16 megapixels."
            )

        image.verify()

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ):
        raise ValidationError("The image could not be read.")

    finally:
        upload.seek(0)