import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from mfi_tools.mfi_tools.utils.customer import get_customer_display, get_customer_display_map
from mfi_tools.mfi_tools.utils.nota_eeff import build_note_identifier, get_package_note_rows
from mfi_tools.mfi_tools.utils.nota_tablas import (
    build_complex_section_tables,
    normalize_column_code,
    normalize_row_code,
    normalize_table_code,
)

MESES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
NOTE_RULE_TARGET_TYPES = ("Cifra Nota", "Celda Seccion Nota")
BALANCE_FIELDS = ("codigo_cuenta", "descripcion_cuenta")
FIGURE_VALUE_PERIODS = (
    "Actual",
    "Comparativo",
    "Saldo Anterior Actual",
    "Movimiento Mes Actual",
    "Saldo Anterior Comparativo",
    "Movimiento Mes Comparativo",
)
SECTION_CELL_PERIODS = (
    "Actual",
    "Comparativo",
    "Base Actual",
    "Base Comparativo",
    "Saldo Anterior Actual",
    "Movimiento Mes Actual",
    "Saldo Anterior Comparativo",
    "Movimiento Mes Comparativo",
)


def _clean(value):
    return cstr(value or "").strip()


def _normalize_code(value):
    return cstr(value or "").strip().upper()


def _ensure_page_access(write=False):
    required = [
        ("Paquete EEFF", "read"),
        ("Nota EEFF", "read"),
        ("Seccion Nota EEFF", "read"),
        ("Regla Mapeo Contable EEFF", "read"),
    ]
    if write:
        required.extend(
            [
                ("Regla Mapeo Contable EEFF", "create"),
                ("Regla Mapeo Contable EEFF", "write"),
            ]
        )
    for doctype, ptype in required:
        if frappe.has_permission(doctype, ptype=ptype):
            continue
        frappe.throw(
            _("No tienes permisos para usar el helper de mapeo de notas EEFF."),
            frappe.PermissionError,
        )


def _build_filters(cliente=None, anio=None, mes=None):
    filters = {}
    if _clean(cliente):
        filters["cliente"] = _clean(cliente)
    if cint(anio or 0):
        filters["anio"] = cint(anio)
    if _clean(mes):
        filters["mes"] = _clean(mes)
    return filters


def _get_clients():
    rows = frappe.get_all(
        "Paquete EEFF",
        fields=["cliente"],
        filters={"cliente": ["is", "set"]},
        distinct=True,
        order_by="cliente asc",
        limit_page_length=2000,
    )
    names = sorted({_clean(row.cliente) for row in rows if _clean(row.cliente)})
    label_map = get_customer_display_map(names)
    return [{"value": name, "label": label_map.get(name, name)} for name in names]


def _get_packages(cliente=None, anio=None, mes=None):
    rows = frappe.get_all(
        "Paquete EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes),
        fields=["name", "cliente", "anio", "mes", "periodo_nombre", "estado_preparacion", "modified"],
        order_by="modified desc",
        limit_page_length=500,
    )
    label_map = get_customer_display_map([row.cliente for row in rows])
    output = []
    for row in rows:
        customer_label = label_map.get(row.cliente, row.cliente)
        output.append(
            {
                "value": row.name,
                "label": f"{row.name} | {customer_label or row.cliente or '-'} | {row.mes or '-'} {row.anio or '-'} | {row.estado_preparacion or 'Borrador'}",
                "cliente": row.cliente,
                "cliente_label": customer_label,
                "anio": row.anio,
                "mes": row.mes,
                "periodo_nombre": row.periodo_nombre,
                "estado_preparacion": row.estado_preparacion,
            }
        )
    return output


def _serialize_note_rows(package_name):
    rows = get_package_note_rows(
        package_name,
        fields=["estructura_nota", "estado_aprobacion", "total_secciones_complejas", "total_cifras"],
        limit_page_length=1000,
    )
    return [
        {
            "name": row.name,
            "numero_nota": row.numero_nota,
            "sub_nota": row.sub_nota,
            "identificador_nota": build_note_identifier(row.numero_nota, row.sub_nota),
            "titulo": row.titulo,
            "estructura_nota": row.estructura_nota or "Simple",
            "estado_aprobacion": row.estado_aprobacion or "Borrador",
            "total_secciones_complejas": cint(row.total_secciones_complejas or 0),
            "total_cifras": cint(row.total_cifras or 0),
            "label": _("Nota {0}. {1}").format(
                build_note_identifier(row.numero_nota, row.sub_nota) or "-",
                row.titulo or _("Sin titulo"),
            ),
        }
        for row in rows
    ]


def _serialize_rule(row):
    destino = cstr(row.destino_tipo or "").strip()
    if destino == "Cifra Nota":
        target_label = cstr(row.destino_codigo_cifra or "-").strip() or "-"
    else:
        target_label = " / ".join(
            [
                cstr(row.destino_codigo_seccion or "-").strip() or "-",
                cstr(row.destino_codigo_tabla or "-").strip() or "-",
                cstr(row.destino_codigo_fila or "-").strip() or "-",
                cstr(row.destino_codigo_columna or "-").strip() or "-",
            ]
        )

    return {
        "name": row.name,
        "nombre_regla": cstr(getattr(row, "nombre_regla", "") or row.name).strip(),
        "activo": cint(row.activo or 0),
        "orden": cint(row.orden or 0),
        "fuente_tipo": cstr(row.fuente_tipo or "Balanza").strip() or "Balanza",
        "destino_tipo": destino,
        "nota_eeff": cstr(getattr(row, "nota_eeff", "") or "").strip(),
        "seccion_nota_eeff": cstr(getattr(row, "seccion_nota_eeff", "") or "").strip(),
        "destino_numero_nota": cstr(getattr(row, "destino_numero_nota", "") or "").strip(),
        "destino_codigo_cifra": cstr(row.destino_codigo_cifra or "").strip(),
        "usar_periodos_especiales_cifra": cint(getattr(row, "usar_periodos_especiales_cifra", 0) or 0),
        "destino_periodo_cifra_actual": cstr(getattr(row, "destino_periodo_cifra_actual", "") or "Actual").strip() or "Actual",
        "destino_periodo_cifra_comparativo": cstr(
            getattr(row, "destino_periodo_cifra_comparativo", "") or "Comparativo"
        ).strip()
        or "Comparativo",
        "destino_codigo_seccion": cstr(row.destino_codigo_seccion or "").strip(),
        "destino_codigo_tabla": cstr(row.destino_codigo_tabla or "").strip(),
        "destino_codigo_fila": cstr(row.destino_codigo_fila or "").strip(),
        "destino_codigo_columna": cstr(row.destino_codigo_columna or "").strip(),
        "destino_periodo_celda": cstr(getattr(row, "destino_periodo_celda", "") or "Actual").strip() or "Actual",
        "observaciones": cstr(getattr(row, "observaciones", "") or "").strip(),
        "target_label": target_label,
        "modified": cstr(getattr(row, "modified", "") or "").strip(),
    }


def _serialize_rule_detail(rule_doc):
    data = _serialize_rule(rule_doc)
    data["cuentas"] = [
        {
            "cuenta": cstr(getattr(row, "cuenta", "") or "").strip(),
            "campo_balanza": cstr(getattr(row, "campo_balanza", "codigo_cuenta") or "codigo_cuenta").strip(),
            "operacion": cstr(getattr(row, "operacion", "+") or "+").strip(),
            "porcentaje": flt(getattr(row, "porcentaje", 100) or 100),
            "centro_costo": cstr(getattr(row, "centro_costo", "") or "").strip(),
            "comentario": cstr(getattr(row, "comentario", "") or "").strip(),
        }
        for row in (rule_doc.cuentas or [])
    ]
    return data


def _get_note_rule_rows(note_doc):
    rows = frappe.get_all(
        "Regla Mapeo Contable EEFF",
        filters={
            "paquete_eeff": note_doc.paquete_eeff,
            "destino_tipo": ["in", list(NOTE_RULE_TARGET_TYPES)],
            "nota_eeff": note_doc.name,
        },
        fields=[
            "name",
            "activo",
            "orden",
            "fuente_tipo",
            "destino_tipo",
            "destino_codigo_cifra",
            "usar_periodos_especiales_cifra",
            "destino_periodo_cifra_actual",
            "destino_periodo_cifra_comparativo",
            "destino_codigo_seccion",
            "destino_codigo_tabla",
            "destino_codigo_fila",
            "destino_codigo_columna",
            "destino_periodo_celda",
            "modified",
        ],
        order_by="activo desc, orden asc, modified desc",
        limit_page_length=1000,
    )
    serialized = [_serialize_rule(row) for row in rows]
    figure_rules = {}
    cell_rules = {}
    for row in serialized:
        if row["destino_tipo"] == "Cifra Nota":
            figure_rules.setdefault(_normalize_code(row["destino_codigo_cifra"]), []).append(row)
            continue
        key = (
            _normalize_code(row["destino_codigo_seccion"]),
            _normalize_code(row["destino_codigo_tabla"]),
            _normalize_code(row["destino_codigo_fila"]),
            _normalize_code(row["destino_codigo_columna"]),
        )
        cell_rules.setdefault(key, []).append(row)
    return serialized, figure_rules, cell_rules


def _serialize_figures(note_doc, figure_rules):
    output = []
    for row in note_doc.cifras_nota or []:
        code = _normalize_code(getattr(row, "codigo_cifra", ""))
        rules = figure_rules.get(code, [])
        output.append(
            {
                "codigo_cifra": cstr(getattr(row, "codigo_cifra", "") or "").strip(),
                "concepto": cstr(getattr(row, "concepto", "") or "").strip(),
                "formato_numero": cstr(getattr(row, "formato_numero", "") or "").strip(),
                "monto_actual": None if getattr(row, "monto_actual", None) in ("", None) else flt(getattr(row, "monto_actual", 0) or 0),
                "monto_comparativo": None
                if getattr(row, "monto_comparativo", None) in ("", None)
                else flt(getattr(row, "monto_comparativo", 0) or 0),
                "display_actual": note_doc.format_figure_value(row, "monto_actual"),
                "display_comparativo": note_doc.format_figure_value(row, "monto_comparativo"),
                "origen_dato": cstr(getattr(row, "origen_dato", "") or "").strip() or "Manual",
                "es_manual": cint(getattr(row, "es_manual", 0) or 0),
                "es_titulo": cint(getattr(row, "es_titulo", 0) or 0),
                "es_linea_blanco": cint(getattr(row, "es_linea_blanco", 0) or 0),
                "calculo_automatico": cint(getattr(row, "calculo_automatico", 0) or 0),
                "formula_cifras": cstr(getattr(row, "formula_cifras", "") or "").strip(),
                "rules_count": len(rules),
                "rules": rules,
            }
        )
    return output


def _build_section_tables(section_doc, cell_rules):
    rendered_tables = build_complex_section_tables(section_doc)
    cell_docs = {}
    for cell in section_doc.celdas_tabulares or []:
        key = (
            normalize_table_code(getattr(cell, "codigo_tabla", None)),
            normalize_row_code(getattr(cell, "codigo_fila", None)),
            normalize_column_code(getattr(cell, "codigo_columna", None)),
        )
        cell_docs[key] = cell

    tables = []
    section_code = _normalize_code(getattr(section_doc, "codigo_seccion", ""))
    for table in rendered_tables:
        table_code = _normalize_code(table.get("codigo_tabla"))
        rows = []
        for row in table.get("filas") or []:
            row_code = _normalize_code(row.get("codigo_fila"))
            cells = []
            for cell in row.get("celdas") or []:
                column_code = _normalize_code(cell.get("codigo_columna"))
                cell_doc = cell_docs.get((table_code, row_code, column_code))
                rules = cell_rules.get((section_code, table_code, row_code, column_code), [])
                cells.append(
                    {
                        "codigo_columna": column_code,
                        "etiqueta_columna": cstr(cell.get("codigo_columna") or "").strip(),
                        "display_value": cstr(cell.get("texto") or "").strip() or "-",
                        "valor_numero": None
                        if not cell_doc or getattr(cell_doc, "valor_numero", None) in ("", None)
                        else flt(getattr(cell_doc, "valor_numero", 0) or 0),
                        "valor_texto": cstr(getattr(cell_doc, "valor_texto", "") or "").strip() if cell_doc else "",
                        "formato_numero": cstr(cell.get("formato_numero") or "").strip(),
                        "origen_dato": cstr(getattr(cell_doc, "origen_dato", "") or "").strip() if cell_doc else "",
                        "ultima_regla_mapeo": cstr(getattr(cell_doc, "ultima_regla_mapeo", "") or "").strip() if cell_doc else "",
                        "es_manual": cint(getattr(cell_doc, "es_manual", 0) or 0) if cell_doc else 0,
                        "rules_count": len(rules),
                        "rules": rules,
                    }
                )
            rows.append(
                {
                    "codigo_fila": cstr(row.get("codigo_fila") or "").strip(),
                    "descripcion": cstr(row.get("descripcion") or row.get("texto") or "").strip(),
                    "tipo_fila": cstr(row.get("tipo_fila") or "Detalle").strip() or "Detalle",
                    "celdas": cells,
                }
            )
        tables.append(
            {
                "codigo_tabla": cstr(table.get("codigo_tabla") or "").strip(),
                "columnas": [
                    {
                        "codigo_columna": cstr(col.get("codigo_columna") or "").strip(),
                        "etiqueta": cstr(col.get("etiqueta") or col.get("codigo_columna") or "").strip(),
                        "tipo_dato": cstr(col.get("tipo_dato") or "Numero").strip() or "Numero",
                    }
                    for col in (table.get("columnas") or [])
                ],
                "filas": rows,
            }
        )
    return tables


def _serialize_sections(note_doc, cell_rules):
    section_names = frappe.get_all(
        "Seccion Nota EEFF",
        filters={"nota_eeff": note_doc.name},
        pluck="name",
        order_by="orden asc, modified asc",
        limit_page_length=300,
    )
    output = []
    for section_name in section_names:
        section_doc = frappe.get_doc("Seccion Nota EEFF", section_name)
        tables = _build_section_tables(section_doc, cell_rules)
        output.append(
            {
                "name": section_doc.name,
                "codigo_seccion": cstr(section_doc.codigo_seccion or "").strip(),
                "titulo_seccion": cstr(section_doc.titulo_seccion or "").strip(),
                "tipo_seccion": cstr(section_doc.tipo_seccion or "Narrativa").strip() or "Narrativa",
                "orden": cint(section_doc.orden or 0),
                "total_columnas": cint(section_doc.total_columnas or 0),
                "total_filas": cint(section_doc.total_filas or 0),
                "total_celdas": cint(section_doc.total_celdas or 0),
                "tables": tables,
            }
        )
    return output


def _build_package_summary(package_name):
    package_name = _clean(package_name)
    if not package_name or not frappe.db.exists("Paquete EEFF", package_name):
        return None

    package_values = frappe.db.get_value(
        "Paquete EEFF",
        package_name,
        ["cliente", "anio", "mes", "periodo_nombre", "estado_preparacion"],
        as_dict=True,
    ) or {}
    notes = _serialize_note_rows(package_name)
    return {
        "package_name": package_name,
        "cliente": package_values.get("cliente"),
        "cliente_label": get_customer_display(package_values.get("cliente")),
        "anio": cint(package_values.get("anio") or 0),
        "mes": package_values.get("mes"),
        "periodo_nombre": package_values.get("periodo_nombre"),
        "estado_preparacion": package_values.get("estado_preparacion") or "Borrador",
        "total_notas": len(notes),
        "total_notas_complejas": sum(1 for row in notes if row.get("estructura_nota") == "Compleja"),
        "reglas_notas_activas": frappe.db.count(
            "Regla Mapeo Contable EEFF",
            {
                "paquete_eeff": package_name,
                "activo": 1,
                "destino_tipo": ["in", list(NOTE_RULE_TARGET_TYPES)],
            },
        ),
    }


def _serialize_note_mapping(note_doc):
    all_rules, figure_rules, cell_rules = _get_note_rule_rows(note_doc)
    figures = _serialize_figures(note_doc, figure_rules)
    sections = _serialize_sections(note_doc, cell_rules)
    active_rules = [row for row in all_rules if cint(row.get("activo") or 0)]
    return {
        "doc": {
            "name": note_doc.name,
            "paquete_eeff": note_doc.paquete_eeff,
            "numero_nota": note_doc.numero_nota,
            "sub_nota": note_doc.sub_nota,
            "identificador_nota": build_note_identifier(note_doc.numero_nota, note_doc.sub_nota),
            "titulo": note_doc.titulo,
            "estructura_nota": cstr(note_doc.estructura_nota or "Simple").strip() or "Simple",
            "estado_aprobacion": cstr(note_doc.estado_aprobacion or "Borrador").strip() or "Borrador",
            "total_cifras": cint(note_doc.total_cifras or 0),
            "total_secciones_complejas": cint(note_doc.total_secciones_complejas or 0),
        },
        "figures": figures,
        "sections": sections,
        "rules": all_rules,
        "stats": {
            "total_reglas": len(all_rules),
            "reglas_activas": len(active_rules),
            "cifras_con_regla": sum(1 for row in figures if cint(row.get("rules_count") or 0)),
            "celdas_con_regla": sum(
                1
                for section in sections
                for table in (section.get("tables") or [])
                for row in (table.get("filas") or [])
                for cell in (row.get("celdas") or [])
                if cint(cell.get("rules_count") or 0)
            ),
        },
    }


def _sanitize_rule_accounts(rows):
    output = []
    for row in rows or []:
        values = row.as_dict(no_nulls=False) if hasattr(row, "as_dict") else dict(row or {})
        cuenta = cstr(values.get("cuenta") or "").strip()
        if not cuenta:
            continue
        campo_balanza = cstr(values.get("campo_balanza") or "codigo_cuenta").strip()
        if campo_balanza not in BALANCE_FIELDS:
            campo_balanza = "codigo_cuenta"
        operacion = cstr(values.get("operacion") or "+").strip()
        if operacion not in ("+", "-"):
            operacion = "+"
        porcentaje = flt(values.get("porcentaje") or 100)
        output.append(
            {
                "cuenta": cuenta,
                "campo_balanza": campo_balanza,
                "operacion": operacion,
                "porcentaje": porcentaje,
                "centro_costo": cstr(values.get("centro_costo") or "").strip(),
                "comentario": cstr(values.get("comentario") or "").strip(),
            }
        )
    return output


def _apply_rule_payload(rule_doc, note_doc, payload):
    payload = payload or {}
    destino_tipo = cstr(payload.get("destino_tipo") or "").strip()
    if destino_tipo not in NOTE_RULE_TARGET_TYPES:
        frappe.throw(_("El destino de la regla no es valido."), title=_("Destino Invalido"))

    rule_doc.paquete_eeff = note_doc.paquete_eeff
    rule_doc.nota_eeff = note_doc.name
    rule_doc.destino_numero_nota = build_note_identifier(note_doc.numero_nota, note_doc.sub_nota)
    rule_doc.activo = cint(payload.get("activo", 1) or 0)
    rule_doc.orden = cint(payload.get("orden") or 0)
    rule_doc.fuente_tipo = cstr(payload.get("fuente_tipo") or "Balanza").strip() or "Balanza"
    rule_doc.observaciones = cstr(payload.get("observaciones") or "").strip()
    rule_doc.destino_tipo = destino_tipo

    rule_doc.estado_financiero_eeff = ""
    rule_doc.destino_codigo_estado = ""
    rule_doc.destino_codigo_linea = ""
    rule_doc.destino_codigo_cifra = ""
    rule_doc.usar_periodos_especiales_cifra = 0
    rule_doc.destino_periodo_cifra_actual = "Actual"
    rule_doc.destino_periodo_cifra_comparativo = "Comparativo"
    rule_doc.seccion_nota_eeff = ""
    rule_doc.destino_codigo_seccion = ""
    rule_doc.destino_codigo_tabla = ""
    rule_doc.destino_codigo_fila = ""
    rule_doc.destino_codigo_columna = ""
    rule_doc.destino_periodo_celda = "Actual"

    if destino_tipo == "Cifra Nota":
        rule_doc.destino_codigo_cifra = _normalize_code(payload.get("destino_codigo_cifra"))
        rule_doc.usar_periodos_especiales_cifra = cint(payload.get("usar_periodos_especiales_cifra") or 0)
        period_actual = cstr(payload.get("destino_periodo_cifra_actual") or "Actual").strip()
        rule_doc.destino_periodo_cifra_actual = period_actual if period_actual in FIGURE_VALUE_PERIODS else "Actual"
        period_comparativo = cstr(payload.get("destino_periodo_cifra_comparativo") or "Comparativo").strip()
        rule_doc.destino_periodo_cifra_comparativo = (
            period_comparativo if period_comparativo in FIGURE_VALUE_PERIODS else "Comparativo"
        )
    else:
        rule_doc.seccion_nota_eeff = cstr(payload.get("seccion_nota_eeff") or "").strip()
        rule_doc.destino_codigo_seccion = _normalize_code(payload.get("destino_codigo_seccion"))
        rule_doc.destino_codigo_tabla = _normalize_code(payload.get("destino_codigo_tabla"))
        rule_doc.destino_codigo_fila = _normalize_code(payload.get("destino_codigo_fila"))
        rule_doc.destino_codigo_columna = _normalize_code(payload.get("destino_codigo_columna"))
        period = cstr(payload.get("destino_periodo_celda") or "Actual").strip()
        rule_doc.destino_periodo_celda = period if period in SECTION_CELL_PERIODS else "Actual"

    rule_doc.set("cuentas", [])
    cuentas = _sanitize_rule_accounts(payload.get("cuentas") or [])
    for row in cuentas:
        rule_doc.append("cuentas", row)

    return rule_doc


@frappe.whitelist()
def get_mapping_helper_bootstrap(cliente=None, anio=None, mes=None, package_name=None, note_name=None):
    _ensure_page_access()

    note_doc = None
    package_name = _clean(package_name)
    note_name = _clean(note_name)

    if note_name:
        if not frappe.db.exists("Nota EEFF", note_name):
            frappe.throw(_("La nota indicada no existe."), title=_("Nota Invalida"))
        note_doc = frappe.get_doc("Nota EEFF", note_name)
        package_name = note_doc.paquete_eeff
        package_values = frappe.db.get_value(
            "Paquete EEFF",
            package_name,
            ["cliente", "anio", "mes"],
            as_dict=True,
        ) or {}
        cliente = package_values.get("cliente") or cliente
        anio = package_values.get("anio") or anio
        mes = package_values.get("mes") or mes
    elif package_name and frappe.db.exists("Paquete EEFF", package_name):
        package_values = frappe.db.get_value(
            "Paquete EEFF",
            package_name,
            ["cliente", "anio", "mes"],
            as_dict=True,
        ) or {}
        cliente = package_values.get("cliente") or cliente
        anio = package_values.get("anio") or anio
        mes = package_values.get("mes") or mes

    notes = _serialize_note_rows(package_name) if package_name else []
    if not note_doc and notes:
        note_doc = frappe.get_doc("Nota EEFF", notes[0]["name"])
        note_name = note_doc.name

    return {
        "cliente": _clean(cliente),
        "anio": cint(anio or 0),
        "mes": _clean(mes),
        "package_name": package_name,
        "note_name": note_name or (note_doc.name if note_doc else ""),
        "clients": _get_clients(),
        "packages": _get_packages(cliente=cliente, anio=anio, mes=mes),
        "meses": list(MESES),
        "notes": notes,
        "summary": _build_package_summary(package_name),
        "note": _serialize_note_mapping(note_doc) if note_doc else None,
    }


@frappe.whitelist()
def get_mapping_rule_detail(rule_name):
    _ensure_page_access()

    rule_name = _clean(rule_name)
    if not rule_name or not frappe.db.exists("Regla Mapeo Contable EEFF", rule_name):
        frappe.throw(_("La regla indicada no existe."), title=_("Regla Invalida"))

    rule_doc = frappe.get_doc("Regla Mapeo Contable EEFF", rule_name)
    return _serialize_rule_detail(rule_doc)


@frappe.whitelist()
def save_mapping_rule_from_helper(note_name, rule_payload):
    _ensure_page_access(write=True)

    note_name = _clean(note_name)
    if not note_name or not frappe.db.exists("Nota EEFF", note_name):
        frappe.throw(_("La nota indicada no existe."), title=_("Nota Invalida"))

    payload = frappe.parse_json(rule_payload) if isinstance(rule_payload, str) else (rule_payload or {})
    note_doc = frappe.get_doc("Nota EEFF", note_name)
    rule_name = _clean(payload.get("name"))

    if rule_name:
        if not frappe.db.exists("Regla Mapeo Contable EEFF", rule_name):
            frappe.throw(_("La regla indicada no existe."), title=_("Regla Invalida"))
        rule_doc = frappe.get_doc("Regla Mapeo Contable EEFF", rule_name)
    else:
        rule_doc = frappe.get_doc({"doctype": "Regla Mapeo Contable EEFF"})

    _apply_rule_payload(rule_doc, note_doc, payload)

    if rule_name:
        rule_doc.save(ignore_permissions=True)
    else:
        rule_doc.insert(ignore_permissions=True)

    return {
        "rule": _serialize_rule_detail(rule_doc),
        "note_name": note_doc.name,
    }
