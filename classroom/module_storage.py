from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def learning_storage():
    return FileSystemStorage(
        location=settings.PRIVATE_LEARNING_ROOT,
    )


def module_pdf_path(instance, filename):
    # Random filenames prevent conflicts between uploaded files.
    return f"modules/{uuid4().hex}.pdf"


def student_module_pdf_path(instance, filename):
    # This copy excludes any Teacher-only pages such as answer keys.
    return f"modules/student/{uuid4().hex}.pdf"


def submission_file_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"answers/{uuid4().hex}{extension}"
