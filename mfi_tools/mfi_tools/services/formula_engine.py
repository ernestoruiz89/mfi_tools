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
    <code>ANUAL_ANT("101*")</code> &rarr; Suma 12 meses año anterior Balanza<br>
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
                  "YTD", "YTD_ANT", "ANUAL_ANT", "CIERRE_ANT", "MES_AÑO_ANT", "MES_ANIO_ANT"}

def has_data_functions(expression):
    if not expression:
        return False
    expr = cstr(expression).upper()
    if "VAR " in expr:
        return True
    for func in DATA_FUNCTIONS:
        if f"{func}(" in expr:
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

def evaluate_formula(expression, context, period_context="actual"):
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
        lines = [line.strip() for line in expr.splitlines() if line.strip()]
        if not lines:
            return 0.0
            
        local_vars = {}
        result = 0.0
        
        for line in lines:
            if line.startswith("VAR "):
                parts = line[4:].split("=", 1)
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    var_expr = parts[1].strip()
                    
                    if var_name in safe_funcs:
                        frappe.throw(_("No puedes usar '{0}' como nombre de variable porque es una función reservada.").format(var_name))
                        
                    val = eval(var_expr, {"__builtins__": None}, {**safe_funcs, **local_vars})
                    local_vars[var_name] = flt(val)
                    result = local_vars[var_name]
                else:
                    val = eval(line, {"__builtins__": None}, {**safe_funcs, **local_vars})
                    result = flt(val)
            else:
                val = eval(line, {"__builtins__": None}, {**safe_funcs, **local_vars})
                result = flt(val)
                
        return result
    except ZeroDivisionError:
        return 0.0
    except Exception as e:
        frappe.throw(_("Error evaluando formula '{0}': {1}").format(expression, str(e)))
