import unittest
from unittest.mock import patch

import frappe

from mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff import cargar_balanza_csv
from mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff import copiar_eeff_y_notas_desde_paquete
from mfi_tools.mfi_tools.services import mapping_refresh as refresh
from mfi_tools.mfi_tools.services.report_periods import MONTHS, configure_default_periods, should_emit


class MappingRefreshTest(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.company = "_Test Company"
        self.year = 2197

    def tearDown(self):
        frappe.db.rollback()

    def balance(self, month="Mayo", amount=100):
        balance = frappe.get_doc({
            "doctype": "Balanza Comprobacion EEFF", "company": self.company,
            "anio": self.year, "mes": month, "moneda": "USD",
            "lineas": [{"codigo_cuenta": "1101", "descripcion_cuenta": "Caja", "debe_saldo": amount},
                       {"codigo_cuenta": "3101", "descripcion_cuenta": "Patrimonio", "haber_saldo": amount}],
        }).insert()
        return balance

    def package(self, balance):
        return frappe.get_doc({
            "doctype": "Paquete EEFF", "company": self.company,
            "anio": self.year, "mes": balance.mes, "balanza_comprobacion_eeff": balance.name,
        }).insert()

    def targets(self, package):
        state = frappe.get_doc({
            "doctype": "Estado Financiero EEFF", "paquete_eeff": package.name,
            "codigo_estado": "QA", "tipo_estado": "Estado de Situacion Financiera", "titulo": "Prueba",
            "lineas": [{"codigo_linea": "CAJA", "descripcion": "Caja", "origen_dato": "Formula", "formula_lineas": 'BAL("1101")'}],
        }).insert()
        note = frappe.get_doc({
            "doctype": "Nota EEFF", "paquete_eeff": package.name, "numero_nota": 1, "titulo": "Caja",
            "cifras_nota": [{"codigo_cifra": "CAJA", "concepto": "Caja", "origen_dato": "Formula", "formula_cifras": 'BAL("1101")'}],
        }).insert()
        return state, note

    def upload(self, balance, amount):
        return cargar_balanza_csv(balance.name,
            "codigo_cuenta,descripcion_cuenta,debe_saldo,haber_saldo\n"
            f"1101,Caja,{amount},0\n3101,Patrimonio,0,{amount}\n")

    def test_reimport_recalculates_states_and_notes(self):
        balance = self.balance()
        package = self.package(balance)
        state, note = self.targets(package)
        result = self.upload(balance, 325)
        self.assertFalse(result["mapeos"][0]["mapeo_desactualizado"], result)
        self.assertEqual(frappe.get_doc(state.doctype, state.name).lineas[0].monto_actual, 325)
        self.assertEqual(frappe.get_doc(note.doctype, note.name).cifras_nota[0].monto_actual, 325)
        self.assertEqual(frappe.db.get_value("Paquete EEFF", package.name, "mapeo_desactualizado"), 0)

    def test_failed_mapping_preserves_upload_and_previous_target_values(self):
        balance = self.balance()
        package = self.package(balance)
        state, note = self.targets(package)
        self.assertFalse(refresh.recalculate_package(package.name)["mapeo_desactualizado"])

        def fail(name):
            frappe.db.set_value("Linea Estado Financiero EEFF", state.lineas[0].name, "monto_actual", 999)
            raise frappe.ValidationError("Formula de prueba invalida")

        with patch("mfi_tools.mfi_tools.services.mapeo.aplicar_mapeo_paquete", side_effect=fail), patch.object(frappe, "log_error"):
            result = self.upload(balance, 400)
        self.assertTrue(result["mapeos"][0]["mapeo_desactualizado"])
        self.assertEqual(frappe.get_doc(balance.doctype, balance.name).total_debe, 400)
        self.assertEqual(frappe.get_doc(state.doctype, state.name).lineas[0].monto_actual, 100)
        self.assertEqual(frappe.get_doc(note.doctype, note.name).cifras_nota[0].monto_actual, 100)
        self.assertTrue(frappe.db.get_value("Paquete EEFF", package.name, "mapeo_desactualizado"))

    def test_copy_maps_using_destination_balance(self):
        source = self.package(self.balance("Mayo", 100))
        source_state, source_note = self.targets(source)
        refresh.recalculate_package(source.name)
        destination = self.package(self.balance("Junio", 250))
        result = copiar_eeff_y_notas_desde_paquete(destination.name, source.name)
        self.assertFalse(result["mapeo"]["mapeo_desactualizado"], result)
        state = frappe.get_doc("Estado Financiero EEFF", result["estados"][0])
        note = frappe.get_doc("Nota EEFF", result["notas"][0])
        self.assertEqual(state.lineas[0].monto_actual, 250)
        self.assertEqual(note.cifras_nota[0].monto_actual, 250)
        self.assertEqual(frappe.get_doc(source_state.doctype, source_state.name).lineas[0].monto_actual, 100)

    def test_copy_survives_mapping_failure(self):
        source = self.package(self.balance("Mayo", 100))
        self.targets(source)
        refresh.recalculate_package(source.name)
        destination = self.package(self.balance("Junio", 250))
        with patch("mfi_tools.mfi_tools.services.mapeo.aplicar_mapeo_paquete", side_effect=frappe.ValidationError("Error QA")), patch.object(frappe, "log_error"):
            result = copiar_eeff_y_notas_desde_paquete(destination.name, source.name)
        self.assertTrue(result["mapeo"]["mapeo_desactualizado"])
        self.assertTrue(frappe.db.exists("Estado Financiero EEFF", result["estados"][0]))
        self.assertTrue(frappe.db.exists("Nota EEFF", result["notas"][0]))

    def test_comparative_and_base_links_also_recalculate(self):
        actual = self.balance("Mayo", 100)
        reference = self.balance("Junio", 50)
        package = self.package(actual)
        state, note = self.targets(package)
        for field in refresh.BALANCE_LINKS[1:]:
            package.set(field, reference.name)
        package.save()
        state.lineas[0].formula_lineas = 'BAL_COMP("1101") + BAL_BASE_ACT("1101") + BAL_BASE_COMP("1101")'
        state.save()
        result = self.upload(reference, 75)
        self.assertFalse(result["mapeos"][0]["mapeo_desactualizado"], result)
        self.assertEqual(frappe.get_doc(state.doctype, state.name).lineas[0].monto_actual, 225)

    def test_historical_change_marks_package_pending(self):
        previous = self.balance("Mayo", 100)
        package = self.package(self.balance("Junio", 200))
        state, note = self.targets(package)
        state.lineas[0].formula_lineas = 'YTD("1101", "saldo")'
        state.save()
        self.assertFalse(refresh.recalculate_package(package.name)["mapeo_desactualizado"])
        self.upload(previous, 150)
        self.assertTrue(frappe.db.get_value("Paquete EEFF", package.name, "mapeo_desactualizado"))
        self.assertIn("historica", frappe.db.get_value("Paquete EEFF", package.name, "detalle_mapeo"))

    def test_metadata_only_save_does_not_recalculate(self):
        balance = self.balance()
        package = self.package(balance)
        with patch.object(refresh, "recalculate_package") as recalculate:
            balance.observaciones = "Solo comentario"
            balance.save()
            recalculate.assert_not_called()

    def test_incompatible_period_does_not_overwrite_existing_values(self):
        balance = self.balance()
        package = self.package(balance)
        state, note = self.targets(package)
        refresh.recalculate_package(package.name)
        balance.anio = self.year + 1
        with patch.object(frappe, "log_error"):
            balance.save()
        self.assertTrue(frappe.db.get_value("Paquete EEFF", package.name, "mapeo_desactualizado"))
        self.assertEqual(frappe.get_doc(state.doctype, state.name).lineas[0].monto_actual, 100)


class ReportPeriodTest(unittest.TestCase):
    def defaults(self, kind):
        doc = frappe._dict(tipo_estado=kind, emitir_todos_meses=1)
        doc.set = lambda key, value: doc.update({key: value})
        configure_default_periods(doc)
        return doc

    def test_equity_in_june_and_december(self):
        doc = self.defaults("Estado de Cambios en el Patrimonio")
        self.assertEqual([month for month in MONTHS if should_emit(doc, month)], ["Junio", "Diciembre"])

    def test_cash_flow_only_in_december(self):
        doc = self.defaults("Estado de Flujos de Efectivo")
        self.assertEqual([month for month in MONTHS if should_emit(doc, month)], ["Diciembre"])

    def test_other_reports_monthly(self):
        self.assertTrue(all(should_emit(self.defaults("Estado de Resultados"), month) for month in MONTHS))

    def test_custom_months_and_all_months_are_preserved(self):
        doc = self.defaults("Estado de Flujos de Efectivo")
        doc.emitir_diciembre = 0
        doc.emitir_marzo = 1
        configure_default_periods(doc)
        self.assertEqual([month for month in MONTHS if should_emit(doc, month)], ["Marzo"])
        doc.emitir_todos_meses = 1
        self.assertTrue(all(should_emit(doc, month) for month in MONTHS))
