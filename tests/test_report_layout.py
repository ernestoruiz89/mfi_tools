import unittest

import frappe
from docx import Document

import test_mapping_refresh as refresh_tests
from mfi_tools.mfi_tools.utils.word_export import _add_notas_section


class ReportLayoutTest(unittest.TestCase):
    def setUp(self):
        fixture = refresh_tests.MappingRefreshTest()
        fixture.setUp()
        self.package = fixture.package(fixture.balance())
        for number in (1, 2):
            frappe.get_doc({
                "doctype": "Nota EEFF", "paquete_eeff": self.package.name,
                "numero_nota": number, "titulo": f"Nota de prueba {number}",
                "contenido_narrativo": "<p>Contenido breve de prueba.</p>",
            }).insert()

    def tearDown(self):
        frappe.db.rollback()

    def test_portrait_notes_share_the_same_word_section(self):
        doc = Document()
        _add_notas_section(doc, self.package)
        self.assertEqual(len(doc.sections), 1)
        self.assertTrue(any("Nota 1." in p.text for p in doc.paragraphs))
        self.assertTrue(any("Nota 2." in p.text for p in doc.paragraphs))

    def test_orientation_change_keeps_a_required_section_break(self):
        note = frappe.get_doc("Nota EEFF", {"paquete_eeff": self.package.name, "numero_nota": 2})
        note.orientacion = "Horizontal"
        note.save()
        doc = Document()
        _add_notas_section(doc, self.package)
        self.assertEqual(len(doc.sections), 2)
        self.assertGreater(doc.sections[-1].page_width, doc.sections[-1].page_height)
