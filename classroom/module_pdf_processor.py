from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from pypdf import PdfReader, PdfWriter


def parse_page_numbers(value, page_count):
    pages = set()
    if not value.strip():
        return pages
    try:
        for part in value.split(","):
            part = part.strip()
            if "-" in part:
                start, end = [int(number.strip()) for number in part.split("-", 1)]
                if start > end:
                    raise ValueError
                pages.update(range(start, end + 1))
            else:
                pages.add(int(part))
    except ValueError as error:
        raise ValidationError("Use page numbers such as 18, 20-22.") from error
    if any(page < 1 or page > page_count for page in pages):
        raise ValidationError(f"Teacher-only pages must be between 1 and {page_count}.")
    return pages


def build_student_pdf(module):
    module.pdf.open("rb")
    try:
        reader = PdfReader(module.pdf)
        hidden = parse_page_numbers(module.hidden_pages, len(reader.pages))
        writer = PdfWriter()
        for page_number, page in enumerate(reader.pages, start=1):
            if page_number not in hidden:
                writer.add_page(page)
        if not writer.pages:
            raise ValidationError("At least one PDF page must remain visible to Students.")
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        filename = f"student-{Path(module.pdf.name).stem}.pdf"
        module.student_pdf.save(filename, ContentFile(output.read()), save=False)
        module.save(update_fields=["student_pdf"])
    finally:
        module.pdf.close()
