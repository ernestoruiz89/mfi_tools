import frappe
from frappe import _
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.utils.nota_eeff import find_note_name

BALANCE_FIELDS = ("codigo_cuenta", "descripcion_cuenta")
BALANCE_VALUE_FIELDS = ("saldo", "saldo_anterior", "movimiento_del_mes")


def _normalize(value):
    return cstr(value or "").strip().upper()


def _normalize_balance_field(value):
    field = cstr(value or "codigo_cuenta").strip()
    return field if field in BALANCE_FIELDS else "codigo_cuenta"


def _normalize_balance_value_field(value):
    field = cstr(value or "saldo").strip()
    return field if field in BALANCE_VALUE_FIELDS else "saldo"


def _sum_by_prefix(values_map, prefix):
    total = 0.0
    for code, amount in (values_map or {}).items():
        if cstr(code or "").startswith(prefix):
            total += flt(amount or 0)
    return total


def _resolve_balance_value(values_map, raw_key):
    key = _normalize(raw_key)
    if not key:
        return 0.0

    if key.endswith("*"):
        prefix = key[:-1]
        if not prefix:
            return 0.0
        return _sum_by_prefix(values_map, prefix)

    return flt((values_map or {}).get(key, 0) or 0)


def _build_balance_map(balanza_doc):
    output = {
        value_field: {
            field: {"all": {}, "by_cost_center": {}}
            for field in BALANCE_FIELDS
        }
        for value_field in BALANCE_VALUE_FIELDS
    }
    for row in balanza_doc.lineas or []:
        centro_costo = _normalize(getattr(row, "centro_costo", ""))
        for value_field in BALANCE_VALUE_FIELDS:
            amount = flt(getattr(row, value_field, 0) or 0)
            for field in BALANCE_FIELDS:
                key = _normalize(getattr(row, field, ""))
                if not key:
                    continue
                output[value_field][field]["all"][key] = output[value_field][field]["all"].get(key, 0.0) + amount
                if centro_costo:
                    cc_map = output[value_field][field]["by_cost_center"].setdefault(centro_costo, {})
                    cc_map[key] = cc_map.get(key, 0.0) + amount
    return output


def _get_balance_amount(balance_map, cuenta, campo_balanza=None, centro_costo=None, value_field="saldo"):
    field = _normalize_balance_field(campo_balanza)
    amount_field = _normalize_balance_value_field(value_field)
    cost_center = _normalize(centro_costo)
    if cost_center:
        scoped_map = balance_map[amount_field][field]["by_cost_center"].get(cost_center, {})
        return _resolve_balance_value(scoped_map, cuenta)
    return _resolve_balance_value(balance_map[amount_field][field]["all"], cuenta)


def _build_stat_maps(package_doc):
    actual = {}
    for row in package_doc.datos_estadisticos or []:
        code = _normalize(getattr(row, "codigo_dato", ""))
        if not code:
            continue
        actual[code] = actual.get(code, 0.0) + flt(getattr(row, "valor_actual", 0) or 0)
    comparative = {}
    if hasattr(package_doc, "get_datos_estadisticos_comparativos_map"):
        raw_map = package_doc.get_datos_estadisticos_comparativos_map() or {}
        for code, value in raw_map.items():
            normalized = _normalize(code)
            if not normalized:
                continue
            comparative[normalized] = comparative.get(normalized, 0.0) + flt(value or 0)
    return actual, comparative


def _compute_rule_amount(rule_doc, balances, stats, balance_value_field="saldo"):
    source_type = cstr(getattr(rule_doc, "fuente_tipo", "Balanza") or "Balanza").strip()

    amount = 0.0
    for row in rule_doc.cuentas or []:
        cuenta = _normalize(row.cuenta)
        sign = -1 if cstr(row.operacion or "+").strip() == "-" else 1
        ratio = flt(row.porcentaje or 100) / 100.0
        if source_type == "Dato Estadistico":
            source_value = flt(stats.get(cuenta, 0))
        else:
            source_value = _get_balance_amount(
                balances,
                row.cuenta,
                getattr(row, "campo_balanza", "codigo_cuenta"),
                getattr(row, "centro_costo", ""),
                balance_value_field,
            )
        amount += sign * source_value * ratio
    return amount


def _compute_rule_amounts(
    rule_doc,
    actual_balances,
    comparative_balances,
    base_actual_balances,
    base_comparative_balances,
    actual_stats,
    comparative_stats,
):
    actual_amount = _compute_rule_amount(rule_doc, actual_balances, actual_stats)
    comparative_amount = 0.0
    base_actual_amount = 0.0
    base_comparative_amount = 0.0
    source_type = cstr(getattr(rule_doc, "fuente_tipo", "Balanza") or "Balanza").strip()
    if source_type == "Dato Estadistico":
        comparative_amount = _compute_rule_amount(rule_doc, {}, comparative_stats or {})
        # No hay fuentes estadisticas base dedicadas; se replica en columnas base.
        base_actual_amount = actual_amount
        base_comparative_amount = comparative_amount
    else:
        if comparative_balances:
            comparative_amount = _compute_rule_amount(rule_doc, comparative_balances, {})
        if base_actual_balances:
            base_actual_amount = _compute_rule_amount(rule_doc, base_actual_balances, {})
        if base_comparative_balances:
            base_comparative_amount = _compute_rule_amount(rule_doc, base_comparative_balances, {})
    return actual_amount, comparative_amount, base_actual_amount, base_comparative_amount


def _select_figure_amount(
    rule_doc,
    period,
    actual_amount,
    comparative_amount,
    actual_balances,
    comparative_balances,
    actual_stats,
    comparative_stats,
):
    selected_period = cstr(period or "Actual").strip()
    if selected_period == "Comparativo":
        return comparative_amount
    if selected_period == "Saldo Anterior Actual":
        return _compute_rule_amount(rule_doc, actual_balances, actual_stats, balance_value_field="saldo_anterior")
    if selected_period == "Movimiento Mes Actual":
        return _compute_rule_amount(rule_doc, actual_balances, actual_stats, balance_value_field="movimiento_del_mes")
    if selected_period == "Saldo Anterior Comparativo":
        return _compute_rule_amount(
            rule_doc,
            comparative_balances or {},
            comparative_stats or {},
            balance_value_field="saldo_anterior",
        )
    if selected_period == "Movimiento Mes Comparativo":
        return _compute_rule_amount(
            rule_doc,
            comparative_balances or {},
            comparative_stats or {},
            balance_value_field="movimiento_del_mes",
        )
    return actual_amount


def _select_figure_amounts(
    rule_doc,
    actual_amount,
    comparative_amount,
    actual_balances,
    comparative_balances,
    actual_stats,
    comparative_stats,
):
    if not cint(getattr(rule_doc, "usar_periodos_especiales_cifra", 0) or 0):
        return actual_amount, comparative_amount

    selected_actual = _select_figure_amount(
        rule_doc,
        getattr(rule_doc, "destino_periodo_cifra_actual", "Actual"),
        actual_amount,
        comparative_amount,
        actual_balances,
        comparative_balances,
        actual_stats,
        comparative_stats,
    )
    selected_comparative = _select_figure_amount(
        rule_doc,
        getattr(rule_doc, "destino_periodo_cifra_comparativo", "Comparativo"),
        actual_amount,
        comparative_amount,
        actual_balances,
        comparative_balances,
        actual_stats,
        comparative_stats,
    )
    return selected_actual, selected_comparative


def _select_section_cell_amount(
    rule_doc,
    actual_amount,
    comparative_amount,
    base_actual_amount,
    base_comparative_amount,
    actual_balances,
    comparative_balances,
    actual_stats,
    comparative_stats,
):
    period = cstr(getattr(rule_doc, "destino_periodo_celda", "") or "Actual").strip()
    if period == "Saldo Anterior Actual":
        return _compute_rule_amount(rule_doc, actual_balances, actual_stats, balance_value_field="saldo_anterior")
    if period == "Movimiento Mes Actual":
        return _compute_rule_amount(rule_doc, actual_balances, actual_stats, balance_value_field="movimiento_del_mes")
    if period == "Comparativo":
        return comparative_amount
    if period == "Saldo Anterior Comparativo":
        return _compute_rule_amount(rule_doc, comparative_balances or {}, comparative_stats or {}, balance_value_field="saldo_anterior")
    if period == "Movimiento Mes Comparativo":
        return _compute_rule_amount(
            rule_doc,
            comparative_balances or {},
            comparative_stats or {},
            balance_value_field="movimiento_del_mes",
        )
    if period == "Base Actual":
        return base_actual_amount
    if period == "Base Comparativo":
        return base_comparative_amount
    return actual_amount


def _find_state_line(doc, code):
    code = _normalize(code)
    for row in doc.lineas or []:
        if _normalize(getattr(row, "codigo_linea", "")) == code:
            return row
    return None


def _find_note_figure(doc, code):
    code = _normalize(code)
    for row in doc.cifras_nota or []:
        if _normalize(getattr(row, "codigo_cifra", "")) == code:
            return row
    return None


def _find_section_cell(doc, codigo_tabla, codigo_fila, codigo_columna):
    table_code = _normalize(codigo_tabla)
    row_code = _normalize(codigo_fila)
    col_code = _normalize(codigo_columna)
    for row in doc.celdas_tabulares or []:
        if (
            _normalize(getattr(row, "codigo_tabla", "")) == table_code
            and _normalize(getattr(row, "codigo_fila", "")) == row_code
            and _normalize(getattr(row, "codigo_columna", "")) == col_code
        ):
            return row
    return None


def _find_section_row_definition(doc, codigo_tabla, codigo_fila):
    table_code = _normalize(codigo_tabla)
    row_code = _normalize(codigo_fila)
    for row in doc.filas_tabulares or []:
        if _normalize(getattr(row, "codigo_tabla", "")) == table_code and _normalize(getattr(row, "codigo_fila", "")) == row_code:
            return row
    return None


def _find_section_column_definition(doc, codigo_tabla, codigo_columna):
    table_code = _normalize(codigo_tabla)
    col_code = _normalize(codigo_columna)
    for row in doc.columnas_tabulares or []:
        if _normalize(getattr(row, "codigo_tabla", "")) == table_code and _normalize(getattr(row, "codigo_columna", "")) == col_code:
            return row
    return None


def _resolve_rule_targets(rule_doc, package_name):
    """Resolve rule destinations within the given package using stable codes only."""
    destino = cstr(rule_doc.destino_tipo or "").strip()
    targets = {}

    if destino == "Linea Estado":
        codigo_estado = _normalize(getattr(rule_doc, "destino_codigo_estado", ""))
        if not codigo_estado:
            return False, _("La regla {0} no tiene codigo de estado destino.").format(rule_doc.name), targets

        names = frappe.get_all(
            "Estado Financiero EEFF",
            filters={"paquete_eeff": package_name, "codigo_estado": codigo_estado},
            pluck="name",
            limit_page_length=2,
        )
        if not names:
            return False, _("La regla {0} no encontro un estado con codigo {1} dentro del paquete.").format(
                rule_doc.name, codigo_estado
            ), targets
        targets["estado_name"] = names[0]
        return True, None, targets

    if destino in ("Cifra Nota", "Celda Seccion Nota"):
        numero_nota = _normalize(getattr(rule_doc, "destino_numero_nota", ""))
        if not numero_nota:
            return False, _("La regla {0} no tiene numero de nota destino.").format(rule_doc.name), targets

        note_name, _, _ = find_note_name(package_name, numero_nota)
        if not note_name:
            return False, _("La regla {0} no encontro una nota con numero {1} dentro del paquete.").format(
                rule_doc.name, numero_nota
            ), targets
        targets["note_name"] = note_name

        if destino == "Celda Seccion Nota":
            codigo_seccion = _normalize(getattr(rule_doc, "destino_codigo_seccion", ""))
            if not codigo_seccion:
                return False, _("La regla {0} no tiene codigo de seccion destino.").format(rule_doc.name), targets

            section_names = frappe.get_all(
                "Seccion Nota EEFF",
                filters={"nota_eeff": note_name, "codigo_seccion": codigo_seccion},
                pluck="name",
                limit_page_length=2,
            )
            if not section_names:
                return False, _("La regla {0} no encontro una seccion con codigo {1} dentro de la nota destino.").format(
                    rule_doc.name, codigo_seccion
                ), targets
            targets["section_name"] = section_names[0]

        return True, None, targets

    if destino == "Linea Factsheet":
        codigo_factsheet = _normalize(getattr(rule_doc, "destino_codigo_factsheet", ""))
        if not codigo_factsheet:
            return False, _("La regla {0} no tiene codigo de factsheet destino.").format(rule_doc.name), targets

        names = frappe.get_all(
            "Factsheet",
            filters={"paquete_eeff": package_name, "codigo_factsheet": codigo_factsheet},
            pluck="name",
            limit_page_length=2,
        )
        if not names:
            return False, _("La regla {0} no encontro un factsheet con codigo {1} dentro del paquete.").format(
                rule_doc.name, codigo_factsheet
            ), targets
        targets["factsheet_name"] = names[0]
        return True, None, targets

    return False, _("La regla {0} tiene un tipo de destino no valido.").format(rule_doc.name), targets


def _reset_package_targets(package_name):
    for name in frappe.get_all("Estado Financiero EEFF", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=200):
        doc = frappe.get_doc("Estado Financiero EEFF", name)
        for row in doc.lineas or []:
            if cint(getattr(row, "es_titulo", 0)):
                row.monto_actual = None
                row.monto_comparativo = None
                row.monto_base_actual = None
                row.monto_base_comparativo = None
                continue
            if not cint(getattr(row, "es_manual", 0)):
                row.monto_actual = 0
                row.monto_comparativo = 0
                row.monto_base_actual = 0
                row.monto_base_comparativo = 0
        doc.save(ignore_permissions=True)

    for name in frappe.get_all("Nota EEFF", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=300):
        doc = frappe.get_doc("Nota EEFF", name)
        for row in doc.cifras_nota or []:
            if cint(getattr(row, "es_linea_blanco", 0)) or cint(getattr(row, "es_titulo", 0)):
                row.monto_actual = None
                row.monto_comparativo = None
                row.valor_texto_actual = ""
                row.valor_texto_comparativo = ""
                row.origen_dato = "Manual"
                continue
            if not cint(getattr(row, "es_manual", 0)):
                row.monto_actual = 0
                row.monto_comparativo = 0
                row.valor_texto_actual = ""
                row.valor_texto_comparativo = ""
                row.origen_dato = "Manual"
        doc.save(ignore_permissions=True)

    for name in frappe.get_all("Seccion Nota EEFF", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=600):
        doc = frappe.get_doc("Seccion Nota EEFF", name)
        for cell in doc.celdas_tabulares or []:
            if not cint(getattr(cell, "es_manual", 0)):
                cell.valor_numero = 0
                cell.valor_texto = ""
                cell.origen_dato = "Manual"
                cell.ultima_regla_mapeo = None
        doc.save(ignore_permissions=True)

    for name in frappe.get_all("Factsheet", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=200):
        doc = frappe.get_doc("Factsheet", name)
        for row in doc.lineas or []:
            if cstr(getattr(row, "origen_dato", "")) != "Manual":
                row.monto_actual = 0
                row.monto_comparativo = 0
        doc.save(ignore_permissions=True)


def aplicar_mapeo_paquete(paquete_name):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))

    package = frappe.get_doc("Paquete EEFF", paquete_name)
    if not package.balanza_comprobacion_eeff:
        frappe.throw(_("El paquete no tiene balanza vinculada."), title=_("Balanza Requerida"))

    balanza = frappe.get_doc("Balanza Comprobacion EEFF", package.balanza_comprobacion_eeff)
    balances = _build_balance_map(balanza)
    comparative_balances = None
    if cstr(getattr(package, "balanza_comparativa_eeff", "") or "").strip():
        if frappe.db.exists("Balanza Comprobacion EEFF", package.balanza_comparativa_eeff):
            comparative_doc = frappe.get_doc("Balanza Comprobacion EEFF", package.balanza_comparativa_eeff)
            comparative_balances = _build_balance_map(comparative_doc)
    base_actual_balances = None
    if cstr(getattr(package, "balanza_base_actual_eeff", "") or "").strip():
        if frappe.db.exists("Balanza Comprobacion EEFF", package.balanza_base_actual_eeff):
            base_actual_doc = frappe.get_doc("Balanza Comprobacion EEFF", package.balanza_base_actual_eeff)
            base_actual_balances = _build_balance_map(base_actual_doc)
    base_comparative_balances = None
    if cstr(getattr(package, "balanza_base_comparativa_eeff", "") or "").strip():
        if frappe.db.exists("Balanza Comprobacion EEFF", package.balanza_base_comparativa_eeff):
            base_comparative_doc = frappe.get_doc("Balanza Comprobacion EEFF", package.balanza_base_comparativa_eeff)
            base_comparative_balances = _build_balance_map(base_comparative_doc)
    actual_stats, comparative_stats = _build_stat_maps(package)

    _reset_package_targets(paquete_name)

    rules = frappe.get_all(
        "Regla Mapeo Contable EEFF",
        filters={"company": package.company, "activo": 1},
        fields=[
            "name",
            "fuente_tipo",
            "destino_tipo",
            "destino_codigo_estado",
            "destino_codigo_factsheet",
            "destino_codigo_linea",
            "destino_numero_nota",
            "destino_codigo_cifra",
            "destino_codigo_seccion",
            "destino_codigo_tabla",
            "destino_seccion_id",
            "destino_codigo_fila",
            "destino_codigo_columna",
            "orden",
        ],
        order_by="orden asc, creation asc",
        limit_page_length=1000,
    )

    touched_states = set()
    touched_notes = set()
    touched_sections = set()
    touched_factsheets = set()
    state_docs = {}
    note_docs = {}
    section_docs = {}
    factsheet_docs = {}
    alertas = []

    def get_state_doc(name):
        doc = state_docs.get(name)
        if not doc:
            doc = frappe.get_doc("Estado Financiero EEFF", name)
            state_docs[name] = doc
        return doc

    def get_note_doc(name):
        doc = note_docs.get(name)
        if not doc:
            doc = frappe.get_doc("Nota EEFF", name)
            note_docs[name] = doc
        return doc

    def get_section_doc(name):
        doc = section_docs.get(name)
        if not doc:
            doc = frappe.get_doc("Seccion Nota EEFF", name)
            section_docs[name] = doc
        return doc

    def get_factsheet_doc(name):
        doc = factsheet_docs.get(name)
        if not doc:
            doc = frappe.get_doc("Factsheet", name)
            factsheet_docs[name] = doc
        return doc

    for rule_row in rules:
        rule = frappe.get_doc("Regla Mapeo Contable EEFF", rule_row.name)
        target_ready, target_alert, resolved = _resolve_rule_targets(rule, package.name)
        if not target_ready:
            alertas.append(target_alert)
            continue
        amount, comparative_amount, base_actual_amount, base_comparative_amount = _compute_rule_amounts(
            rule,
            balances,
            comparative_balances,
            base_actual_balances,
            base_comparative_balances,
            actual_stats,
            comparative_stats,
        )
        source_type = cstr(getattr(rule, "fuente_tipo", "Balanza") or "Balanza").strip()

        destino = cstr(rule.destino_tipo or "").strip()
        if destino == "Linea Estado":
            if not resolved.get("estado_name"):
                alertas.append(_("La regla {0} apunta a un estado inexistente.").format(rule.name))
                continue
            state_doc = get_state_doc(resolved["estado_name"])
            line = _find_state_line(state_doc, rule.destino_codigo_linea)
            if not line:
                state_doc.append(
                    "lineas",
                    {
                        "codigo_linea": _normalize(rule.destino_codigo_linea),
                        "descripcion": rule.destino_codigo_linea,
                    },
                )
                line = state_doc.lineas[-1]
            if cint(getattr(line, "es_titulo", 0)):
                line.monto_actual = None
                line.monto_comparativo = None
                line.monto_base_actual = None
                line.monto_base_comparativo = None
                line.origen_dato = "Manual"
                touched_states.add(state_doc.name)
                continue
            if cint(getattr(line, "es_manual", 0)):
                continue
            line.monto_actual = flt(line.monto_actual or 0) + amount
            line.monto_comparativo = flt(line.monto_comparativo or 0) + comparative_amount
            line.monto_base_actual = flt(line.monto_base_actual or 0) + base_actual_amount
            line.monto_base_comparativo = flt(line.monto_base_comparativo or 0) + base_comparative_amount
            line.origen_dato = source_type
            touched_states.add(state_doc.name)

        elif destino == "Cifra Nota":
            if not resolved.get("note_name"):
                alertas.append(_("La regla {0} apunta a una nota inexistente.").format(rule.name))
                continue
            note_doc = get_note_doc(resolved["note_name"])
            selected_actual_amount, selected_comparative_amount = _select_figure_amounts(
                rule,
                amount,
                comparative_amount,
                balances,
                comparative_balances,
                actual_stats,
                comparative_stats,
            )
            figure = _find_note_figure(note_doc, rule.destino_codigo_cifra)
            if not figure:
                note_doc.append(
                    "cifras_nota",
                    {
                        "codigo_cifra": _normalize(rule.destino_codigo_cifra),
                        "concepto": rule.destino_codigo_cifra,
                        "formato_numero": "Moneda",
                        "valor_texto_actual": "",
                        "valor_texto_comparativo": "",
                    },
                )
                figure = note_doc.cifras_nota[-1]
            if cint(getattr(figure, "es_linea_blanco", 0)) or cint(getattr(figure, "es_titulo", 0)):
                figure.monto_actual = None
                figure.monto_comparativo = None
                figure.valor_texto_actual = ""
                figure.valor_texto_comparativo = ""
                figure.origen_dato = "Manual"
                touched_notes.add(note_doc.name)
                continue
            if cint(getattr(figure, "es_manual", 0)):
                continue
            figure.monto_actual = flt(figure.monto_actual or 0) + selected_actual_amount
            figure.monto_comparativo = flt(figure.monto_comparativo or 0) + selected_comparative_amount
            figure.origen_dato = source_type
            touched_notes.add(note_doc.name)

        elif destino == "Celda Seccion Nota":
            if not resolved.get("section_name"):
                alertas.append(_("La regla {0} apunta a una seccion inexistente.").format(rule.name))
                continue
            section_doc = get_section_doc(resolved["section_name"])
            selected_amount = _select_section_cell_amount(
                rule,
                amount,
                comparative_amount,
                base_actual_amount,
                base_comparative_amount,
                balances,
                comparative_balances,
                actual_stats,
                comparative_stats,
            )
            table_code = _normalize(rule.destino_codigo_tabla or "TABLA_01")
            row_code = _normalize(rule.destino_codigo_fila)
            column_code = _normalize(rule.destino_codigo_columna)
            if row_code and not _find_section_row_definition(section_doc, table_code, row_code):
                section_doc.append(
                    "filas_tabulares",
                    {
                        "codigo_tabla": table_code,
                        "codigo_fila": row_code,
                        "descripcion": rule.destino_codigo_fila,
                        "orden": len(section_doc.filas_tabulares or []) + 1,
                        "nivel": 1,
                        "tipo_fila": "Detalle",
                    },
                )
            if column_code and not _find_section_column_definition(section_doc, table_code, column_code):
                section_doc.append(
                    "columnas_tabulares",
                    {
                        "codigo_tabla": table_code,
                        "codigo_columna": column_code,
                        "etiqueta": rule.destino_codigo_columna,
                        "orden": len(section_doc.columnas_tabulares or []) + 1,
                        "tipo_dato": "Numero",
                        "alineacion": "Right",
                    },
                )
            cell = _find_section_cell(
                section_doc,
                table_code,
                row_code,
                column_code,
            )
            if not cell:
                section_doc.append(
                    "celdas_tabulares",
                    {
                        "codigo_tabla": table_code,
                        "codigo_fila": row_code,
                        "codigo_columna": column_code,
                        "formato_numero": "Numero",
                    },
                )
                cell = section_doc.celdas_tabulares[-1]
            if cint(getattr(cell, "es_manual", 0)):
                continue
            cell.valor_numero = flt(getattr(cell, "valor_numero", 0) or 0) + selected_amount
            cell.origen_dato = source_type
            cell.ultima_regla_mapeo = rule.name
            touched_sections.add(section_doc.name)

        elif destino == "Linea Factsheet":
            if not resolved.get("factsheet_name"):
                alertas.append(_("La regla {0} apunta a un factsheet inexistente.").format(rule.name))
                continue
            fact_doc = get_factsheet_doc(resolved["factsheet_name"])
            line = None
            for row in fact_doc.lineas or []:
                if _normalize(row.codigo_linea) == _normalize(rule.destino_codigo_linea):
                    line = row
                    break
            if not line:
                fact_doc.append("lineas", {
                    "codigo_linea": _normalize(rule.destino_codigo_linea),
                    "descripcion": rule.destino_codigo_linea,
                })
                line = fact_doc.lineas[-1]
            if cstr(getattr(line, "origen_dato", "")) != "Mapeo":
                continue
            line.monto_actual = flt(line.monto_actual or 0) + amount
            line.monto_comparativo = flt(line.monto_comparativo or 0) + comparative_amount
            touched_factsheets.add(fact_doc.name)

    for name in touched_states:
        doc = state_docs.get(name)
        if doc:
            doc.save(ignore_permissions=True)

    for name in touched_notes:
        doc = note_docs.get(name)
        if doc:
            doc.save(ignore_permissions=True)

    for name in touched_sections:
        doc = section_docs.get(name)
        if doc:
            doc.save(ignore_permissions=True)

    for name in touched_factsheets:
        doc = factsheet_docs.get(name)
        if doc:
            doc.save(ignore_permissions=True)

    frappe.db.set_value(
        "Paquete EEFF",
        package.name,
        {
            "estado_preparacion": "En Preparacion" if touched_states or touched_notes or touched_sections or touched_factsheets else package.estado_preparacion,
        },
        update_modified=False,
    )

    return {
        "paquete": package.name,
        "reglas": len(rules),
        "estados_actualizados": len(touched_states),
        "notas_actualizadas": len(touched_notes),
        "secciones_actualizadas": len(touched_sections),
        "factsheets_actualizados": len(touched_factsheets),
        "alertas": alertas,
    }
