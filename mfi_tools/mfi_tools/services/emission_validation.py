"""Read-only checks shared by the emission indicators and their regression tests."""

import ast
from html import unescape
from html.parser import HTMLParser

import frappe
from frappe import _
from frappe.utils import cint, cstr

from mfi_tools.mfi_tools.services.formula_engine import DATA_FUNCTIONS, _parse_formula_statements


class _ContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
        self.has_image = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag == "img" and not self.hidden:
            self.has_image |= bool(cstr(dict(attrs).get("src") or "").strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def has_rich_text(value):
    parser = _ContentParser()
    parser.feed(cstr(value or ""))
    text = unescape("".join(parser.parts))
    for invisible in ("\u200b", "\ufeff"):
        text = text.replace(invisible, "")
    return bool(text.strip()) or parser.has_image


def data_formula_issues(expression):
    """Check the engine's statement syntax without evaluating data or executing expressions."""
    known = set(DATA_FUNCTIONS) | {
        "ABS", "MAX", "MIN", "REDONDEAR", "SI", "PERIODO", "ACTUAL", "COMPARATIVO",
    }
    reserved = set(known)
    arities = {name: (1, 3) for name in DATA_FUNCTIONS}
    arities.update({name: (1, 2) for name in DATA_FUNCTIONS if name.startswith("BAL")})
    arities.update({name: (1, 1) for name in ("EST", "EST_ACT", "EST_COMP", "ABS")})
    arities.update({name: (0, 1) for name in ("VAL_ACT", "VAL_COMP")})
    arities.update({name: (0, 0) for name in ("ES_ACTUAL", "ES_COMPARATIVO", "PERIODO")})
    arities.update(SI=(3, 3), REDONDEAR=(1, 2), MAX=(1, float("inf")), MIN=(1, float("inf")))
    issues = []
    try:
        statements = _parse_formula_statements(cstr(expression).strip().upper())
        for kind, variable, code in statements:
            clean_code = code.strip().rstrip("; \t\r\n")
            if not clean_code:
                issues.append(_("Expresion de formula vacia."))
                continue
            tree = ast.parse("(\n" + clean_code + "\n)", mode="eval")
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id not in known:
                    issues.append(_("Funcion o variable desconocida: {0}.").format(node.id))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    bounds = arities.get(node.func.id)
                    count = len(node.args) + len(node.keywords)
                    if bounds is None or not bounds[0] <= count <= bounds[1]:
                        issues.append(_("Llamada invalida a {0}: revisa sus argumentos.").format(node.func.id))
                if isinstance(node, (ast.Attribute, ast.Subscript, ast.Lambda, ast.ListComp,
                                     ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.NamedExpr)):
                    issues.append(_("Expresion no soportada en una formula de datos."))
            if kind == "VAR":
                if variable in reserved:
                    issues.append(_("Nombre de variable reservado: {0}.").format(variable))
                known.add(variable)
    except (SyntaxError, ValueError) as exc:
        issues.append(_("Sintaxis de formula invalida: {0}.").format(getattr(exc, "msg", str(exc))))
    return list(dict.fromkeys(issues))


def tabular_formula_issues(doc, scope):
    """Use the document's own row/column precedence and cycle rules, on an unsaved copy."""
    issues = []
    copy = frappe.get_doc(doc.as_dict())
    messages = list(getattr(frappe.local, "message_log", None) or [])
    try:
        copy._validar_formulas_tabulares()
        copy._calcular_tablas()
    except (frappe.ValidationError, RecursionError) as exc:
        issues.append({
            "scope": scope, "documento": doc.name, "codigo": "Tablas",
            "formula": "", "referencia": "-", "motivo": cstr(exc),
        })
    finally:
        # A diagnostic must not leave throw() messages queued for the next request.
        frappe.local.message_log = messages
    for cell in doc.celdas_tabulares or []:
        if cell.origen_dato != "Formula" or not cstr(cell.formula_celda or "").strip():
            continue
        for message in data_formula_issues(cell.formula_celda):
            issues.append({
                "scope": scope, "documento": doc.name,
                "codigo": ".".join(cstr(cell.get(f) or "") for f in
                                   ("codigo_tabla", "codigo_fila", "codigo_columna")),
                "formula": cell.formula_celda, "referencia": "-", "motivo": message,
            })
    return issues


def has_figure_content(row):
    return not any(cint(row.get(flag)) for flag in ("no_imprimir", "es_titulo", "es_linea_blanco"))


def section_has_content(section):
    if has_rich_text(section.contenido_narrativo) or has_rich_text(section.get("observaciones")):
        return True
    titles = {(row.codigo_tabla, row.codigo_fila) for row in section.filas_tabulares or []
              if row.tipo_fila == "Titulo"}
    return any(
        (cell.codigo_tabla, cell.codigo_fila) not in titles
        and (cell.valor_numero not in (None, "") or has_rich_text(cell.valor_texto))
        for cell in section.celdas_tabulares or []
    )
