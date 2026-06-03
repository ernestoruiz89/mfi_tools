import frappe
from frappe import _
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.utils.nota_eeff import find_note_name
from mfi_tools.mfi_tools.services.formula_engine import FormulaContext, has_data_functions, evaluate_formula

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
            if value_field == "saldo":
                debe = flt(getattr(row, "debe_saldo", 0) or 0)
                haber = flt(getattr(row, "haber_saldo", 0) or 0)
                if debe != 0 or haber != 0:
                    amount = debe - haber
                else:
                    amount = flt(getattr(row, "saldo", 0) or 0)
            elif value_field == "saldo_anterior":
                debe_ant = flt(getattr(row, "debe_saldo_anterior", 0) or 0)
                haber_ant = flt(getattr(row, "haber_saldo_anterior", 0) or 0)
                if debe_ant != 0 or haber_ant != 0:
                    amount = debe_ant - haber_ant
                else:
                    amount = flt(getattr(row, "saldo_anterior", 0) or 0)
            elif value_field == "movimiento_del_mes":
                debe_mov = flt(getattr(row, "debe_mes", 0) or 0)
                haber_mov = flt(getattr(row, "haber_mes", 0) or 0)
                if debe_mov != 0 or haber_mov != 0:
                    amount = debe_mov - haber_mov
                else:
                    amount = flt(getattr(row, "movimiento_del_mes", 0) or 0)
            else:
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
    if not balance_map:
        return 0.0
    field = _normalize_balance_field(campo_balanza)
    amount_field = _normalize_balance_value_field(value_field)
    if amount_field not in balance_map:
        return 0.0
    cost_center = _normalize(centro_costo)
    if cost_center:
        scoped_map = balance_map[amount_field].get(field, {}).get("by_cost_center", {}).get(cost_center, {})
        return _resolve_balance_value(scoped_map, cuenta)
    return _resolve_balance_value(balance_map[amount_field].get(field, {}).get("all", {}), cuenta)


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
    historical_data=None,
):
    if historical_data is None:
        historical_data = {}
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
    if selected_period == "Saldo Cierre Anterior Actual":
        historical = historical_data.get("cierre_anterior_actual_balances", {})
        h_stats = historical_data.get("cierre_anterior_actual_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if selected_period == "Saldo Año Anterior Actual":
        historical = historical_data.get("anio_anterior_actual_balances", {})
        h_stats = historical_data.get("anio_anterior_actual_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if selected_period == "Saldo Cierre Anterior Comparativo":
        historical = historical_data.get("cierre_anterior_comparativo_balances", {})
        h_stats = historical_data.get("cierre_anterior_comparativo_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if selected_period == "Saldo Año Anterior Comparativo":
        historical = historical_data.get("anio_anterior_comparativo_balances", {})
        h_stats = historical_data.get("anio_anterior_comparativo_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if selected_period == "Promedio Movil 12 Meses (Actual)":
        bals = historical_data.get("promedio_12_actual_balances", {})
        sts = historical_data.get("promedio_12_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="saldo") for k in keys)
        return total / 12.0
    if selected_period == "Promedio Movil 12 Meses (Comparativo)":
        bals = historical_data.get("promedio_12_comparativo_balances", {})
        sts = historical_data.get("promedio_12_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="saldo") for k in keys)
        return total / 12.0
    if selected_period == "YTD Actual":
        bals = historical_data.get("ytd_actual_balances", {})
        sts = historical_data.get("ytd_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if selected_period == "YTD Comparativo":
        bals = historical_data.get("ytd_comparativo_balances", {})
        sts = historical_data.get("ytd_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if selected_period == "YTD Año Anterior Actual":
        bals = historical_data.get("ytd_anio_anterior_actual_balances", {})
        sts = historical_data.get("ytd_anio_anterior_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if selected_period == "YTD Año Anterior Comparativo":
        bals = historical_data.get("ytd_anio_anterior_comparativo_balances", {})
        sts = historical_data.get("ytd_anio_anterior_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if selected_period == "Suma Año Completo Anterior Actual":
        bals = historical_data.get("suma_anio_completo_anterior_actual_balances", {})
        sts = historical_data.get("suma_anio_completo_anterior_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if selected_period == "Suma Año Completo Anterior Comparativo":
        bals = historical_data.get("suma_anio_completo_anterior_comparativo_balances", {})
        sts = historical_data.get("suma_anio_completo_anterior_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    return actual_amount

def _select_figure_amounts(
    rule_doc,
    actual_amount,
    comparative_amount,
    actual_balances,
    comparative_balances,
    actual_stats,
    comparative_stats,
    historical_data=None,
):
    if historical_data is None:
        historical_data = {}
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
        historical_data=historical_data,
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
        historical_data=historical_data,
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
    historical_data=None,
):
    if historical_data is None:
        historical_data = {}
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
    if period == "Saldo Cierre Anterior Actual":
        historical = historical_data.get("cierre_anterior_actual_balances", {})
        h_stats = historical_data.get("cierre_anterior_actual_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if period == "Saldo Año Anterior Actual":
        historical = historical_data.get("anio_anterior_actual_balances", {})
        h_stats = historical_data.get("anio_anterior_actual_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if period == "Saldo Cierre Anterior Comparativo":
        historical = historical_data.get("cierre_anterior_comparativo_balances", {})
        h_stats = historical_data.get("cierre_anterior_comparativo_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if period == "Saldo Año Anterior Comparativo":
        historical = historical_data.get("anio_anterior_comparativo_balances", {})
        h_stats = historical_data.get("anio_anterior_comparativo_stats", {})
        return _compute_rule_amount(rule_doc, historical, h_stats, balance_value_field="saldo")
    if period == "Promedio Movil 12 Meses (Actual)":
        bals = historical_data.get("promedio_12_actual_balances", {})
        sts = historical_data.get("promedio_12_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="saldo") for k in keys)
        return total / 12.0
    if period == "Promedio Movil 12 Meses (Comparativo)":
        bals = historical_data.get("promedio_12_comparativo_balances", {})
        sts = historical_data.get("promedio_12_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="saldo") for k in keys)
        return total / 12.0
    if period == "YTD Actual":
        bals = historical_data.get("ytd_actual_balances", {})
        sts = historical_data.get("ytd_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if period == "YTD Comparativo":
        bals = historical_data.get("ytd_comparativo_balances", {})
        sts = historical_data.get("ytd_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if period == "YTD Año Anterior Actual":
        bals = historical_data.get("ytd_anio_anterior_actual_balances", {})
        sts = historical_data.get("ytd_anio_anterior_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if period == "YTD Año Anterior Comparativo":
        bals = historical_data.get("ytd_anio_anterior_comparativo_balances", {})
        sts = historical_data.get("ytd_anio_anterior_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if period == "Suma Año Completo Anterior Actual":
        bals = historical_data.get("suma_anio_completo_anterior_actual_balances", {})
        sts = historical_data.get("suma_anio_completo_anterior_actual_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
    if period == "Suma Año Completo Anterior Comparativo":
        bals = historical_data.get("suma_anio_completo_anterior_comparativo_balances", {})
        sts = historical_data.get("suma_anio_completo_anterior_comparativo_stats", {})
        keys = set(bals.keys()).union(set(sts.keys()))
        if not keys: return 0.0
        total = sum(_compute_rule_amount(rule_doc, bals.get(k, {}), sts.get(k, {}), balance_value_field="movimiento_del_mes") for k in keys)
        return total
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

        note_name, _ignored1, _ignored2 = find_note_name(package_name, numero_nota)
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


def _build_target_lookup_maps(package_name):
    """Pre-build lookup dictionaries for target resolution (Optimization 3).

    Returns a dict with:
      - estado_lookup: {CODIGO_ESTADO_UPPER: name}
      - nota_lookup: {(numero_nota_int, SUB_NOTA_UPPER): name}
      - nota_simple_lookup: {numero_nota_int: name}  (for notes without sub_nota)
      - seccion_lookup: {(nota_name, CODIGO_SECCION_UPPER): name}
      - factsheet_lookup: {CODIGO_FACTSHEET_UPPER: name}
    """
    estado_lookup = {}
    for r in frappe.get_all("Estado Financiero EEFF",
            filters={"paquete_eeff": package_name},
            fields=["name", "codigo_estado"], limit_page_length=200):
        key = _normalize(r.codigo_estado)
        if key:
            estado_lookup[key] = r.name

    nota_lookup = {}
    nota_simple_lookup = {}
    for r in frappe.get_all("Nota EEFF",
            filters={"paquete_eeff": package_name},
            fields=["name", "numero_nota", "sub_nota"], limit_page_length=300):
        numero = cint(r.numero_nota)
        sub = _normalize(r.sub_nota or "")
        if numero:
            nota_lookup[(numero, sub)] = r.name
            if not sub:
                nota_simple_lookup[numero] = r.name

    seccion_lookup = {}
    for s in frappe.get_all("Seccion Nota EEFF",
            filters={"paquete_eeff": package_name},
            fields=["name", "nota_eeff", "codigo_seccion"], limit_page_length=600):
        key = (s.nota_eeff, _normalize(s.codigo_seccion))
        seccion_lookup[key] = s.name

    factsheet_lookup = {}
    for r in frappe.get_all("Factsheet",
            filters={"paquete_eeff": package_name},
            fields=["name", "codigo_factsheet"], limit_page_length=200):
        key = _normalize(r.codigo_factsheet)
        if key:
            factsheet_lookup[key] = r.name

    return {
        "estado_lookup": estado_lookup,
        "nota_lookup": nota_lookup,
        "nota_simple_lookup": nota_simple_lookup,
        "seccion_lookup": seccion_lookup,
        "factsheet_lookup": factsheet_lookup,
    }


def _resolve_rule_targets_cached(rule_doc, lookup_maps):
    """Resolve rule destinations using pre-built lookup maps (O(1) per rule)."""
    destino = cstr(rule_doc.destino_tipo or "").strip()
    targets = {}

    if destino == "Linea Estado":
        codigo_estado = _normalize(getattr(rule_doc, "destino_codigo_estado", ""))
        if not codigo_estado:
            return False, _("La regla {0} no tiene codigo de estado destino.").format(rule_doc.name), targets
        estado_name = lookup_maps["estado_lookup"].get(codigo_estado)
        if not estado_name:
            return False, _("La regla {0} no encontro un estado con codigo {1} dentro del paquete.").format(
                rule_doc.name, codigo_estado
            ), targets
        targets["estado_name"] = estado_name
        return True, None, targets

    if destino in ("Cifra Nota", "Celda Seccion Nota"):
        numero_nota_raw = _normalize(getattr(rule_doc, "destino_numero_nota", ""))
        if not numero_nota_raw:
            return False, _("La regla {0} no tiene numero de nota destino.").format(rule_doc.name), targets

        from mfi_tools.mfi_tools.utils.nota_eeff import parse_note_identifier, normalize_sub_note_key
        numero_nota, sub_nota = parse_note_identifier(numero_nota_raw)
        if not numero_nota:
            return False, _("La regla {0} no encontro una nota con numero {1} dentro del paquete.").format(
                rule_doc.name, numero_nota_raw
            ), targets

        sub_key = _normalize(sub_nota or "")
        note_name = lookup_maps["nota_lookup"].get((numero_nota, sub_key))
        if not note_name and not sub_key:
            note_name = lookup_maps["nota_simple_lookup"].get(numero_nota)
        if not note_name:
            return False, _("La regla {0} no encontro una nota con numero {1} dentro del paquete.").format(
                rule_doc.name, numero_nota_raw
            ), targets
        targets["note_name"] = note_name

        if destino == "Celda Seccion Nota":
            codigo_seccion = _normalize(getattr(rule_doc, "destino_codigo_seccion", ""))
            if not codigo_seccion:
                return False, _("La regla {0} no tiene codigo de seccion destino.").format(rule_doc.name), targets
            section_name = lookup_maps["seccion_lookup"].get((note_name, codigo_seccion))
            if not section_name:
                return False, _("La regla {0} no encontro una seccion con codigo {1} dentro de la nota destino.").format(
                    rule_doc.name, codigo_seccion
                ), targets
            targets["section_name"] = section_name

        return True, None, targets

    if destino == "Linea Factsheet":
        codigo_factsheet = _normalize(getattr(rule_doc, "destino_codigo_factsheet", ""))
        if not codigo_factsheet:
            return False, _("La regla {0} no tiene codigo de factsheet destino.").format(rule_doc.name), targets
        factsheet_name = lookup_maps["factsheet_lookup"].get(codigo_factsheet)
        if not factsheet_name:
            return False, _("La regla {0} no encontro un factsheet con codigo {1} dentro del paquete.").format(
                rule_doc.name, codigo_factsheet
            ), targets
        targets["factsheet_name"] = factsheet_name
        return True, None, targets

    return False, _("La regla {0} tiene un tipo de destino no valido.").format(rule_doc.name), targets


def _reset_package_targets(package_name):
    """Reset all mapping targets in the package using bulk SQL (Optimization 1).

    This is safe because the reset only zeroes/nullifies amounts without
    needing controller validation hooks.  The controllers will run their
    validate logic when the documents are saved after mapping rules are
    applied.
    """
    # --- Estado Financiero EEFF ---
    # Non-manual, non-titulo lines -> zero
    frappe.db.sql("""
        UPDATE `tabLinea Estado Financiero EEFF` child
        INNER JOIN `tabEstado Financiero EEFF` parent ON parent.name = child.parent
        SET child.monto_actual = 0, child.monto_comparativo = 0,
            child.monto_base_actual = 0, child.monto_base_comparativo = 0,
            child.origen_dato = CASE WHEN child.origen_dato = 'Formula' THEN 'Formula' ELSE 'Manual' END
        WHERE parent.paquete_eeff = %s
          AND IFNULL(child.es_titulo, 0) = 0
          AND IFNULL(child.origen_dato, 'Manual') != 'Manual'
    """, (package_name,))
    # Titulo lines -> zero (NOT NULL constraint on Currency fields)
    frappe.db.sql("""
        UPDATE `tabLinea Estado Financiero EEFF` child
        INNER JOIN `tabEstado Financiero EEFF` parent ON parent.name = child.parent
        SET child.monto_actual = 0, child.monto_comparativo = 0,
            child.monto_base_actual = 0, child.monto_base_comparativo = 0,
            child.origen_dato = 'Manual'
        WHERE parent.paquete_eeff = %s
          AND IFNULL(child.es_titulo, 0) = 1
    """, (package_name,))

    # --- Nota EEFF (Cifra Nota EEFF) ---
    # Non-manual, non-titulo, non-blank lines -> zero
    frappe.db.sql("""
        UPDATE `tabCifra Nota EEFF` child
        INNER JOIN `tabNota EEFF` parent ON parent.name = child.parent
        SET child.monto_actual = 0, child.monto_comparativo = 0,
            child.valor_texto_actual = '', child.valor_texto_comparativo = '',
            child.origen_dato = CASE WHEN child.origen_dato = 'Formula' THEN 'Formula' ELSE 'Manual' END
        WHERE parent.paquete_eeff = %s
          AND IFNULL(child.es_linea_blanco, 0) = 0
          AND IFNULL(child.es_titulo, 0) = 0
          AND IFNULL(child.origen_dato, 'Manual') != 'Manual'
    """, (package_name,))
    # Titulo or blank lines -> zero (NOT NULL constraint on Currency fields)
    frappe.db.sql("""
        UPDATE `tabCifra Nota EEFF` child
        INNER JOIN `tabNota EEFF` parent ON parent.name = child.parent
        SET child.monto_actual = 0, child.monto_comparativo = 0,
            child.valor_texto_actual = '', child.valor_texto_comparativo = '',
            child.origen_dato = 'Manual'
        WHERE parent.paquete_eeff = %s
          AND (IFNULL(child.es_linea_blanco, 0) = 1 OR IFNULL(child.es_titulo, 0) = 1)
    """, (package_name,))

    # --- Seccion Nota EEFF (Celda Seccion Nota EEFF) ---
    frappe.db.sql("""
        UPDATE `tabCelda Seccion Nota EEFF` child
        INNER JOIN `tabSeccion Nota EEFF` parent ON parent.name = child.parent
        SET child.valor_numero = 0, child.valor_texto = '',
            child.origen_dato = CASE WHEN child.origen_dato = 'Formula' THEN 'Formula' ELSE 'Manual' END, 
            child.ultima_regla_mapeo = NULL
        WHERE parent.paquete_eeff = %s
          AND IFNULL(child.origen_dato, 'Manual') != 'Manual'
    """, (package_name,))

    # --- Factsheet (Linea Factsheet) ---
    frappe.db.sql("""
        UPDATE `tabLinea Factsheet` child
        INNER JOIN `tabFactsheet` parent ON parent.name = child.parent
        SET child.monto_actual = 0, child.monto_comparativo = 0
        WHERE parent.paquete_eeff = %s
          AND IFNULL(child.origen_dato, 'Manual') != 'Manual'
    """, (package_name,))

    frappe.db.commit()


def aplicar_mapeo_paquete(paquete_name):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))

    package = frappe.get_doc("Paquete EEFF", paquete_name)
    if not package.balanza_comprobacion_eeff:
        frappe.throw(_("El paquete no tiene balanza vinculada."), title=_("Balanza Requerida"))

    balanza = frappe.get_doc("Balanza Comprobacion EEFF", package.balanza_comprobacion_eeff)
    balances = _build_balance_map(balanza)
    comparative_balances = None
    comparative_doc = None
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

    historical_data = {}
    _historical_cache = {}

    def _get_historical(doctype, field_filters, anio, mes):
        cache_key = (doctype, anio, mes, tuple(sorted(field_filters.items())))
        if cache_key in _historical_cache:
            return _historical_cache[cache_key]
        filters = field_filters.copy()
        filters["anio"] = anio
        filters["mes"] = mes
        docs = frappe.get_all(doctype, filters=filters, pluck="name", limit_page_length=1)
        result = {}
        if docs:
            doc = frappe.get_doc(doctype, docs[0])
            if doctype == "Balanza Comprobacion EEFF":
                result = _build_balance_map(doc)
            else:
                stats = {}
                for row in getattr(doc, "lineas", []):
                    code = _normalize(getattr(row, "codigo_dato", ""))
                    if code:
                        stats[code] = flt(getattr(row, "valor_actual", 0) or 0)
                result = stats
        _historical_cache[cache_key] = result
        return result

    MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

    def _get_historical_12_months(doctype, field_filters, anio, mes):
        try:
            mes_idx = MESES.index(mes)
        except ValueError:
            return {}
        
        results = {}
        curr_anio = anio
        curr_mes_idx = mes_idx
        
        for _ in range(12):
            curr_mes = MESES[curr_mes_idx]
            m = _get_historical(doctype, field_filters, curr_anio, curr_mes)
            if m:
                results[(curr_anio, curr_mes)] = m
            
            curr_mes_idx -= 1
            if curr_mes_idx < 0:
                curr_mes_idx = 11
                curr_anio -= 1
                
        return results

    def _get_historical_ytd(doctype, field_filters, anio, mes):
        try:
            mes_idx = MESES.index(mes)
        except ValueError:
            return {}
        
        results = {}
        for idx in range(mes_idx + 1):
            curr_mes = MESES[idx]
            m = _get_historical(doctype, field_filters, anio, curr_mes)
            if m:
                results[(anio, curr_mes)] = m
                
        return results

    if balanza:
        f_bal = {"company": balanza.company, "moneda": balanza.moneda}
        historical_data["cierre_anterior_actual_balances"] = _get_historical("Balanza Comprobacion EEFF", f_bal, balanza.anio - 1, "Diciembre")
        historical_data["anio_anterior_actual_balances"] = _get_historical("Balanza Comprobacion EEFF", f_bal, balanza.anio - 1, balanza.mes)
        historical_data["promedio_12_actual_balances"] = _get_historical_12_months("Balanza Comprobacion EEFF", f_bal, balanza.anio, balanza.mes)
        historical_data["ytd_actual_balances"] = _get_historical_ytd("Balanza Comprobacion EEFF", f_bal, balanza.anio, balanza.mes)
        historical_data["ytd_anio_anterior_actual_balances"] = _get_historical_ytd("Balanza Comprobacion EEFF", f_bal, balanza.anio - 1, balanza.mes)
        historical_data["suma_anio_completo_anterior_actual_balances"] = _get_historical_ytd("Balanza Comprobacion EEFF", f_bal, balanza.anio - 1, "Diciembre")

    if comparative_doc:
        f_comp = {"company": comparative_doc.company, "moneda": comparative_doc.moneda}
        historical_data["cierre_anterior_comparativo_balances"] = _get_historical("Balanza Comprobacion EEFF", f_comp, comparative_doc.anio - 1, "Diciembre")
        historical_data["anio_anterior_comparativo_balances"] = _get_historical("Balanza Comprobacion EEFF", f_comp, comparative_doc.anio - 1, comparative_doc.mes)
        historical_data["promedio_12_comparativo_balances"] = _get_historical_12_months("Balanza Comprobacion EEFF", f_comp, comparative_doc.anio, comparative_doc.mes)
        historical_data["ytd_comparativo_balances"] = _get_historical_ytd("Balanza Comprobacion EEFF", f_comp, comparative_doc.anio, comparative_doc.mes)
        historical_data["ytd_anio_anterior_comparativo_balances"] = _get_historical_ytd("Balanza Comprobacion EEFF", f_comp, comparative_doc.anio - 1, comparative_doc.mes)
        historical_data["suma_anio_completo_anterior_comparativo_balances"] = _get_historical_ytd("Balanza Comprobacion EEFF", f_comp, comparative_doc.anio - 1, "Diciembre")

    act_stat_name = getattr(package, "datos_estadisticos_actual_eeff", "")
    if act_stat_name and frappe.db.exists("Datos Estadisticos EEFF", act_stat_name):
        act_stat_doc = frappe.get_doc("Datos Estadisticos EEFF", act_stat_name)
        f_act_stat = {"company": act_stat_doc.company, "moneda": act_stat_doc.moneda}
        historical_data["cierre_anterior_actual_stats"] = _get_historical("Datos Estadisticos EEFF", f_act_stat, act_stat_doc.anio - 1, "Diciembre")
        historical_data["anio_anterior_actual_stats"] = _get_historical("Datos Estadisticos EEFF", f_act_stat, act_stat_doc.anio - 1, act_stat_doc.mes)
        historical_data["promedio_12_actual_stats"] = _get_historical_12_months("Datos Estadisticos EEFF", f_act_stat, act_stat_doc.anio, act_stat_doc.mes)
        historical_data["ytd_actual_stats"] = _get_historical_ytd("Datos Estadisticos EEFF", f_act_stat, act_stat_doc.anio, act_stat_doc.mes)
        historical_data["ytd_anio_anterior_actual_stats"] = _get_historical_ytd("Datos Estadisticos EEFF", f_act_stat, act_stat_doc.anio - 1, act_stat_doc.mes)
        historical_data["suma_anio_completo_anterior_actual_stats"] = _get_historical_ytd("Datos Estadisticos EEFF", f_act_stat, act_stat_doc.anio - 1, "Diciembre")

    comp_stat_name = getattr(package, "datos_estadisticos_comparativo_eeff", "")
    if comp_stat_name and frappe.db.exists("Datos Estadisticos EEFF", comp_stat_name):
        comp_stat_doc = frappe.get_doc("Datos Estadisticos EEFF", comp_stat_name)
        f_comp_stat = {"company": comp_stat_doc.company, "moneda": comp_stat_doc.moneda}
        historical_data["cierre_anterior_comparativo_stats"] = _get_historical("Datos Estadisticos EEFF", f_comp_stat, comp_stat_doc.anio - 1, "Diciembre")
        historical_data["anio_anterior_comparativo_stats"] = _get_historical("Datos Estadisticos EEFF", f_comp_stat, comp_stat_doc.anio - 1, comp_stat_doc.mes)
        historical_data["promedio_12_comparativo_stats"] = _get_historical_12_months("Datos Estadisticos EEFF", f_comp_stat, comp_stat_doc.anio, comp_stat_doc.mes)
        historical_data["ytd_comparativo_stats"] = _get_historical_ytd("Datos Estadisticos EEFF", f_comp_stat, comp_stat_doc.anio, comp_stat_doc.mes)
        historical_data["ytd_anio_anterior_comparativo_stats"] = _get_historical_ytd("Datos Estadisticos EEFF", f_comp_stat, comp_stat_doc.anio - 1, comp_stat_doc.mes)
        historical_data["suma_anio_completo_anterior_comparativo_stats"] = _get_historical_ytd("Datos Estadisticos EEFF", f_comp_stat, comp_stat_doc.anio - 1, "Diciembre")

    _reset_package_targets(paquete_name)

    # --- Optimization 2: Batch-load all rules + their child tables ---
    rules = frappe.get_all(
        "Regla Mapeo Contable EEFF",
        filters={"company": package.company, "activo": 1},
        fields=["*"],
        order_by="orden asc, creation asc",
        limit_page_length=0,
    )

    # Pre-load all child tables in ONE query
    rule_names = [r.name for r in rules]
    cuentas_by_rule = {}
    if rule_names:
        all_cuentas = frappe.get_all(
            "Cuenta Regla Mapeo EEFF",
            filters={"parent": ["in", rule_names]},
            fields=["parent", "cuenta", "operacion", "porcentaje", "campo_balanza", "centro_costo"],
            order_by="idx asc",
            limit_page_length=0,
        )
        for c in all_cuentas:
            cuentas_by_rule.setdefault(c.parent, []).append(c)

    # Attach child tables to each rule object
    for rule in rules:
        rule.cuentas = cuentas_by_rule.get(rule.name, [])

    # --- Optimization 3: Pre-build target lookup maps ---
    lookup_maps = _build_target_lookup_maps(package.name)

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

    for rule in rules:
        # rule already has all fields + cuentas preloaded (Optimization 2)
        target_ready, target_alert, resolved = _resolve_rule_targets_cached(rule, lookup_maps)
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
            if getattr(line, "origen_dato", "Manual") == "Manual":
                continue

            selected_actual_amount, selected_comparative_amount = _select_figure_amounts(
                rule,
                amount,
                comparative_amount,
                balances,
                comparative_balances,
                actual_stats,
                comparative_stats,
                historical_data=historical_data,
            )

            line.monto_actual = flt(line.monto_actual or 0) + selected_actual_amount
            line.monto_comparativo = flt(line.monto_comparativo or 0) + selected_comparative_amount
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
                historical_data=historical_data,
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
            if getattr(figure, "origen_dato", "Manual") == "Manual":
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
                historical_data=historical_data,
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
            if getattr(cell, "origen_dato", "Manual") == "Manual":
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

            selected_actual_amount, selected_comparative_amount = _select_figure_amounts(
                rule,
                amount,
                comparative_amount,
                balances,
                comparative_balances,
                actual_stats,
                comparative_stats,
                historical_data=historical_data,
            )

            line.monto_actual = flt(line.monto_actual or 0) + selected_actual_amount
            line.monto_comparativo = flt(line.monto_comparativo or 0) + selected_comparative_amount
            touched_factsheets.add(fact_doc.name)

    # --- Evaluate Data Formulas ---
    formula_ctx = FormulaContext(
        actual_balances=balances,
        comparative_balances=comparative_balances,
        base_actual_balances=base_actual_balances,
        base_comparative_balances=base_comparative_balances,
        actual_stats=actual_stats,
        comparative_stats=comparative_stats,
        historical_data=historical_data
    )

    for name in touched_states:
        doc = state_docs.get(name)
        if doc:
            for row in doc.lineas or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula_lineas", "")):
                    expr = row.formula_lineas
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")
                    row.monto_base_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_base_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")

    for name in touched_notes:
        doc = note_docs.get(name)
        if doc:
            for row in doc.cifras_nota or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula_cifras", "")):
                    expr = row.formula_cifras
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")

    for name in touched_sections:
        doc = section_docs.get(name)
        if doc:
            for row in doc.celdas_tabulares or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula_celda", "")):
                    expr = row.formula_celda
                    # Sections mix actual/comp within cells, so evaluate as actual context always
                    row.valor_numero = evaluate_formula(expr, formula_ctx, "actual")

    for name in touched_factsheets:
        doc = factsheet_docs.get(name)
        if doc:
            for row in doc.lineas or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula", "")):
                    expr = row.formula
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")

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

    # --- Recalculate untouched target docs with formulas ---
    # Recalculate untouched Estados Financieros EEFF with formulas
    states_with_formulas = set(frappe.db.sql_list("""
        SELECT DISTINCT child.parent
        FROM `tabLinea Estado Financiero EEFF` child
        INNER JOIN `tabEstado Financiero EEFF` parent ON parent.name = child.parent
        WHERE parent.paquete_eeff = %s AND child.origen_dato = 'Formula'
    """, (package.name,)))
    states_to_recalc = states_with_formulas - touched_states
    if states_to_recalc:
        for state_name in states_to_recalc:
            state_doc = frappe.get_doc("Estado Financiero EEFF", state_name)
            for row in state_doc.lineas or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula_lineas", "")):
                    expr = row.formula_lineas
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")
                    row.monto_base_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_base_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")
            state_doc.save(ignore_permissions=True)
            touched_states.add(state_name)

    # Recalculate untouched Notas EEFF with formulas
    notes_with_formulas = set(frappe.db.sql_list("""
        SELECT DISTINCT child.parent
        FROM `tabCifra Nota EEFF` child
        INNER JOIN `tabNota EEFF` parent ON parent.name = child.parent
        WHERE parent.paquete_eeff = %s AND child.origen_dato = 'Formula'
    """, (package.name,)))
    notes_to_recalc = notes_with_formulas - touched_notes
    if notes_to_recalc:
        for note_name in notes_to_recalc:
            note_doc = frappe.get_doc("Nota EEFF", note_name)
            for row in note_doc.cifras_nota or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula_cifras", "")):
                    expr = row.formula_cifras
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")
            note_doc.save(ignore_permissions=True)
            touched_notes.add(note_name)

    # Recalculate untouched Secciones Nota EEFF with formulas
    sections_with_formulas = set(frappe.db.sql_list("""
        SELECT DISTINCT child.parent
        FROM `tabCelda Seccion Nota EEFF` child
        INNER JOIN `tabSeccion Nota EEFF` parent ON parent.name = child.parent
        WHERE parent.paquete_eeff = %s AND child.origen_dato = 'Formula'
    """, (package.name,)))
    sections_to_recalc = sections_with_formulas - touched_sections
    if sections_to_recalc:
        for section_name in sections_to_recalc:
            section_doc = frappe.get_doc("Seccion Nota EEFF", section_name)
            for row in section_doc.celdas_tabulares or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula_celda", "")):
                    expr = row.formula_celda
                    row.valor_numero = evaluate_formula(expr, formula_ctx, "actual")
            section_doc.save(ignore_permissions=True)
            touched_sections.add(section_name)

    # --- Optimization 4: Only recalculate factsheets with formulas ---
    # Identify factsheets that have formula lines (cross-factsheet references)
    fs_with_formulas = set(frappe.db.sql_list("""
        SELECT DISTINCT child.parent
        FROM `tabLinea Factsheet` child
        INNER JOIN `tabFactsheet` parent ON parent.name = child.parent
        WHERE parent.paquete_eeff = %s AND child.origen_dato = 'Formula'
    """, (package.name,)))

    # Factsheets with formulas that were NOT already processed by the mapping rules loop
    fs_to_recalc = fs_with_formulas - touched_factsheets
    if fs_to_recalc:
        for fs_name in frappe.get_all("Factsheet",
                filters={"paquete_eeff": package.name, "name": ["in", list(fs_to_recalc)]},
                pluck="name",
                order_by="numero_factsheet asc, codigo_factsheet asc",
                limit_page_length=200):
            fs_doc = frappe.get_doc("Factsheet", fs_name)
            # Evaluate data-function formulas (EST, BAL, YTD, etc.) via formula engine
            for row in fs_doc.lineas or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula", "")):
                    expr = row.formula
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")
            fs_doc.save(ignore_permissions=True)

    # Re-save touched factsheets that also have formulas (to pick up cross-references
    # that may have changed after other factsheets were saved above)
    fs_touched_with_formulas = touched_factsheets & fs_with_formulas
    if fs_touched_with_formulas:
        for fs_name in frappe.get_all("Factsheet",
                filters={"paquete_eeff": package.name, "name": ["in", list(fs_touched_with_formulas)]},
                pluck="name",
                order_by="numero_factsheet asc, codigo_factsheet asc",
                limit_page_length=200):
            fs_doc = frappe.get_doc("Factsheet", fs_name)
            # Re-evaluate data-function formulas after cross-references are updated
            for row in fs_doc.lineas or []:
                if getattr(row, "origen_dato", "") == "Formula" and has_data_functions(getattr(row, "formula", "")):
                    expr = row.formula
                    row.monto_actual = evaluate_formula(expr, formula_ctx, "actual")
                    row.monto_comparativo = evaluate_formula(expr, formula_ctx, "comparativo")
            fs_doc.save(ignore_permissions=True)


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
