"""Génération de la Fiche d'Évaluation de Stage de Fin d'études au format Word,
à partir du gabarit officiel (assets/fiche_evaluation_template.docx) dont les
champs à remplir ont été remplacés par des jetons {{...}}."""

import io
import os
import zipfile
from xml.sax.saxutils import escape


TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "assets", "fiche_evaluation_template.docx"
)

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _fmt_note(value):
    """Note en format virgule (14,00) ou pointillés si absente."""
    if value is None:
        return "…………"
    return str(value).replace(".", ",")


def build_fiche_docx(assignment, averages):
    """Retourne les octets d'un .docx identique au document officiel, pré-rempli."""
    student = assignment.student
    jury = assignment.jury
    defense_date = jury.defense_date

    members = list(jury.members.select_related("professor").all())
    president_name = assignment.president.full_name if assignment.president else ""
    others = [
        m.professor.full_name for m in members
        if not assignment.president or m.professor_id != assignment.president_id
    ]
    membre1 = others[0] if len(others) > 0 else ""
    membre2 = others[1] if len(others) > 1 else ""

    values = {
        "{{MATRICULE}}": student.matricule or "",
        "{{NOM}}": student.full_name or "",
        "{{FILIERE}}": student.filiere or "",
        "{{ENTREPRISE}}": student.entreprise or "",
        "{{DJ}}": f"{defense_date.day:02d}" if defense_date else "  ",
        "{{DM}}": f"{defense_date.month:02d}" if defense_date else "  ",
        "{{RAPPORT}}": _fmt_note(averages.get("avg_rapport")),
        "{{PRESENTATION}}": _fmt_note(averages.get("avg_presentation")),
        "{{QUESTIONS}}": _fmt_note(averages.get("avg_questions")),
        "{{FINALE}}": _fmt_note(averages.get("avg_finale")),
        "{{PRESIDENT}}": president_name,
        "{{MEMBRE1}}": membre1,
        "{{MEMBRE2}}": membre2,
    }

    with zipfile.ZipFile(TEMPLATE_PATH) as template:
        document_xml = template.read("word/document.xml").decode("utf-8")
        for token, value in values.items():
            document_xml = document_xml.replace(token, escape(value))

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output:
            for item in template.namelist():
                if item == "word/document.xml":
                    output.writestr(item, document_xml.encode("utf-8"))
                else:
                    output.writestr(item, template.read(item))

    return buffer.getvalue()
