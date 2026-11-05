"""Regression coverage for list settings with and without the legacy column count."""

import json
import unittest
from unittest.mock import Mock, patch

from mfi_tools.mfi_tools.patches.v1_0 import backfill_eeff_mes_anio as migration


class PeriodBackfillTest(unittest.TestCase):
    def setUp(self):
        self.db_patch = patch.object(migration.frappe, "db", new=Mock())
        self.db = self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.db.sql.return_value = [("tabList View Settings",)]
        self.db.exists.return_value = True
        self.db.has_column.return_value = False
        self.fields = [
            {"fieldname": "paquete_eeff", "label": "Paquete"},
            {"fieldname": "titulo", "label": "Titulo", "custom": True},
        ]

        def get_value(doctype, name, fieldname):
            if fieldname == "fields":
                return json.dumps(self.fields)
            if fieldname == "total_fields" and self.db.has_column.return_value:
                return 8
            raise AssertionError(f"Unexpected column access: {fieldname}")

        self.db.get_value.side_effect = get_value

    def saved_fields(self):
        args, kwargs = self.db.set_value.call_args
        self.assertEqual(args[:2], ("List View Settings", "Nota EEFF"))
        self.assertEqual(kwargs, {"update_modified": False})
        return json.loads(args[2]["fields"]), args[2]

    def test_schema_without_total_fields_updates_only_existing_columns(self):
        migration._sync_list_view_settings("Nota EEFF")
        fields, values = self.saved_fields()
        self.assertEqual([f["fieldname"] for f in fields], ["paquete_eeff", "mes", "anio", "titulo"])
        self.assertEqual(fields[-1], self.fields[-1])
        self.assertEqual(set(values), {"fields"})
        self.db.get_value.assert_called_once_with("List View Settings", "Nota EEFF", "fields")

    def test_legacy_schema_preserves_column_count(self):
        self.db.has_column.return_value = True
        migration._sync_list_view_settings("Nota EEFF")
        _, values = self.saved_fields()
        self.assertEqual(values["total_fields"], 8)

    def test_repeat_run_does_not_duplicate_fields(self):
        migration._sync_list_view_settings("Nota EEFF")
        self.fields, _ = self.saved_fields()
        self.db.set_value.reset_mock()
        migration._sync_list_view_settings("Nota EEFF")
        self.db.set_value.assert_not_called()

    def test_adds_only_missing_period_field(self):
        self.fields.append({"fieldname": "mes", "label": "Mes personalizado"})
        migration._sync_list_view_settings("Nota EEFF")
        fields, _ = self.saved_fields()
        self.assertEqual(sum(f["fieldname"] == "mes" for f in fields), 1)
        self.assertIn(self.fields[-1], fields)
        self.assertEqual(sum(f["fieldname"] == "anio" for f in fields), 1)

    def test_missing_settings_are_not_created(self):
        self.db.exists.return_value = False
        migration._sync_list_view_settings("Nota EEFF")
        self.db.get_value.assert_not_called()
        self.db.set_value.assert_not_called()

    def test_invalid_settings_are_not_overwritten(self):
        for raw in (None, "invalid json", '{"fieldname": "titulo"}'):
            with self.subTest(raw=raw):
                self.db.get_value.side_effect = None
                self.db.get_value.return_value = raw
                migration._sync_list_view_settings("Nota EEFF")
                self.db.set_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
