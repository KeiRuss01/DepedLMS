"""Build the final, flattened PDF for a custom Module submission."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .models import SubmissionExtraPage


def _field_bytes(field_file):
    field_file.open("rb")
    try:
        return field_file.read()
    finally:
        field_file.close()


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _color(value, default="#0b57d0"):
    try:
        return colors.HexColor(value or default)
    except (TypeError, ValueError):
        return colors.HexColor(default)


def _page_overlay(page_width, page_height, annotations):
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(page_width, page_height))

    for annotation in annotations:
        tool = annotation.get("tool")
        x = _number(annotation.get("x")) * page_width
        top_y = _number(annotation.get("y")) * page_height
        width = _number(annotation.get("width")) * page_width
        height = _number(annotation.get("height")) * page_height

        if tool == "type":
            font_size = max(8, _number(annotation.get("size"), 0.026) * page_height)
            pdf.setFillColor(_color(annotation.get("color")))
            pdf.setFont("Helvetica", font_size)
            text = pdf.beginText(x, page_height - top_y - font_size)
            text.setLeading(font_size * 1.2)
            for line in str(annotation.get("text", "")).splitlines() or [""]:
                text.textLine(line)
            pdf.drawText(text)

        elif tool == "draw":
            points = annotation.get("points") or []
            if len(points) < 2:
                continue
            pdf.setStrokeColor(_color(annotation.get("color")))
            pdf.setLineWidth(max(1, _number(annotation.get("size"), 0.005) * page_width))
            pdf.setLineCap(1)
            path = pdf.beginPath()
            first = points[0]
            path.moveTo(
                _number(first.get("x")) * page_width,
                page_height - _number(first.get("y")) * page_height,
            )
            for point in points[1:]:
                path.lineTo(
                    _number(point.get("x")) * page_width,
                    page_height - _number(point.get("y")) * page_height,
                )
            pdf.drawPath(path, stroke=1, fill=0)

        elif tool == "check":
            size = max(12, _number(annotation.get("size"), 0.04) * page_height)
            y = page_height - top_y
            pdf.setStrokeColor(_color(annotation.get("color"), "#16803a"))
            pdf.setLineWidth(max(2, size * 0.13))
            path = pdf.beginPath()
            path.moveTo(x, y - size * 0.45)
            path.lineTo(x + size * 0.32, y - size * 0.75)
            path.lineTo(x + size, y)
            pdf.drawPath(path, stroke=1, fill=0)

        elif tool == "circle":
            pdf.setStrokeColor(_color(annotation.get("color"), "#dc3545"))
            pdf.setLineWidth(max(1.5, page_width * 0.004))
            pdf.ellipse(
                x,
                page_height - top_y - height,
                x + width,
                page_height - top_y,
                stroke=1,
                fill=0,
            )

        elif tool == "highlight":
            pdf.saveState()
            if hasattr(pdf, "setFillAlpha"):
                pdf.setFillAlpha(min(max(_number(annotation.get("opacity"), 0.35), 0.05), 1))
            pdf.setFillColor(_color(annotation.get("color"), "#ffe066"))
            pdf.rect(
                x,
                page_height - top_y - height,
                width,
                height,
                stroke=0,
                fill=1,
            )
            pdf.restoreState()

    pdf.save()
    output.seek(0)
    return output


def _essay_pdf(extra_page, submission):
    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AnswerTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#102448"),
        spaceAfter=14,
    )
    meta_style = ParagraphStyle(
        "AnswerMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#667085"),
        spaceAfter=16,
    )
    answer_style = ParagraphStyle(
        "AnswerBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=17,
        textColor=colors.HexColor("#102448"),
        spaceAfter=9,
    )
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
        title=extra_page.title,
        author=str(submission.student),
    )
    related = (
        f" - Related Module page {extra_page.related_pdf_page}"
        if extra_page.related_pdf_page else ""
    )
    story = [
        Paragraph(escape(extra_page.title), title_style),
        Paragraph(
            escape(
                f"Student: {submission.student} - Module: {submission.module.title}{related}"
            ),
            meta_style,
        ),
    ]
    paragraphs = extra_page.essay_text.splitlines() or [""]
    for paragraph in paragraphs:
        story.append(Paragraph(escape(paragraph) or "&nbsp;", answer_style))
    document.build(story)
    output.seek(0)
    return output


def _drawing_pdf(extra_page, submission):
    output = BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(extra_page.title)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.setFillColor(colors.HexColor("#102448"))
    pdf.drawString(42, page_height - 44, extra_page.title)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#667085"))
    pdf.drawString(42, page_height - 61, f"Student: {submission.student}")

    left, bottom = 42, 42
    drawing_width = page_width - 84
    drawing_height = page_height - 125
    pdf.setStrokeColor(colors.HexColor("#dce4ef"))
    pdf.rect(left, bottom, drawing_width, drawing_height, stroke=1, fill=0)

    for stroke in extra_page.drawing_data or []:
        points = stroke.get("points") or []
        if len(points) < 2:
            continue
        pdf.setStrokeColor(_color(stroke.get("color"), "#102448"))
        pdf.setLineWidth(max(1, _number(stroke.get("size"), 0.006) * drawing_width))
        pdf.setLineCap(1)
        path = pdf.beginPath()
        first = points[0]
        path.moveTo(
            left + _number(first.get("x")) * drawing_width,
            bottom + (1 - _number(first.get("y"))) * drawing_height,
        )
        for point in points[1:]:
            path.lineTo(
                left + _number(point.get("x")) * drawing_width,
                bottom + (1 - _number(point.get("y"))) * drawing_height,
            )
        pdf.drawPath(path, stroke=1, fill=0)

    pdf.save()
    output.seek(0)
    return output


def _image_pdf(extra_page, file_bytes):
    output = BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(extra_page.title)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.setFillColor(colors.HexColor("#102448"))
    pdf.drawString(42, page_height - 44, extra_page.title)

    with Image.open(BytesIO(file_bytes)) as raw_image:
        image = ImageOps.exif_transpose(raw_image).convert("RGB")
        image_width, image_height = image.size
        available_width = page_width - 84
        available_height = page_height - 120
        scale = min(available_width / image_width, available_height / image_height)
        draw_width = image_width * scale
        draw_height = image_height * scale
        x = (page_width - draw_width) / 2
        y = 44 + (available_height - draw_height) / 2
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG", quality=92)
        image_buffer.seek(0)
        pdf.drawImage(
            ImageReader(image_buffer),
            x,
            y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
        )

    if extra_page.caption:
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(colors.HexColor("#667085"))
        pdf.drawCentredString(page_width / 2, 25, extra_page.caption[:120])
    pdf.save()
    output.seek(0)
    return output


def _append_reader(writer, stream):
    reader = PdfReader(stream, strict=False)
    for page in reader.pages:
        writer.add_page(page)


def build_final_submission_pdf(submission):
    """Flatten the custom draft into one PDF and store it as answered_pdf."""
    source_field = submission.module.student_pdf or submission.module.pdf
    if not source_field:
        raise ValidationError("The Module PDF is missing.")

    try:
        source_reader = PdfReader(BytesIO(_field_bytes(source_field)), strict=False)
        writer = PdfWriter()
        annotations_by_page = {}
        for annotation in submission.annotation_data or []:
            annotations_by_page.setdefault(int(annotation.get("page", 0)), []).append(annotation)

        for page_number, source_page in enumerate(source_reader.pages, start=1):
            page_width = float(source_page.mediabox.width)
            page_height = float(source_page.mediabox.height)
            page_annotations = annotations_by_page.get(page_number, [])
            if page_annotations:
                overlay_reader = PdfReader(
                    _page_overlay(page_width, page_height, page_annotations),
                    strict=False,
                )
                source_page.merge_page(overlay_reader.pages[0])
            writer.add_page(source_page)

        for extra_page in submission.extra_pages.all():
            if extra_page.page_type == SubmissionExtraPage.PageType.ESSAY:
                _append_reader(writer, _essay_pdf(extra_page, submission))
            elif extra_page.page_type == SubmissionExtraPage.PageType.DRAWING:
                _append_reader(writer, _drawing_pdf(extra_page, submission))
            elif extra_page.page_type == SubmissionExtraPage.PageType.UPLOAD:
                if not extra_page.uploaded_file:
                    continue
                file_bytes = _field_bytes(extra_page.uploaded_file)
                extension = Path(extra_page.original_name).suffix.lower()
                if extension == ".pdf":
                    _append_reader(writer, BytesIO(file_bytes))
                elif extension in {".jpg", ".jpeg", ".png"}:
                    _append_reader(writer, _image_pdf(extra_page, file_bytes))

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        completed_bytes = output.getvalue()
        completed_reader = PdfReader(BytesIO(completed_bytes), strict=False)
        if not completed_reader.pages:
            raise ValidationError("The completed Module has no pages.")
    except ValidationError:
        raise
    except Exception as error:
        raise ValidationError(
            "The final answered Module could not be generated. Check the uploaded files and try again."
        ) from error

    if submission.answered_pdf:
        submission.answered_pdf.delete(save=False)
    submission.answered_pdf.save(
        f"module-{submission.module_id}-student-{submission.student_id}-final.pdf",
        ContentFile(completed_bytes),
        save=False,
    )
    submission.pdf_saved_at = timezone.now()
    submission.save(update_fields=["answered_pdf", "pdf_saved_at", "updated_at"])
    return completed_bytes
