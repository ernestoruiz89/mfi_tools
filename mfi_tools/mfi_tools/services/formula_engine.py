import ast
import re
import frappe
from frappe import _
from frappe.utils import flt, cstr

FORMULA_HELP_HTML = """
<div style="font-size: 11px; line-height: 1.5; color: var(--text-muted);">
    <strong>&#9654; Balanza</strong><br>
    <code>BAL("101*")</code> &rarr; Saldo cuentas 101 (contextual: actual o comparativo)<br>
    <code>BAL("101*", "SALDO_ANTERIOR")</code> &rarr; Saldo anterior<br>
    <code>BAL("101*", "MOVIMIENTO_DEL_MES")</code> &rarr; Movimiento del mes<br>
    <code>BAL_ACT("101*")</code> &rarr; Siempre balanza actual<br>
    <code>BAL_COMP("101*")</code> &rarr; Siempre balanza comparativa<br>
    <code>BAL_BASE_ACT("101*")</code> / <code>BAL_BASE_COMP("101*")</code> &rarr; Balanzas base<br>
    <br>
    <strong>&#9654; Estadísticos</strong><br>
    <code>EST("NO_EMP")</code> &rarr; Dato estadístico (contextual: actual o comparativo)<br>
    <code>EST_ACT("NO_EMP")</code> &rarr; Siempre estadístico actual<br>
    <code>EST_COMP("NO_EMP")</code> &rarr; Siempre estadístico comparativo<br>
    <br>
    <strong>&#9654; Históricas (por defecto usan Balanza)</strong><br>
    <code>YTD("101*")</code> &rarr; YTD Balanza (Ene a mes actual, movimiento_del_mes)<br>
    <code>YTD("NO_EMP", "EST")</code> &rarr; YTD Estadístico<br>
    <code>YTD_ANT("101*")</code> &rarr; YTD Año Anterior Balanza<br>
    <code>YTD_ANT("NO_EMP", "EST")</code> &rarr; YTD Año Anterior Estadístico<br>
    <code>ANUAL("101*")</code> &rarr; Suma 12 meses año actual Balanza<br>
    <code>ANUAL_ANT("101*")</code> &rarr; Suma 12 meses año anterior Balanza<br>
    <code>ANUAL("NO_EMP", "EST")</code> &rarr; Suma 12 meses año actual Estadístico<br>
    <code>ANUAL_ANT("NO_EMP", "EST")</code> &rarr; Suma 12 meses año anterior Estadístico<br>
    <code>CIERRE_ANT("101*")</code> &rarr; Saldo cierre dic. año anterior Balanza<br>
    <code>CIERRE_ANT("NO_EMP", "EST")</code> &rarr; Cierre año anterior Estadístico<br>
    <code>MES_ANIO_ANT("101*")</code> &rarr; Mismo mes año anterior Balanza<br>
    <code>MES_ANIO_ANT("NO_EMP", "EST")</code> &rarr; Mismo mes año anterior Estadístico<br>
    <br>
    <strong>&#9654; Matemáticas</strong><br>
    <code>ABS(x)</code>, <code>MAX(a, b)</code>, <code>MIN(a, b)</code>, <code>REDONDEAR(x, 2)</code><br>
    <code>SI(condicion, valor_si, valor_no)</code><br>
    Operadores: <code>+ - * / ** ()</code><br>
    <br>
    <strong>&#9654; Variables</strong><br>
    <code>VAR SC = BAL("1401*") + BAL("1402*")</code><br>
    <code>VAR TC = EST("TIPO_CAMBIO")</code><br>
    <code>VAR SC_USD = SC / TC</code><br>
    <code>SC_USD</code> &larr; última línea = resultado<br>
</div>
"""


DATA_FUNCTIONS = {"BAL", "BAL_ACT", "BAL_COMP", "BAL_BASE_ACT", "BAL_BASE_COMP",
                  "EST", "EST_ACT", "EST_COMP",
                  "YTD", "YTD_ANT", "ANUAL", "ANUAL_ANT", "CIERRE_ANT", "MES_AÑO_ANT", "MES_ANIO_ANT"}

def has_data_functions(expression):
    if not expression:
        return False
    expr = cstr(expression).upper()
    if "VAR " in expr:
        return True
    for func in DATA_FUNCTIONS:
        if f"{func}(" in expr or f"{func} (" in expr:
            return True
    return False

class FormulaContext:
    def __init__(self, actual_balances=None, comparative_balances=None,
                 base_actual_balances=None, base_comparative_balances=None,
                 actual_stats=None, comparative_stats=None, historical_data=None):
        self.actual_balances = actual_balances or {}
        self.comparative_balances = comparative_balances or {}
        self.base_actual_balances = base_actual_balances or {}
        self.base_comparative_balances = base_comparative_balances or {}
        self.actual_stats = actual_stats or {}
        self.comparative_stats = comparative_stats or {}
        self.historical_data = historical_data or {}


def _get_balance_value(pattern, field, balance_map):
    if not balance_map:
        return 0.0
    field = cstr(field or "saldo").strip().lower()
    if field not in ("saldo", "saldo_anterior", "movimiento_del_mes"):
        field = "saldo"
    
    if field not in balance_map:
        return 0.0
        
    code_map = balance_map[field].get("codigo_cuenta", {}).get("all", {})
    pat = cstr(pattern or "").strip().upper()
    
    if not pat:
        return 0.0
        
    if pat.endswith("*"):
        prefix = pat[:-1]
        if not prefix:
            return 0.0
        total = 0.0
        for code, amount in code_map.items():
            if cstr(code or "").startswith(prefix):
                total += flt(amount)
        return total
    
    return flt(code_map.get(pat, 0.0))

def _get_stat_value(code, stat_map):
    if not stat_map:
        return 0.0
    pat = cstr(code or "").strip().upper()
    return flt(stat_map.get(pat, 0.0))

def _get_ytd_balance_value(pattern, historical_ytd_dict, field="movimiento_del_mes"):
    if not historical_ytd_dict:
        return 0.0
    total = 0.0
    for period_key, balance_map in historical_ytd_dict.items():
        total += _get_balance_value(pattern, field, balance_map)
    return total

def _get_ytd_stat_value(code, historical_ytd_dict):
    if not historical_ytd_dict:
        return 0.0
    total = 0.0
    pat = cstr(code or "").strip().upper()
    for period_key, stat_map in historical_ytd_dict.items():
        total += flt(stat_map.get(pat, 0.0))
    return total


VAR_PATTERN = re.compile(r"^\s*VAR\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=(.*)$", re.IGNORECASE)
CONTINUATION_END_OPS = ("+", "-", "*", "/", "%", "**", ",", "(", "[", "=")
NON_UNARY_START_OPS = ("*", "/", "%", "**", ",", ")", "]")
UNARY_OR_BINARY_OPS = ("+", "-")


def _is_escaped(s, idx):
    count = 0
    i = idx - 1
    while i >= 0 and s[i] == "\\":
        count += 1
        i -= 1
    return (count % 2) == 1


def _has_unclosed_delimiters(text):
    in_quote = None
    paren_depth = 0
    for i, ch in enumerate(text):
        if in_quote:
            if ch == in_quote and not _is_escaped(text, i):
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
        elif ch in "([{":
            paren_depth += 1
        elif ch in ")]}":
            paren_depth = max(0, paren_depth - 1)
    return paren_depth > 0


def _is_valid_expr(s):
    try:
        ast.parse(s.strip().rstrip("; \t\r\n"), mode="eval")
        return True
    except (SyntaxError, ValueError):
        return False


def _split_into_lines(expr):
    """
    Divide una formula en lineas respetando saltos de linea, puntos y coma fuera de comillas,
    y separando sentencias VAR que se hayan escrito consecutivamente en una sola linea.
    """
    raw_chunks = []
    for raw_line in expr.splitlines():
        in_quote = None
        curr = []
        i = 0
        while i < len(raw_line):
            ch = raw_line[i]
            if in_quote:
                curr.append(ch)
                if ch == in_quote and not _is_escaped(raw_line, i):
                    in_quote = None
            elif ch in ('"', "'"):
                in_quote = ch
                curr.append(ch)
            elif ch == ";":
                chunk = "".join(curr).strip()
                if chunk:
                    raw_chunks.append(chunk)
                curr = []
            elif ch == "/" and i + 1 < len(raw_line) and raw_line[i + 1] == "/":
                break
            elif ch == "#":
                break
            else:
                if (ch == "V" or ch == "v") and i + 3 < len(raw_line):
                    sub = raw_line[i:i+4]
                    if sub.upper() == "VAR " and curr:
                        prev_char = raw_line[i-1] if i > 0 else " "
                        if prev_char.isspace() or prev_char in "=;,+-*/":
                            chunk = "".join(curr).strip()
                            if chunk:
                                raw_chunks.append(chunk)
                            curr = []
                curr.append(ch)
            i += 1
        chunk = "".join(curr).strip()
        if chunk:
            raw_chunks.append(chunk)
    return raw_chunks


def _parse_formula_statements(expr):
    lines = _split_into_lines(expr)
    if not lines:
        return []

    # Si no hay declaraciones VAR en toda la formula, se evalua toda como una sola expresion
    has_any_var = any(VAR_PATTERN.match(l) for l in lines)
    if not has_any_var:
        return [("EXPR", None, "\n".join(lines))]

    statements = []
    current_type = None
    current_var = None
    current_chunk = []

    def flush():
        if current_type == "VAR":
            statements.append(("VAR", current_var, "\n".join(current_chunk)))
        elif current_type == "EXPR":
            statements.append(("EXPR", None, "\n".join(current_chunk)))

    for line in lines:
        var_match = VAR_PATTERN.match(line)
        if var_match:
            flush()
            current_type = "VAR"
            current_var = var_match.group(1).strip()
            rest = var_match.group(2).strip()
            current_chunk = [rest] if rest else []
            continue

        if current_type is None:
            current_type = "EXPR"
            current_chunk = [line]
            continue

        # Si estamos en un VAR y no tenia expresion en la misma linea (ej. VAR SC = \n ...)
        if current_type == "VAR" and not any(c.strip() for c in current_chunk):
            current_chunk.append(line)
            continue

        prev_text = "\n".join(current_chunk).rstrip()
        is_continuation = False
        if _has_unclosed_delimiters(prev_text):
            is_continuation = True
        elif any(prev_text.endswith(op) for op in CONTINUATION_END_OPS):
            is_continuation = True
        elif any(line.startswith(op) for op in NON_UNARY_START_OPS):
            is_continuation = True
        elif any(line.startswith(op) for op in UNARY_OR_BINARY_OPS):
            if current_type == "VAR":
                if current_var and re.search(r"\b" + re.escape(current_var) + r"\b", line):
                    is_continuation = False
                elif _is_valid_expr(prev_text):
                    is_continuation = False
                else:
                    is_continuation = True
            else:
                is_continuation = True

        if is_continuation:
            current_chunk.append(line)
        else:
            flush()
            current_type = "EXPR"
            current_var = None
            current_chunk = [line]

    flush()
    return statements


def evaluate_formula(expression, context, period_context="actual", doc_context=None):
    expr = cstr(expression or "").strip().upper()
    if not expr:
        return 0.0
        
    default_balances = context.comparative_balances if period_context == "comparativo" else context.actual_balances
    default_stats = context.comparative_stats if period_context == "comparativo" else context.actual_stats
    
    def func_bal(pattern, field="saldo"): return _get_balance_value(pattern, field, default_balances)
    def func_bal_act(pattern, field="saldo"): return _get_balance_value(pattern, field, context.actual_balances)
    def func_bal_comp(pattern, field="saldo"): return _get_balance_value(pattern, field, context.comparative_balances)
    def func_bal_base_act(pattern, field="saldo"): return _get_balance_value(pattern, field, context.base_actual_balances)
    def func_bal_base_comp(pattern, field="saldo"): return _get_balance_value(pattern, field, context.base_comparative_balances)
    
    def func_est(code): return _get_stat_value(code, default_stats)
    def func_est_act(code): return _get_stat_value(code, context.actual_stats)
    def func_est_comp(code): return _get_stat_value(code, context.comparative_stats)
    
    def _parse_args(arg1, arg2, default_field):
        a1 = cstr(arg1).strip().upper()
        if a1 == "EST": return "EST", None
        if a1 == "BAL": return "BAL", cstr(arg2 or default_field).strip().lower()
        if a1 in ("SALDO", "MOVIMIENTO_DEL_MES", "SALDO_ANTERIOR"): return "BAL", a1.lower()
        return "BAL", default_field

    def func_ytd(pattern, arg1="BAL", arg2=None):
        src, field = _parse_args(arg1, arg2, "movimiento_del_mes")
        if src == "EST":
            hist_stat = context.historical_data.get("ytd_comparativo_stats") if period_context == "comparativo" else context.historical_data.get("ytd_actual_stats")
            return _get_ytd_stat_value(pattern, hist_stat)
        hist_bal = context.historical_data.get("ytd_comparativo_balances") if period_context == "comparativo" else context.historical_data.get("ytd_actual_balances")
        return _get_ytd_balance_value(pattern, hist_bal, field)
        
    def func_ytd_ant(pattern, arg1="BAL", arg2=None):
        src, field = _parse_args(arg1, arg2, "movimiento_del_mes")
        if src == "EST":
            hist_stat = context.historical_data.get("ytd_anio_anterior_comparativo_stats") if period_context == "comparativo" else context.historical_data.get("ytd_anio_anterior_actual_stats")
            return _get_ytd_stat_value(pattern, hist_stat)
        hist_bal = context.historical_data.get("ytd_anio_anterior_comparativo_balances") if period_context == "comparativo" else context.historical_data.get("ytd_anio_anterior_actual_balances")
        return _get_ytd_balance_value(pattern, hist_bal, field)

    def func_anual(pattern, arg1="BAL", arg2=None):
        src, field = _parse_args(arg1, arg2, "movimiento_del_mes")
        if src == "EST":
            hist_stat = context.historical_data.get("suma_anio_completo_comparativo_stats") if period_context == "comparativo" else context.historical_data.get("suma_anio_completo_actual_stats")
            return _get_ytd_stat_value(pattern, hist_stat)
        hist_bal = context.historical_data.get("suma_anio_completo_comparativo_balances") if period_context == "comparativo" else context.historical_data.get("suma_anio_completo_actual_balances")
        return _get_ytd_balance_value(pattern, hist_bal, field)

    def func_anual_ant(pattern, arg1="BAL", arg2=None):
        src, field = _parse_args(arg1, arg2, "movimiento_del_mes")
        if src == "EST":
            hist_stat = context.historical_data.get("suma_anio_completo_anterior_comparativo_stats") if period_context == "comparativo" else context.historical_data.get("suma_anio_completo_anterior_actual_stats")
            return _get_ytd_stat_value(pattern, hist_stat)
        hist_bal = context.historical_data.get("suma_anio_completo_anterior_comparativo_balances") if period_context == "comparativo" else context.historical_data.get("suma_anio_completo_anterior_actual_balances")
        return _get_ytd_balance_value(pattern, hist_bal, field)

    def func_cierre_ant(pattern, arg1="BAL", arg2=None):
        src, field = _parse_args(arg1, arg2, "saldo")
        if src == "EST":
            hist_stat = context.historical_data.get("cierre_anterior_comparativo_stats") if period_context == "comparativo" else context.historical_data.get("cierre_anterior_actual_stats")
            return _get_stat_value(pattern, hist_stat)
        hist_bal = context.historical_data.get("cierre_anterior_comparativo_balances") if period_context == "comparativo" else context.historical_data.get("cierre_anterior_actual_balances")
        return _get_balance_value(pattern, field, hist_bal)

    def func_mes_anio_ant(pattern, arg1="BAL", arg2=None):
        src, field = _parse_args(arg1, arg2, "saldo")
        if src == "EST":
            hist_stat = context.historical_data.get("anio_anterior_comparativo_stats") if period_context == "comparativo" else context.historical_data.get("anio_anterior_actual_stats")
            return _get_stat_value(pattern, hist_stat)
        hist_bal = context.historical_data.get("anio_anterior_comparativo_balances") if period_context == "comparativo" else context.historical_data.get("anio_anterior_actual_balances")
        return _get_balance_value(pattern, field, hist_bal)

    safe_funcs = {
        "BAL": func_bal,
        "BAL_ACT": func_bal_act,
        "BAL_COMP": func_bal_comp,
        "BAL_BASE_ACT": func_bal_base_act,
        "BAL_BASE_COMP": func_bal_base_comp,
        "EST": func_est,
        "EST_ACT": func_est_act,
        "EST_COMP": func_est_comp,
        "YTD": func_ytd,
        "YTD_ANT": func_ytd_ant,
        "ANUAL": func_anual,
        "ANUAL_ANT": func_anual_ant,
        "CIERRE_ANT": func_cierre_ant,
        "MES_AÑO_ANT": func_mes_anio_ant,
        "MES_ANIO_ANT": func_mes_anio_ant,
        "ABS": abs,
        "MAX": max,
        "MIN": min,
        "REDONDEAR": lambda x, n=0: round(x, int(n)),
        "SI": lambda cond, v_true, v_false: v_true if cond else v_false,
    }

    try:
        statements = _parse_formula_statements(expr)
        if not statements:
            return 0.0

        local_vars = {}
        result = 0.0

        for stype, var_name, code in statements:
            clean_code = code.strip().rstrip("; \t\r\n")
            if not clean_code:
                continue

            if stype == "VAR":
                if var_name in safe_funcs:
                    frappe.throw(_("No puedes usar '{0}' como nombre de variable porque es una función reservada.").format(var_name))

                val = eval("(\n" + clean_code + "\n)", {"__builtins__": {}}, {**safe_funcs, **local_vars})
                local_vars[var_name] = flt(val)
                result = local_vars[var_name]
            else:
                val = eval("(\n" + clean_code + "\n)", {"__builtins__": {}}, {**safe_funcs, **local_vars})
                result = flt(val)

        return result
    except ZeroDivisionError:
        return 0.0
    except Exception as e:
        info_parts = []
        if doc_context:
            if isinstance(doc_context, dict):
                tipo = doc_context.get("tipo") or doc_context.get("doctype")
                nombre = doc_context.get("nombre") or doc_context.get("docname")
                linea = doc_context.get("linea") or doc_context.get("row_code") or doc_context.get("codigo")
                col = doc_context.get("columna") or doc_context.get("col")
                desc = doc_context.get("descripcion") or doc_context.get("row_desc")
                periodo = doc_context.get("periodo") or period_context

                if tipo:
                    info_parts.append(f"Tipo: {tipo}")
                if nombre:
                    info_parts.append(f"Documento: {nombre}")
                if linea:
                    info_parts.append(f"Línea/Fila: {linea}")
                if col:
                    info_parts.append(f"Columna: {col}")
                if desc:
                    info_parts.append(f"Descripción: {desc}")
                if periodo:
                    info_parts.append(f"Periodo: {periodo}")
            else:
                info_parts.append(str(doc_context))

        ubicacion = f" [{', '.join(info_parts)}]" if info_parts else ""
        frappe.throw(
            _("Error evaluando formula '{0}'{1}: {2}").format(expression, ubicacion, str(e)),
            title=_("Error en Fórmula")
        )
