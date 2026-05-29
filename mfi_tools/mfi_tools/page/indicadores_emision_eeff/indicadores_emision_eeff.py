import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.utils.customer import get_customer_display, get_customer_display_map
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
    "BASE_ACT",
    "BASE_COMP",
    "MONTO_ACTUAL",
    "MONTO_COMPARATIVO",
    "MONTO_BASE_ACTUAL",
    "MONTO_BASE_COMPARATIVO",
}


def _clean(value):
    return cstr(value or "").strip()


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
    values = sorted({_clean(row.cliente) for row in rows if _clean(row.cliente)})
    display_map = get_customer_display_map(values)
    return [{"value": row, "label": display_map.get(row, row)} for row in values]


def _get_packages(cliente=None, anio=None, mes=None):
    rows = frappe.get_all(
        "Paquete EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes),
        fields=[
            "name",
            "cliente",
            "anio",
            "mes",
            "periodo_nombre",
            "estado_preparacion",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=500,
    )
    customer_labels = get_customer_display_map([row.cliente for row in rows])
    return [
        {
            "value": row.name,
            "label": f"{row.name} | {customer_labels.get(row.cliente, row.cliente) or '-'} | {row.mes or '-'} {row.anio or '-'} | {row.estado_preparacion or 'Borrador'}",
            "cliente": row.cliente,
            "cliente_label": customer_labels.get(row.cliente, row.cliente),
            "anio": row.anio,
            "mes": row.mes,
        }
        for row in rows
    ]


def _extract_formula_refs(expression, mode="Vertical"):
    expr = _clean(expression).upper()
    if not expr:
        return [], []

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
    lineas = sorted(list(estado_doc.lineas or []), key=lambda row: (cint(row.orden or 0), cint(row.idx or 0)))

    for idx, row in enumerate(lineas):
        nivel = max(cint(row.nivel or 1), 1)
        if nivel <= 1:
            continue

        parent_ok = False
        for prev in reversed(lineas[:idx]):
            prev_level = max(cint(prev.nivel or 1), 1)
            if prev_level < nivel:
                parent_ok = prev_level == (nivel - 1)
                break

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
        if not code or not formula:
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

    cycle_signatures = set()
    visited = set()
    stack = []
    in_stack = set()

    def dfs(node):
        visited.add(node)
        stack.append(node)
        in_stack.add(node)

        for ref in graph.get(node, []):
            if ref not in visited:
                dfs(ref)
                continue
            if ref in in_stack:
                idx = stack.index(ref)
                cycle = tuple(stack[idx:] + [ref])
                signature = tuple(sorted(set(cycle)))
                if signature not in cycle_signatures:
                    cycle_signatures.add(signature)
                    issues.append(
                        {
                            "scope": scope,
                            "documento": docname,
                            "codigo": node,
                            "formula": _clean(getattr(row_map.get(node), formula_field, "")),
                            "referencia": " -> ".join(cycle),
                            "motivo": _("Referencia circular detectada."),
                        }
                    )

        stack.pop()
        in_stack.discard(node)

    for code in graph:
        if code not in visited:
            dfs(code)

    return issues


def _has_rich_text(value):
    text = re.sub(r"<[^>]+>", "", cstr(value or ""))
    return bool(_clean(text))


def _complex_note_has_content(nota):
    if cstr(getattr(nota, "estructura_nota", "Simple") or "Simple").strip() != "Compleja":
        return False

    section_names = frappe.get_all(
        "Seccion Nota EEFF",
        filters={"nota_eeff": nota.name},
        pluck="name",
        limit_page_length=300,
    )
    if not section_names:
        return False

    for section_name in section_names:
        section = frappe.get_doc("Seccion Nota EEFF", section_name)
        has_narrative = _has_rich_text(getattr(section, "contenido_narrativo", ""))
        has_cells = bool(getattr(section, "celdas_tabulares", None) or [])
        if has_narrative or has_cells:
            return True

    return False


def _notas_faltantes(notas):
    issues = []
    if not notas:
        issues.append({"tipo": "conjunto", "detalle": _("El paquete no tiene notas registradas.")})
        return issues

    numbers = []
    for nota in notas:
        raw = _clean(nota.numero_nota)
        match = re.search(r"\d+", raw)
        if match:
            numbers.append(int(match.group(0)))

    if numbers:
        missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
        for number in missing:
            issues.append({"tipo": "secuencia", "detalle": _("Falta la nota numero {0}.").format(number)})

    for nota in notas:
        visible_cifras = [row for row in (nota.cifras_nota or []) if not cint(getattr(row, "no_imprimir", 0))]
        has_narrative = _has_rich_text(nota.contenido_narrativo)
        has_complex_content = _complex_note_has_content(nota)
        if not has_narrative and not visible_cifras and not has_complex_content:
            issues.append(
                {
                    "tipo": "contenido",
                    "detalle": _("Nota {0} ({1}) sin contenido.").format(
                        build_note_identifier(nota.numero_nota, getattr(nota, "sub_nota", "")) or "-",
                        nota.name,
                    ),
                }
            )

    return issues


def _compute_indicators(paquete_name):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))

    package = frappe.get_doc("Paquete EEFF", paquete_name)
    estados_meta = frappe.get_all(
        "Estado Financiero EEFF",
        filters={"paquete_eeff": package.name},
        fields=["name"],
        order_by="orden_presentacion asc, creation asc",
        limit_page_length=200,
    )
    notas_meta = get_package_note_rows(package.name, fields=[], limit_page_length=300)

    estados = [frappe.get_doc("Estado Financiero EEFF", row.name) for row in estados_meta]
    notas = [frappe.get_doc("Nota EEFF", row.name) for row in notas_meta]

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
        diff = flt(balanza.total_debe or 0) - flt(balanza.total_haber or 0)
        is_balanced = cint(balanza.cuadra) and abs(diff) < 0.01
        cuadre = {
            "status": "ok" if is_balanced else "error",
            "title": _("Cuadre Automatico"),
            "value": _("Cuadra") if is_balanced else _("No cuadra"),
            "detail": _("Debe Saldo: {0} | Haber Saldo: {1} | Diferencia: {2}").format(
                f"{flt(balanza.total_debe or 0):,.2f}",
                f"{flt(balanza.total_haber or 0):,.2f}",
                f"{diff:,.2f}",
            ),
            "difference": diff,
        }

    # Indicador 2: lineas huerfanas
    orphan_issues = []
    for estado in estados:
        orphan_issues.extend(_lineas_huerfanas(estado))

    lineas_huerfanas = {
        "status": "ok" if not orphan_issues else "warning",
        "title": _("Lineas Huerfanas"),
        "value": len(orphan_issues),
        "detail": _("Sin incidencias.") if not orphan_issues else _("Se detectaron lineas sin padre valido."),
    }

    # Indicador 3: formulas rotas (estados + notas)
    formula_issues = []
    for estado in estados:
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

    formulas_rotas = {
        "status": "ok" if not formula_issues else "error",
        "title": _("Formulas Rotas"),
        "value": len(formula_issues),
        "detail": _("Sin incidencias.") if not formula_issues else _("Hay referencias invalidas o circulares."),
    }

    # Indicador 4: notas faltantes
    note_issues = _notas_faltantes(notas)
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
    score = max(score, 0)

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
            "cliente": package.cliente,
            "cliente_label": get_customer_display(package.cliente),
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
        },
        "details": {
            "lineas_huerfanas": orphan_issues,
            "formulas_rotas": formula_issues,
            "notas_faltantes": note_issues,
        },
        "meta": {
            "message": _("Estos indicadores son informativos y no bloquean la emision."),
        },
    }


def _bootstrap_response(cliente=None, anio=None, mes=None, paquete_name=None):
    selected_package = _clean(paquete_name) or None
    indicators = None
    if selected_package and frappe.db.exists("Paquete EEFF", selected_package):
        indicators = _compute_indicators(selected_package)

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
