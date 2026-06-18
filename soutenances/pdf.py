import re
import unicodedata
from datetime import datetime

from django.http import HttpResponse


PAGE_WIDTH = 595
PAGE_HEIGHT = 842

MARGIN_LEFT = 45
MARGIN_TOP = 800
LINE_HEIGHT = 16

FONT_NORMAL = "F1"
FONT_BOLD = "F2"


def simple_pdf_response(title, lines, filename):
    """
    Génère un PDF simple sans dépendances externes.
    Compatible avec les exports existants:
        simple_pdf_response(title, lines, filename)
    """

    safe_title = clean_text(title)
    safe_filename = safe_pdf_filename(filename)

    prepared_lines = prepare_lines(safe_title, lines)
    pages = paginate(prepared_lines)

    objects = []

    # 1. Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

    # 2. Pages placeholder
    page_object_ids = []
    content_object_ids = []

    # 3. Font normal
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # 4. Font bold
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    next_id = 5

    for _ in pages:
        page_object_ids.append(next_id)
        content_object_ids.append(next_id + 1)
        next_id += 2

    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    pages_object = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>"
    ).encode("ascii")

    objects.insert(1, pages_object)

    for index, page_lines in enumerate(pages, start=1):
        page_id = page_object_ids[index - 1]
        content_id = content_object_ids[index - 1]

        page_object = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << "
            f"/F1 3 0 R "
            f"/F2 4 0 R "
            f">> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")

        objects.append(page_object)

        stream = build_page_stream(page_lines, index, len(pages))

        content_object = (
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\n"
            b"stream\n" + stream + b"\nendstream"
        )

        objects.append(content_object)

    pdf = build_pdf(objects)

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    return response


def prepare_lines(title, lines):
    prepared = []

    prepared.append({
        "text": title,
        "font": FONT_BOLD,
        "size": 17,
        "spacing_after": 10,
    })

    prepared.append({
        "text": f"Genere le {datetime.now():%d/%m/%Y a %H:%M}",
        "font": FONT_NORMAL,
        "size": 9,
        "spacing_after": 14,
    })

    prepared.append({
        "text": "",
        "font": FONT_NORMAL,
        "size": 10,
        "spacing_after": 8,
    })

    for raw_line in lines:
        line = clean_text(raw_line)

        if not line.strip():
            prepared.append({
                "text": "",
                "font": FONT_NORMAL,
                "size": 10,
                "spacing_after": 8,
            })
            continue

        if is_section_title(line):
            prepared.append({
                "text": line,
                "font": FONT_BOLD,
                "size": 13,
                "spacing_after": 8,
            })
            continue

        if is_separator(line):
            prepared.append({
                "text": "-" * 95,
                "font": FONT_NORMAL,
                "size": 9,
                "spacing_after": 8,
            })
            continue

        wrapped_lines = wrap_text(line, max_chars=95)

        for wrapped_line in wrapped_lines:
            prepared.append({
                "text": wrapped_line,
                "font": FONT_NORMAL,
                "size": 10,
                "spacing_after": 4,
            })

    if len(prepared) <= 3:
        prepared.append({
            "text": "Aucune donnee disponible.",
            "font": FONT_NORMAL,
            "size": 10,
            "spacing_after": 4,
        })

    return prepared


def paginate(prepared_lines):
    pages = []
    current_page = []
    y = MARGIN_TOP

    for item in prepared_lines:
        line_size = item.get("size", 10)
        spacing_after = item.get("spacing_after", 4)

        needed_height = line_size + spacing_after + 4

        if y - needed_height < 55 and current_page:
            pages.append(current_page)
            current_page = []
            y = MARGIN_TOP

        current_page.append(item)
        y -= needed_height

    if current_page:
        pages.append(current_page)

    return pages or [[{
        "text": "Aucune donnee disponible.",
        "font": FONT_NORMAL,
        "size": 10,
        "spacing_after": 4,
    }]]


def build_page_stream(page_lines, page_number, total_pages):
    commands = []

    y = MARGIN_TOP

    for item in page_lines:
        text = item.get("text", "")
        font = item.get("font", FONT_NORMAL)
        size = item.get("size", 10)
        spacing_after = item.get("spacing_after", 4)

        if text.strip():
            commands.append("BT")
            commands.append(f"/{font} {size} Tf")
            commands.append(f"{MARGIN_LEFT} {y} Td")
            commands.append(f"({escape_pdf_text(text)}) Tj")
            commands.append("ET")

        y -= size + spacing_after + 4

    footer = f"Page {page_number}/{total_pages}"

    commands.append("BT")
    commands.append(f"/{FONT_NORMAL} 8 Tf")
    commands.append(f"{MARGIN_LEFT} 35 Td")
    commands.append(f"({escape_pdf_text(footer)}) Tj")
    commands.append("ET")

    return "\n".join(commands).encode("ascii")


def build_pdf(objects):
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)

    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n"
            f"%%EOF\n"
        ).encode("ascii")
    )

    return bytes(output)


def clean_text(value):
    text = str(value or "")

    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ç": "c",
        "É": "E",
        "È": "E",
        "Ê": "E",
        "À": "A",
        "Ù": "U",
        "Ç": "C",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "•": "-",
    }

    for source, target in replacements.items():
        text = text.replace(source, target)

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()

    return text


def escape_pdf_text(value):
    text = clean_text(value)
    text = text.replace("\\", "\\\\")
    text = text.replace("(", "\\(")
    text = text.replace(")", "\\)")
    return text


def wrap_text(text, max_chars=95):
    text = clean_text(text)

    if len(text) <= max_chars:
        return [text]

    words = text.split(" ")
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def is_section_title(line):
    line = clean_text(line)

    if line.endswith(":") and len(line) <= 70:
        return True

    upper_count = sum(1 for char in line if char.isupper())
    letters_count = sum(1 for char in line if char.isalpha())

    if letters_count > 0 and upper_count / letters_count > 0.75 and len(line) <= 80:
        return True

    keywords = [
        "Informations",
        "Etudiant",
        "Jury",
        "Planning",
        "Evaluations",
        "Resultat",
        "Decision",
        "Signatures",
    ]

    return any(line.startswith(keyword) for keyword in keywords)


def is_separator(line):
    stripped = clean_text(line).strip()
    return stripped in {"---", "-----", "------", "__________"}


def safe_pdf_filename(filename):
    name = clean_text(filename)

    if not name:
        name = "document.pdf"

    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_.-]", "", name)

    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    return name