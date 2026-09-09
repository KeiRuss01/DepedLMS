import re

from pypdf import PdfReader


NUMBERED_QUESTION = re.compile(
    r"^\s*(?:question\s*)?(\d{1,3})[.)]\s+(.+)$",
    re.IGNORECASE,
)

MULTIPLE_CHOICE_OPTION = re.compile(
    r"^\s*[A-D][.)]\s+.+",
    re.IGNORECASE,
)

LONG_ANSWER_WORDS = (
    "explain",
    "describe",
    "discuss",
    "compare",
    "differentiate",
    "why",
    "how",
    "essay",
)


def detect_answer_type(question, following_lines):
    option_count = sum(
        1
        for line in following_lines
        if MULTIPLE_CHOICE_OPTION.match(line)
    )

    if option_count >= 2:
        return "choice"

    question_lower = question.lower()

    if any(word in question_lower for word in LONG_ANSWER_WORDS):
        return "long"

    return "short"


def scan_pdf_questions(pdf_field):
    """Return suggested question fields from a text-based PDF."""
    questions = []
    seen_labels = set()

    pdf_field.open("rb")

    try:
        reader = PdfReader(pdf_field)

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except (KeyError, TypeError, ValueError, OSError):
                # A damaged text layer should not prevent the Teacher
                # from creating and reviewing the module manually.
                continue
            lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ]

            for index, line in enumerate(lines):
                match = NUMBERED_QUESTION.match(line)

                if not match:
                    continue

                number = match.group(1)
                question_text = match.group(2).strip()
                following_lines = lines[index + 1:index + 5]

                label = (
                    f"Page {page_number}, Question {number}: "
                    f"{question_text}"
                )[:250]

                if label in seen_labels:
                    continue

                seen_labels.add(label)
                questions.append(
                    {
                        "label": label,
                        "answer_type": detect_answer_type(
                            question_text,
                            following_lines,
                        ),
                    }
                )

                if len(questions) == 50:
                    return questions

    finally:
        pdf_field.close()

    return questions
