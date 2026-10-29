import unittest
from unittest.mock import patch

import frappe

from mfi_tools.mfi_tools.page.indicadores_emision_eeff import indicadores_emision_eeff as indicators
from mfi_tools.mfi_tools.services import emission_validation as validation


def row(**values):
    return frappe._dict(values)


class EmissionIndicatorsTest(unittest.TestCase):
    def setUp(self):
        for module in (indicators, validation):
            translate = patch.object(module, "_", lambda message: message)
            translate.start()
            self.addCleanup(translate.stop)

    def formula_issues(self, rows):
        return indicators._formula_issues_for_rows(
            rows, "codigo_linea", "formula_lineas", "Estado", "E", "modo_formula",
        )

    def formula_row(self, code, formula="", **kwargs):
        return row(codigo_linea=code, formula_lineas=formula, origen_dato="Formula", **kwargs)

    def evaluate(self, balance=None, states=None, notes=None):
        package = row(name="P", company="Company", anio=2026, mes="Enero",
                      periodo_nombre="Enero 2026", estado_preparacion="Borrador",
                      balanza_comprobacion_eeff="B" if balance is not None else "")
        package.check_permission = lambda permission: None
        states, notes = states or [], notes or []
        docs = {("Paquete EEFF", "P"): package}
        if balance is not None:
            balance.check_permission = lambda permission: None
            docs["Balanza Comprobacion EEFF", "B"] = balance
        for doc in states + notes:
            doc.check_permission = lambda permission: None
            docs[doc.doctype, doc.name] = doc

        def get_all(doctype, **kwargs):
            return [row(name=doc.name) for doc in states] if doctype == "Estado Financiero EEFF" else []

        with patch.object(indicators, "_require_access"), \
             patch.object(indicators, "_evaluation_time", return_value="2026-10-18T18:00:00+00:00"), \
             patch.object(indicators, "_get_entity_display", return_value="Company"), \
             patch.object(indicators, "get_package_note_rows", return_value=[row(name=n.name) for n in notes]), \
             patch.object(frappe.db, "exists", return_value=True), \
             patch.object(frappe, "get_all", side_effect=get_all), \
             patch.object(frappe, "get_doc", side_effect=lambda dt, name: docs[dt, name]):
            return indicators._compute_indicators("P")

    def balance(self, **kwargs):
        values = dict(company="Company", anio=2026, mes="Enero", total_debe=100,
                      total_haber=100, cuadra=1, lineas=[row(debe_saldo=100, haber_saldo=100)])
        values.update(kwargs)
        return row(**values)

    def test_valid_data_formulas_are_not_line_references(self):
        for expression in (
            'BAL("1101*")',
            'VAR X = BAL("1*")\nX / 2',
            'SI(ES_ACTUAL(), VAL_ACT(3), VAL_COMP(4))',
            'YTD("1*", "BAL")',
            'VAR X = 1\nVAR X = X + 1\nX',
            'BAL("1201")+BAL("1202")+BAL("1203")+\nBAL("1204")+BAL("1205")+BAL("1206")-\nBAL("1207")-BAL("1208")-BAL("1209")',
            'BAL("2101")+BAL("2102")+BAL("2103")+\n//CUENTAS BANCARIAS SOBREGIRADAS\nSI(BAL("11020101")<0,BAL("11020101"),0)+\nSI(BAL("11020102")<0,BAL("11020102"),0)',
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.formula_issues([self.formula_row("A", expression)]), [])

    def test_bad_data_formula_syntax_and_variables(self):
        for expression in ('BAL("1*"', 'VAR X = MISSING(2)\nX', 'BAL("1*") + UNKNOWN', 'BAL()', 'SI(ES_ACTUAL(), 1)'):
            with self.subTest(expression=expression):
                self.assertTrue(self.formula_issues([self.formula_row("A", expression)]))

    def test_self_prefix_is_supported(self):
        rows = [self.formula_row("A", "SELF.B", modo_formula="Multicolumna"), row(codigo_linea="B")]
        self.assertEqual(self.formula_issues(rows), [])

    def test_missing_reference_is_reported(self):
        issues = self.formula_issues([self.formula_row("A", "B")])
        self.assertEqual(issues[0]["referencia"], "B")

    def test_real_cycle_is_reported(self):
        issues = self.formula_issues([self.formula_row("A", "B"), self.formula_row("B", "A")])
        self.assertTrue(any("circular" in i["motivo"] for i in issues))

    def test_base_self_remains_a_cycle_like_the_calculator(self):
        issues = self.formula_issues([self.formula_row("A", "BASE.A", modo_formula="Multicolumna")])
        self.assertTrue(any("circular" in i["motivo"] for i in issues))

    def test_inactive_manual_formula_is_not_a_dependency(self):
        rows = [self.formula_row("A", "B"), row(codigo_linea="B", formula_lineas="A", origen_dato="Manual")]
        self.assertEqual(self.formula_issues(rows), [])

    def test_long_dependency_chain_does_not_recurse(self):
        rows = [self.formula_row(f"L{i}", f"L{i+1}") for i in range(1500)]
        rows.append(row(codigo_linea="L1500"))
        self.assertEqual(self.formula_issues(rows), [])

    def test_orphan_check_accepts_real_lines_without_an_orden_field(self):
        doc = frappe.get_doc({
            "doctype": "Estado Financiero EEFF", "name": "IN-MEMORY",
            "lineas": [{"codigo_linea": "A", "nivel": 1}, {"codigo_linea": "B", "nivel": 2}],
        })
        self.assertEqual(indicators._lineas_huerfanas(doc), [])

    def test_empty_html_is_not_note_content(self):
        for text in ("", "<p><br></p>", "<p>&nbsp;&#160;\u200b</p>", "<style>a{}</style>", "<img src>"):
            self.assertFalse(validation.has_rich_text(text), text)
        self.assertTrue(validation.has_rich_text('<img src="/files/chart.png">'))
        self.assertTrue(validation.has_rich_text("<p>0</p>"))

    def test_titles_and_blank_figures_do_not_complete_a_note(self):
        note = row(name="N", numero_nota=1, contenido_narrativo="", estructura_nota="Simple",
                   cifras_nota=[row(es_titulo=1), row(es_linea_blanco=1), row(no_imprimir=1)])
        self.assertTrue(indicators._notas_faltantes([note], {}))

    def test_zero_figure_is_valid_content(self):
        note = row(name="N", numero_nota=1, estructura_nota="Simple", cifras_nota=[row(monto_actual=0)])
        self.assertEqual(indicators._notas_faltantes([note], {}), [])

    def test_printed_observations_are_valid_note_content(self):
        note = row(name="N", numero_nota=1, estructura_nota="Simple", observaciones="<p>Informacion impresa</p>")
        self.assertEqual(indicators._notas_faltantes([note], {}), [])

    def test_large_note_number_does_not_expand_an_enormous_range(self):
        note = row(name="N", numero_nota=10**9, estructura_nota="Simple", contenido_narrativo="Contenido")
        self.assertEqual(len(indicators._notas_faltantes([note], {})), 1)

    def test_seeded_empty_cells_do_not_complete_a_complex_note(self):
        section = row(contenido_narrativo="", filas_tabulares=[], celdas_tabulares=[row(valor_numero=None, valor_texto="")])
        self.assertFalse(validation.section_has_content(section))
        section.celdas_tabulares[0].valor_numero = 0
        self.assertTrue(validation.section_has_content(section))

    def test_missing_referenced_note_beyond_the_sequence_is_reported(self):
        state = row(name="E", lineas=[row(codigo_linea="A", nota="8")])
        notes = [row(numero_nota=1)]
        self.assertEqual(len(indicators._missing_note_refs([state], notes)), 1)

    def test_subnote_references_match_the_full_identifier(self):
        state = row(name="E", lineas=[row(codigo_linea="A", nota="1 (a)")])
        self.assertEqual(indicators._missing_note_refs([state], [row(numero_nota=1, sub_nota="A")]), [])
        self.assertTrue(indicators._missing_note_refs([state], [row(numero_nota=1, sub_nota="B")]))

    def test_tabular_cycles_use_the_real_calculator_without_mutating_the_document(self):
        doc = frappe.get_doc({
            "doctype": "Estado Financiero EEFF", "name": "IN-MEMORY",
            "estructura_estado": "Compleja",
            "filas_tabulares": [{"codigo_tabla": "T", "codigo_fila": "R", "tipo_fila": "Detalle", "formula_filas": "R"}],
            "columnas_tabulares": [{"codigo_tabla": "T", "codigo_columna": "ACT", "tipo_dato": "Numero"}],
            "celdas_tabulares": [],
        })
        original = doc.as_dict()
        issues = validation.tabular_formula_issues(doc, "Estado")
        self.assertTrue(any("circular" in i["motivo"] for i in issues))
        self.assertEqual(original, doc.as_dict())

    def test_tabular_missing_reference_is_reported(self):
        doc = frappe.get_doc({
            "doctype": "Seccion Nota EEFF", "name": "IN-MEMORY",
            "filas_tabulares": [{"codigo_tabla": "T", "codigo_fila": "R", "formula_filas": "MISSING"}],
            "columnas_tabulares": [], "celdas_tabulares": [],
        })
        self.assertTrue(validation.tabular_formula_issues(doc, "Seccion de nota"))

    def test_empty_package_is_never_healthy(self):
        result = self.evaluate()
        self.assertEqual(result["kpis"]["health_status"], "error")
        self.assertLess(result["kpis"]["score"], 60)
        self.assertTrue(result["details"]["estructura"])

    def test_balance_uses_lines_instead_of_cached_totals(self):
        result = self.evaluate(self.balance(lineas=[row(debe_saldo=100, haber_saldo=90)]))
        self.assertEqual(result["kpis"]["cuadre"]["difference"], 10)
        self.assertEqual(result["kpis"]["cuadre"]["status"], "error")
        self.assertTrue(result["details"]["estructura"])

    def test_empty_balance_is_not_balanced(self):
        result = self.evaluate(self.balance(lineas=[]))
        self.assertEqual(result["kpis"]["cuadre"]["status"], "warning")

    def test_incompatible_period_and_entity_are_errors(self):
        for changes in ({"mes": "Febrero"}, {"company": "Other"}, {"anio": 2025}):
            self.assertEqual(self.evaluate(self.balance(**changes))["kpis"]["cuadre"]["status"], "error")

    def test_balance_tolerance_matches_the_balance_document(self):
        for difference, status in ((0.00005, "ok"), (0.005, "error")):
            balance = self.balance(cuadra=0, lineas=[row(debe_saldo=100, haber_saldo=100-difference)])
            self.assertEqual(self.evaluate(balance)["kpis"]["cuadre"]["status"], status)

    def test_permission_guard_runs_before_selector_queries(self):
        with patch.object(frappe, "only_for", side_effect=frappe.PermissionError), \
             patch.object(frappe, "get_list") as query:
            with self.assertRaises(frappe.PermissionError):
                indicators.get_indicator_bootstrap()
            query.assert_not_called()

    def test_package_permission_is_checked_before_loading_children(self):
        package = row(check_permission=lambda permission: (_ for _ in ()).throw(frappe.PermissionError()))
        with patch.object(indicators, "_require_access"), \
             patch.object(frappe.db, "exists", return_value=True), \
             patch.object(frappe, "get_doc", return_value=package), \
             patch.object(frappe, "get_all") as query:
            with self.assertRaises(frappe.PermissionError):
                indicators.run_emission_indicators("P")
            query.assert_not_called()

    def test_selected_package_restores_its_actual_filters(self):
        package = row(company="Actual Company", anio=2024, mes="Marzo")
        with patch.object(indicators, "_require_access"), \
             patch.object(indicators, "_compute_indicators", return_value={"package": {"name": "P"}}), \
             patch.object(frappe, "get_doc", return_value=package), \
             patch.object(indicators, "_get_clients", return_value=[]), \
             patch.object(indicators, "_get_packages", return_value=[]) as query:
            data = indicators.get_indicator_bootstrap(cliente="Wrong", anio=2026, mes="Enero", paquete_name="P")
            self.assertEqual((data["cliente"], data["anio"], data["mes"]), ("Actual Company", 2024, "Marzo"))
            query.assert_called_once_with(cliente="Actual Company", anio=2024, mes="Marzo")


if __name__ == "__main__":
    unittest.main()
