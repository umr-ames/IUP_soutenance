from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .forms import PFERequestForm


class PFERequestFormTests(SimpleTestCase):
    def test_rapport_stage_is_required(self):
        form = PFERequestForm(
            data={},
            files={
                "authorization_document": SimpleUploadedFile(
                    "autorisation.pdf",
                    b"%PDF-1.4 autorisation",
                    content_type="application/pdf",
                ),
                "attestation_stage": SimpleUploadedFile(
                    "attestation.pdf",
                    b"%PDF-1.4 attestation",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("rapport_stage", form.errors)
        self.assertIn(
            "Le rapport de stage est obligatoire",
            form.errors["rapport_stage"][0],
        )

    def test_rapport_stage_accepts_pdf(self):
        form = PFERequestForm(
            data={},
            files={
                "authorization_document": SimpleUploadedFile(
                    "autorisation.pdf",
                    b"%PDF-1.4 autorisation",
                    content_type="application/pdf",
                ),
                "attestation_stage": SimpleUploadedFile(
                    "attestation.pdf",
                    b"%PDF-1.4 attestation",
                    content_type="application/pdf",
                ),
                "rapport_stage": SimpleUploadedFile(
                    "rapport.pdf",
                    b"%PDF-1.4 rapport",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
