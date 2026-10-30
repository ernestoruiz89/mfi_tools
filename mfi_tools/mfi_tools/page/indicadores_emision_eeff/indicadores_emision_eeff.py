import re
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.services.formula_engine import has_data_functions
from mfi_tools.mfi_tools.services.emission_validation import (
    data_formula_issues, has_figure_content, has_rich_text,
    section_has_content, tabular_formula_issues,
)
from mfi_tools.mfi_tools.utils.nota_eeff import build_note_identifier, get_package_note_rows

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
FORMULA_ALLOWED_RE = re.compile(r"^[A-Z0-9_+\-*/().,;\s]+$")
FORMULA_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
FORMULA_MULTICOL_PREFIXES = {
    "ACT",
    "COMP",
    "BASE",
    "SELF",
    "BASE_ACT",
    "BASE_COMP",
    "MONTO_ACTUAL",
    "MONTO_COMPARATIVO",
    "MONTO_BASE_ACTUAL",
    "MONTO_BASE_COMPARATIVO",
}


def _clean(value):
    return cstr(value or "").strip()


def _evaluation_time():
    return datetime.now(timezone.utc).isoformat()


def _get_entity_display(name):
    name = _clean(name)
    if not name:
        return ""
    return _get_entity_display_map([name]).get(name, name)


def _get_entity_display_map(names):
    names = sorted({_clean(name) for name in names if _clean(name)})
    mapping = {name: name for name in names}
    for doctype, label in (("Company", "company_name"),):
        if names and frappe.has_permission(doctype, "read"):
            for row in frappe.get_list(doctype, filters={"name": ["in", names]},
                                       fields=["name", label], limit_page_length=0):
                mapping[row.name] = row.get(label) or row.name
    return mapping


def _build_filters(cliente=None, anio=None, mes=None):
    filters = {}
    if _clean(cliente):
        meta = frappe.get_meta("Paquete EEFF")
        field = "company" if meta.has_field("company") else "cliente"
        filters[field] = _clean(cliente)
    if cint(anio or 0):
        filters["anio"] = cint(anio)
    if _clean(mes):
        filters["mes"] = _clean(mes)
    return filters


def _get_clients():
    meta = frappe.get_meta("Paquete EEFF")
    field = "company" if meta.has_field("company") else ("cliente" if meta.has_field("cliente") else None)
    if not field:
        return []
    rows = frappe.get_list(
        "Paquete EEFF",
        fields=[field],
        filters={field: ["is", "set"]},
        distinct=True,
        order_by=f"{field} asc",
        limit_page_length=0,
    )
    values = sorted({_clean(row.get(field)) for row in rows if _clean(row.get(field))})
    if not values and frappe.has_permission("Company", "read"):
        for row in frappe.get_list("Company", fields=["name"], limit_page_length=0):
            values.append(row.name)
        values = sorted(set(values))
    display_map = _get_entity_display_map(values)
    return [{"value": row, "label": display_map.get(row, row)} for row in values]


def _get_packages(cliente=None, anio=None, mes=None):
    meta = frappe.get_meta("Paquete EEFF")
    entity_field = "company" if meta.has_field("company") else "cliente"
    rows = frappe.get_list(
        "Paquete EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes),
        fields=[
            "name",
            entity_field,
            "anio",
            "mes",
            "periodo_nombre",
            "estado_preparacion",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=0,
    )
    customer_labels = _get_entity_display_map([row.get(entity_field) for row in rows])
    return [
        {
            "value": row.name,
            "label": f"{row.name} | {customer_labels.get(row.get(entity_field), row.get(entity_field)) or '-'} | {row.mes or '-'} {row.anio or '-'} | {row.estado_preparacion or 'Borrador'}",
            "cliente": row.get(entity_field),
            "cliente_label": customer_labels.get(row.get(entity_field), row.get(entity_field)),
            "anio": row.anio,
            "mes": row.mes,
        }
        for row in rows
    ]


def _extract_formula_refs(expression, mode="Vertical"):
    expr = _clean(expression).upper()
    if not expr:
        return [], []

    if has_data_functions(expr):
        return [], data_formula_issues(expr)

    issues = []
    if not FORMULA_ALLOWED_RE.match(expr):
        issues.append(_("Contiene caracteres no permitidos."))

    refs = []
    parsed_tokens = [token for token in re.split(r"[\n,;]+", expr) if _clean(token)]
    multicol = _clean(mode) == "Multicolumna"

    for token in parsed_tokens:
        raw = _clean(token).upper()
        if not raw:
            continue
        if raw[0] in "+-":
            raw = _clean(raw[1:]).upper()
        if not raw:
            continue

        if multicol:
            prefix = "ACT"
            ref = raw
            if "." in raw:
                prefix, ref = raw.split(".", 1)
                prefix = _clean(prefix).upper()
                ref = _clean(ref).upper()
            if prefix not in FORMULA_MULTICOL_PREFIXES:
                issues.append(_("Prefijo de columna invalido: {0}.").format(prefix or "-"))
                continue
            if not FORMULA_TOKEN_RE.fullmatch(ref or ""):
                issues.append(_("Referencia invalida: {0}.").format(ref or "-"))
                continue
            refs.append(ref)
            continue

        if "." in raw:
            issues.append(_("Referencia invalida para modo Vertical: {0}.").format(raw))
            continue
        if not FORMULA_TOKEN_RE.fullmatch(raw or ""):
            issues.append(_("Referencia invalida: {0}.").format(raw or "-"))
            continue
        refs.append(raw)

    if not refs:
        issues.append(_("No se detectaron codigos referenciados."))

    return refs, issues


def _lineas_huerfanas(estado_doc):
    issues = []
    lineas = sorted(
        [row for row in estado_doc.lineas or []
         if not cint(row.get("no_imprimir")) and not cint(row.get("es_linea_blanco"))],
        key=lambda row: (cint(row.get("orden") or row.idx or 0), cint(row.idx or 0)),
    )
    ancestors = []

    for row in lineas:
        nivel = max(cint(row.nivel or 1), 1)
        while ancestors and ancestors[-1] >= nivel:
            ancestors.pop()
        parent_ok = bool(ancestors and ancestors[-1] == nivel - 1)
        ancestors.append(nivel)
        if nivel <= 1:
            continue

        if not parent_ok:
            issues.append(
                {
                    "estado": estado_doc.name,
                    "codigo": _clean(row.codigo_linea) or "-",
                    "descripcion": _clean(row.descripcion) or "-",
                    "nivel": nivel,
                    "motivo": _("No tiene una linea padre valida (nivel anterior)."),
                }
            )

    return issues


def _formula_issues_for_rows(rows, code_field, formula_field, scope, docname, mode_field=None):
    issues = []
    row_map = {_clean(getattr(row, code_field, "")).upper(): row for row in rows if _clean(getattr(row, code_field, ""))}
    graph = {}

    for row in rows:
        code = _clean(getattr(row, code_field, "")).upper()
        formula = _clean(getattr(row, formula_field, ""))
        if (not code or not formula or row.get("origen_dato") != "Formula"
                or cint(row.get("es_titulo")) or cint(row.get("es_linea_blanco"))
                or row.get("formato_numero") == "Texto" or row.get("formato_presentacion") == "Texto"):
            continue

        mode = "Vertical"
        if mode_field:
            mode = _clean(getattr(row, mode_field, "")) or "Vertical"
        refs, parse_issues = _extract_formula_refs(formula, mode=mode)
        for msg in parse_issues:
            issues.append(
                {
                    "scope": scope,
                    "documento": docname,
                    "codigo": code,
                    "formula": formula,
                    "referencia": "-",
                    "motivo": msg,
                }
            )

        graph[code] = []
        for ref in refs:
            if ref not in row_map:
                issues.append(
                    {
                        "scope": scope,
                        "documento": docname,
                        "codigo": code,
                        "formula": formula,
                        "referencia": ref,
                        "motivo": _("Referencia inexistente."),
                    }
                )
                continue
            graph[code].append(ref)

    # Iterative DFS also handles long formula chains without Python recursion limits.
    visited = set()
    signatures = set()
    for root in graph:
        if root in visited:
            continue
        stack = [root]
        positions = {root: 0}
        pending = [(root, iter(graph.get(root, [])))]
        visited.add(root)
        while pending:
            node, edges = pending[-1]
            ref = next(edges, None)
            if ref is None:
                pending.pop()
                positions.pop(node, None)
                stack.pop()
            elif ref in positions:
                cycle = stack[positions[ref]:] + [ref]
                signature = frozenset(cycle)
                if signature not in signatures:
                    signatures.add(signature)
                    issues.append({
                        "scope": scope, "documento": docname, "codigo": node,
                        "formula": _clean(getattr(row_map.get(node), formula_field, "")),
                        "referencia": " -> ".join(cycle),
                        "motivo": _("Referencia circular detectada."),
                    })
            elif ref not in visited:
                visited.add(ref)
                positions[ref] = len(stack)
                stack.append(ref)
                pending.append((ref, iter(graph.get(ref, []))))

    return issues


def _has_rich_text(value):
    return has_rich_text(value)


def _complex_note_has_content(nota, sections=None):
    if _clean(nota.get("estructura_nota") or "Simple") != "Compleja":
        return False
    if sections is None:
        names = frappe.get_all("Seccion Nota EEFF", filters={"nota_eeff": nota.name}, pluck="name")
        sections = [frappe.get_doc("Seccion Nota EEFF", name) for name in names]
        for section in sections:
            section.check_permission("read")
    return any(section_has_content(section) for section in sections)


def _notas_faltantes(notas, sections_by_note=None):
    if not notas:
        return [{"tipo": "conjunto", "detalle": _("El paquete no tiene notas registradas.")}]
    issues = []
    numbers = sorted({cint(nota.numero_nota) for nota in notas if cint(nota.numero_nota) > 0})
    previous = 0
    for number in numbers:
        first, last = previous + 1, number - 1
        # A mistyped note number must not allocate an enormous range or response.
        if last - first >= 20:
            issues.append({"tipo": "secuencia", "detalle": _("Faltan las notas {0} a {1}.").format(first, last)})
        else:
            for missing in range(first, last + 1):
                issues.append({"tipo": "secuencia", "detalle": _("Falta la nota numero {0}.").format(missing)})
        previous = number
    for nota in notas:
        visible_cifras = [row for row in nota.cifras_nota or [] if has_figure_content(row)]
        sections = None if sections_by_note is None else sections_by_note.get(nota.name, [])
        if (not _has_rich_text(nota.contenido_narrativo) and not _has_rich_text(nota.get("observaciones")) and not visible_cifras
                and not _complex_note_has_content(nota, sections)):
            issues.append({
                "tipo": "contenido",
                "detalle": _("Nota {0} ({1}) sin contenido.").format(
                    build_note_identifier(nota.numero_nota, nota.get("sub_nota")) or "-", nota.name),
            })
    return issues


def _require_access():
    frappe.only_for("System Manager")
    if not frappe.has_permission("Paquete EEFF", "read"):
        frappe.throw(_("No tienes permiso para consultar paquetes EEFF."), frappe.PermissionError)


def _state_orphans(estado):
    if _clean(estado.get("estructura_estado")) != "Compleja":
        return _lineas_huerfanas(estado)
    tables = {}
    for row in estado.filas_tabulares or []:
        tables.setdefault(row.codigo_tabla, []).append(frappe._dict(
            codigo_linea=row.codigo_fila, descripcion=row.descripcion, nivel=row.nivel,
            orden=row.get("orden"), idx=row.idx,
        ))
    return [issue for table, rows in tables.items()
            for issue in _lineas_huerfanas(frappe._dict(name=f"{estado.name} / {table}", lineas=rows))]


def _missing_note_refs(estados, notas):
    numbers = {cint(n.numero_nota) for n in notas}
    identifiers = {(cint(n.numero_nota), _clean(n.get("sub_nota")).strip("()").upper()) for n in notas}
    issues = []
    for estado in estados:
        rows = estado.filas_tabulares if estado.get("estructura_estado") == "Compleja" else estado.lineas
        for row in rows or []:
            if cint(row.get("no_imprimir")) or cint(row.get("es_linea_blanco")):
                continue
            for number, sub in re.findall(r"(\d+)(?:\s*\(([A-Za-z0-9]+)\))?", _clean(row.get("nota"))):
                exists = (cint(number), sub.upper()) in identifiers if sub else cint(number) in numbers
                if not exists:
                    issues.append({"tipo": "referencia", "detalle": _("Estado {0}, linea {1}: la nota {2} referenciada no existe.").format(
                        estado.name, row.get("codigo_linea") or row.get("codigo_fila") or "-",
                        build_note_identifier(number, sub))})
    return issues


def _compute_indicators(paquete_name):
    _require_access()
    paquete_name = _clean(paquete_name)
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))

    package = frappe.get_doc("Paquete EEFF", paquete_name)
    package.check_permission("read")
    estados_meta = frappe.get_all(
        "Estado Financiero EEFF",
        filters={"paquete_eeff": package.name},
        fields=["name"],
        order_by="orden_presentacion asc, creation asc",
        limit_page_length=0,
    )
    notas_meta = get_package_note_rows(package.name, fields=[], limit_page_length=0)

    estados = [frappe.get_doc("Estado Financiero EEFF", row.name) for row in estados_meta]
    notas = [frappe.get_doc("Nota EEFF", row.name) for row in notas_meta]
    for doc in estados + notas:
        doc.check_permission("read")
    sections_by_note = {}
    complex_note_names = [n.name for n in notas if n.get("estructura_nota") == "Compleja"]
    if complex_note_names:
        for row in frappe.get_all("Seccion Nota EEFF", filters={"nota_eeff": ["in", complex_note_names]},
                                  fields=["name", "nota_eeff"]):
            section = frappe.get_doc("Seccion Nota EEFF", row.name)
            section.check_permission("read")
            sections_by_note.setdefault(row.nota_eeff, []).append(section)
    structure_issues = []
    if not estados:
        structure_issues.append({"status": "error", "detalle": _("El paquete no tiene estados financieros.")})
    for estado in estados:
        rows = estado.filas_tabulares if estado.get("estructura_estado") == "Compleja" else estado.lineas
        if not any(not cint(row.get("no_imprimir")) and not cint(row.get("es_linea_blanco"))
                   and not cint(row.get("es_titulo")) and row.get("tipo_fila") != "Titulo" for row in rows or []):
            structure_issues.append({"status": "error", "detalle": _("Estado {0} sin filas de datos imprimibles.").format(estado.name)})

    # Indicador 1: cuadre automatico (balanza)
    cuadre = {
        "status": "warning",
        "title": _("Cuadre Automatico"),
        "value": _("Sin balanza"),
        "detail": _("El paquete no tiene balanza vinculada."),
        "difference": 0.0,
    }
    if package.balanza_comprobacion_eeff and frappe.db.exists("Balanza Comprobacion EEFF", package.balanza_comprobacion_eeff):
        balanza = frappe.get_doc("Balanza Comprobacion EEFF", package.balanza_comprobacion_eeff)
        balanza.check_permission("read")
        total_debe = sum(flt(row.debe_saldo) for row in balanza.lineas or [])
        total_haber = sum(flt(row.haber_saldo) for row in balanza.lineas or [])
        diff = total_debe - total_haber
        compatible = all(_clean(package.get(field)) == _clean(balanza.get(field))
                         for field in ("company", "cliente", "anio", "mes") if package.get(field))
        is_balanced = bool(balanza.lineas) and compatible and abs(diff) < 0.0001
        cuadre = {
            "status": "ok" if is_balanced else "error",
            "title": _("Cuadre Automatico"),
            "value": _("Cuadra") if is_balanced else _("No cuadra"),
            "detail": _("Debe Saldo: {0} | Haber Saldo: {1} | Diferencia: {2}").format(
                f"{total_debe:,.2f}",
                f"{total_haber:,.2f}",
                f"{diff:,.2f}",
            ),
            "difference": diff,
        }
        if not balanza.lineas:
            cuadre.update(status="warning", value=_("Balanza vacia"), detail=_("La balanza no tiene lineas para evaluar."))
        if not compatible:
            cuadre.update(status="error", value=_("Balanza incompatible"), detail=_("La entidad o el periodo de la balanza no coincide con el paquete."))
        if abs(flt(balanza.total_debe) - total_debe) >= 0.0001 or abs(flt(balanza.total_haber) - total_haber) >= 0.0001:
            structure_issues.append({"status": "warning", "detalle": _("Los totales guardados de la balanza difieren de sus lineas; el cuadre se recalculo sin guardar cambios.")})
    elif package.balanza_comprobacion_eeff:
        cuadre.update(status="error", value=_("Balanza inexistente"), detail=_("La balanza vinculada ya no existe."))

    # Indicador 2: lineas huerfanas
    orphan_issues = []
    for estado in estados:
        orphan_issues.extend(_state_orphans(estado))

    lineas_huerfanas = {
        "status": "ok" if not orphan_issues else "warning",
        "title": _("Lineas Huerfanas"),
        "value": len(orphan_issues),
        "detail": _("Sin incidencias.") if not orphan_issues else _("Se detectaron lineas sin padre valido."),
    }

    # Indicador 3: formulas rotas (estados + notas)
    formula_issues = []
    for estado in estados:
        if estado.get("estructura_estado") == "Compleja":
            formula_issues.extend(tabular_formula_issues(estado, "Estado"))
            continue
        formula_issues.extend(
            _formula_issues_for_rows(
                rows=list(estado.lineas or []),
                code_field="codigo_linea",
                formula_field="formula_lineas",
                scope="Estado",
                docname=estado.name,
                mode_field="modo_formula",
            )
        )
    for nota in notas:
        formula_issues.extend(
            _formula_issues_for_rows(
                rows=list(nota.cifras_nota or []),
                code_field="codigo_cifra",
                formula_field="formula_cifras",
                scope="Nota",
                docname=nota.name,
            )
        )
        if nota.get("estructura_nota") == "Compleja":
            for section in sections_by_note.get(nota.name, []):
                formula_issues.extend(tabular_formula_issues(section, "Seccion de nota"))

    formulas_rotas = {
        "status": "ok" if not formula_issues else "error",
        "title": _("Formulas Rotas"),
        "value": len(formula_issues),
        "detail": _("Sin incidencias.") if not formula_issues else _("Hay referencias invalidas o circulares."),
    }

    # Indicador 4: notas faltantes
    note_issues = _notas_faltantes(notas, sections_by_note)
    note_issues.extend(_missing_note_refs(estados, notas))
    notas_faltantes = {
        "status": "ok" if not note_issues else "warning",
        "title": _("Notas Faltantes"),
        "value": len(note_issues),
        "detail": _("Sin incidencias.") if not note_issues else _("Hay notas faltantes o incompletas."),
    }

    score = 100
    if cuadre["status"] == "error":
        score -= 35
    elif cuadre["status"] == "warning":
        score -= 10
    score -= min(len(orphan_issues) * 2, 25)
    score -= min(len(formula_issues) * 3, 25)
    score -= min(len(note_issues) * 2, 15)
    score -= min(len(structure_issues) * 5, 20)
    score = max(score, 0)

    statuses = [cuadre["status"], lineas_huerfanas["status"], formulas_rotas["status"], notas_faltantes["status"]]
    statuses.extend(issue["status"] for issue in structure_issues)
    if "error" in statuses:
        score = min(score, 59)
    elif "warning" in statuses:
        score = min(score, 84)

    if score >= 85:
        health_level = _("Saludable")
        health_status = "ok"
    elif score >= 60:
        health_level = _("Atencion")
        health_status = "warning"
    else:
        health_level = _("Riesgo Alto")
        health_status = "error"

    return {
        "package": {
            "name": package.name,
            "cliente": package.get("company") or package.get("cliente"),
            "cliente_label": _get_entity_display(package.get("company") or package.get("cliente")),
            "periodo_nombre": package.periodo_nombre,
            "estado_preparacion": package.estado_preparacion,
            "total_estados": len(estados),
            "total_notas": len(notas),
        },
        "kpis": {
            "score": score,
            "health_level": health_level,
            "health_status": health_status,
            "cuadre": cuadre,
            "lineas_huerfanas": lineas_huerfanas,
            "formulas_rotas": formulas_rotas,
            "notas_faltantes": notas_faltantes,
            "estructura": {
                "status": "error" if any(i["status"] == "error" for i in structure_issues) else ("warning" if structure_issues else "ok"),
                "title": _("Integridad del Paquete"), "value": len(structure_issues),
                "detail": _("Hay estados vacios, faltantes o totales desactualizados.") if structure_issues else _("Sin incidencias."),
            },
        },
        "details": {
            "lineas_huerfanas": orphan_issues,
            "formulas_rotas": formula_issues,
            "notas_faltantes": note_issues,
            "estructura": structure_issues,
        },
        "meta": {
            "message": _("Estos indicadores son informativos y no bloquean la emision."),
            "evaluated_at": _evaluation_time(),
            "score_policy": _("Un error limita el score a 59; una advertencia lo limita a 84. No certifica la emision."),
        },
    }


def _bootstrap_response(cliente=None, anio=None, mes=None, paquete_name=None):
    _require_access()
    selected_package = _clean(paquete_name) or None
    indicators = None
    if selected_package:
        indicators = _compute_indicators(selected_package)
        package = frappe.get_doc("Paquete EEFF", selected_package)
        cliente = package.get("company") or package.get("cliente")
        anio, mes = package.anio, package.mes

    return {
        "cliente": _clean(cliente) or None,
        "anio": cint(anio or 0) or None,
        "mes": _clean(mes) or None,
        "paquete_name": selected_package,
        "clients": _get_clients(),
        "packages": _get_packages(cliente=cliente, anio=anio, mes=mes),
        "meses": list(MESES),
        "indicators": indicators,
    }


@frappe.whitelist()
def get_indicator_bootstrap(cliente=None, anio=None, mes=None, paquete_name=None):
    return _bootstrap_response(cliente=cliente, anio=anio, mes=mes, paquete_name=paquete_name)


@frappe.whitelist()
def run_emission_indicators(paquete_name):
    return _compute_indicators(paquete_name)
