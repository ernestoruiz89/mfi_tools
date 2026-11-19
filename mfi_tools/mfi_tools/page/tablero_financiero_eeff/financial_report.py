"""Financial dashboard sourced exclusively from the user's accessible EEFF balances."""
import base64
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import subprocess
import tempfile

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import getdate, now_datetime

from .report_currency import candidates, convert_amounts
from .balance import Balance, BALANCE_CODES
from .metrics import (FLOW_KEYS, METRICS, last_closed, money, month_end, ratio,
                      reporting_months, summarize_balance, variation)

DOCTYPE = "Balanza Comprobacion EEFF"


def _balances(filters):
    parents = frappe.get_list(
        DOCTYPE, filters={"docstatus": ["<", 2], **filters},
        fields=["name", "company", "moneda", "periodo_nombre", "fecha_corte", "cuadra", "modified"],
        order_by="fecha_corte desc, creation, name", limit_page_length=0,
    )
    # Only read rate rows of parents already visible to this user.
    permitted = {parent.name: parent for parent in parents}
    for parent in parents:
        parent.rates = {}
    if permitted:
        rate_rows = frappe.get_all(
            "Tasa Cambio Balanza EEFF",
            filters={"parenttype": DOCTYPE, "parentfield": "tasas_cambio", "parent": ["in", list(permitted)]},
            fields=["parent", "moneda", "tasa_cambio"], limit_page_length=0,
        )
        for row in rate_rows:
            if row.moneda and row.tasa_cambio and row.tasa_cambio > 0:
                permitted[row.parent].rates[row.moneda] = row.tasa_cambio
    return parents


@frappe.whitelist(methods=["GET"])
def get_options():
    frappe.has_permission(DOCTYPE, "read", throw=True)
    cutoff = last_closed(getdate())
    companies = defaultdict(dict)
    for row in _balances({"fecha_corte": ["<=", cutoff]}):
        if not row.moneda:
            continue
        key = str(row.fecha_corte)[:7]
        period = companies[row.company].setdefault(key, {"base": row.moneda, "currencies": set()})
        if row.name == row.periodo_nombre:
            period["base"] = row.moneda
        period["currencies"].update([row.moneda, *row.rates])
    result = []
    for name, periods in sorted(companies.items()):
        for period in periods.values():
            base = period["base"]
            period["currencies"] = [base, *sorted(period["currencies"] - {base})]
        latest = periods[max(periods)]
        result.append({"name": name, "currencies": latest["currencies"], "periods": periods})
    return {"companies": result, "default_cutoff": str(cutoff)}


def _dashboard(company, cutoff, currency):
    if not all(isinstance(value, str) and value for value in (company, cutoff, currency)):
        frappe.throw("Selecciona la empresa, moneda y mes de corte.")
    end = month_end(getdate(cutoff))
    if end > last_closed(getdate()) or end.year < 2000:
        frappe.throw("Selecciona un mes cerrado anterior al mes actual.")
    frappe.has_permission(DOCTYPE, "read", throw=True)
    periods = reporting_months(end)
    parents = _balances({"company": company, "fecha_corte": ["between", [periods[0]["from_date"], end]]})
    by_month = defaultdict(list)
    for parent in parents:
        by_month[str(parent.fecha_corte)[:7]].append(parent)
    warnings, monthly, annual, branches = [], {}, {}, defaultdict(dict)
    balances = defaultdict(dict)
    margins = {}
    for period in periods:
        key = period["key"]
        rows = by_month[key]
        matches = candidates(rows, currency)
        period.update(source=None, available=False)
        if len(matches) > 1:
            warnings.append(f"{period['label']} tiene varias balanzas para la misma moneda. Revisa el período.")
        if rows and not matches:
            warnings.append(f"{period['label']} carece de tasa registrada para {currency}.")
        if len(matches) != 1:
            continue
        parent = matches[0]
        doc = frappe.get_doc(DOCTYPE, parent.name)
        doc.check_permission("read")
        rate = 1 if currency == doc.moneda else parent.rates[currency]
        period.update(source=doc.name, source_currency=doc.moneda, exchange_rate=rate)
        if not doc.lineas:
            continue
        scoped_rows = defaultdict(list)
        for row in doc.lineas:
            scoped_rows[(row.centro_costo or "").strip()].append(row)
        try:
            if any(row.moneda and row.moneda != doc.moneda for row in doc.lineas):
                raise ValueError("Hay líneas con moneda distinta de la balanza.")
            balance = Balance(doc.lineas)
            if not balance.cover("1") or not (balance.cover("4") or balance.cover("5")):
                raise ValueError("Faltan las cuentas de activo o de resultados del catálogo MUC.")
            if "" in scoped_rows and len(scoped_rows) > 1:
                # Distinguish imported totals from the rows by branch. Overlapping
                # codes cannot safely be added without knowing the import convention.
                blank = Balance(scoped_rows[""])
                named = Balance([r for center, rows in scoped_rows.items() if center for r in rows])
                if blank.amounts.keys() & named.amounts.keys():
                    raise ValueError("Hay cuentas repetidas con y sin centro de costo. Revisa el consolidado.")
        except ValueError as error:
            warnings.append(f"{period['label']}. {error}")
            continue
        month_native = balance.results(0)
        monthly[key] = convert_amounts(month_native, rate)
        margins[key] = ratio(month_native["net"], month_native["revenue"])
        annual_native = balance.results(1)
        annual[key] = convert_amounts(annual_native, rate)
        position = balance.position()
        for metric, value in convert_amounts(position, rate).items():
            balances[metric][key] = value
        period["available"] = True
        if not parent.cuadra or abs(position["assets"]-position["liabilities"]-position["equity"]) > 0.02:
            warnings.append(f"Revisar el cuadre de la balanza de {period['label']}.")
        if balance.cover("63") and abs(annual_native["net"]-money(balance.value(1, "63"))) > 0.02:
            warnings.append(f"El resultado acumulado difiere de la cuenta 63 en {period['label']}.")
        if any(scoped_rows):
            for center, rows in scoped_rows.items():
                bucket = Balance(rows)
                branches[center or "Sin centro de costo"][key] = (
                    convert_amounts(bucket.results(0), rate), convert_amounts(bucket.results(1), rate)
                )

    missing = [month["label"] for month in periods if not month["available"]]
    if missing:
        warnings.append("Sin datos disponibles para " + ", ".join(missing) + ".")
    keys = [p["key"] for p in periods]
    series = {metric: [monthly.get(key, {}).get(metric) for key in keys] for metric in FLOW_KEYS}
    for metric in (*BALANCE_CODES, "gross_portfolio", "portfolio_change"):
        series[metric] = [balances[metric].get(key) for key in keys]
    series["margin"] = [margins.get(key) for key in keys]
    comparisons = {key: {"mom": variation(values[-1], values[-2])} for key, values in series.items()}
    empty = dict.fromkeys(FLOW_KEYS)
    current = annual.get(keys[-1], empty)
    findings = []
    for metric in ("net", "revenue", "expenses", "gross_portfolio", "cash"):
        change = comparisons[metric]["mom"]["amount"]
        if change is not None:
            findings.append(f"{METRICS[metric]}. Variación mensual de {currency} {change:,.2f}.")
    snapshot = hashlib.sha256(json.dumps([(p.name, str(p.modified), p.moneda, sorted(p.rates.items())) for p in parents]
                                          + [company, str(end), currency], ensure_ascii=False).encode()).hexdigest()
    return {
        "version": 1, "snapshot_id": snapshot,
        "meta": {"company": company, "currency": currency, "cutoff": str(end),
                 "scope": "Consolidado", "generated_at": str(now_datetime())},
        "months": periods, "labels": METRICS, "series": series, "comparisons": comparisons,
        "ytd": current, "prior_ytd": annual.get(keys[0], empty),
        "branches": [{"label": name, "monthly": data.get(keys[-1], (empty, empty))[0],
                      "ytd": data.get(keys[-1], (empty, empty))[1],
                      "series": [data[key][0]["net"] if key in data else None for key in keys]}
                     for name, data in sorted(branches.items())],
        "balance_summary": summarize_balance(balances, end),
        "findings": findings, "warnings": warnings,
        "reconciliation": {"equity_difference": variation(series["equity_result"][-1], current["net"])["amount"]},
        "definitions": ["Al elegir otra moneda se dividen los importes mensuales y acumulados de cada balanza por su tasa registrada para esa moneda.",
                        "El mes usa los movimientos de la balanza. El acumulado usa los saldos de ingresos, gastos e impuesto a la fecha de corte.",
                        "Resultado neto = ingresos (4) menos gastos (5) e impuesto (62).",
                        "El efectivo corresponde a la cuenta 11. La cartera bruta comprende las cuentas 1401 a 1405."],
    }


@frappe.whitelist(methods=["GET"])
def get_dashboard(company: str, cutoff: str, currency: str):
    return _dashboard(company, cutoff, currency)


def _run_powerpoint_generator(script: Path, source: Path, target: Path):
    try:
        result = subprocess.run(
            ["node", str(script), str(source), str(target)],
            timeout=60, capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        frappe.logger("mfi_tools").error("No se encontró Node.js al generar PowerPoint EEFF.")
        frappe.throw(
            _("El generador de PowerPoint no está disponible en el servidor. Contacta al administrador."),
            title=_("Generador no disponible"),
        )
    except subprocess.TimeoutExpired:
        frappe.logger("mfi_tools").error("Tiempo de espera agotado al generar PowerPoint EEFF.")
        frappe.throw(
            _("La presentación tardó demasiado en generarse. Inténtalo de nuevo o contacta al administrador."),
            title=_("Tiempo de espera agotado"),
        )

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        frappe.logger("mfi_tools").error(
            "Node terminó con código %s al generar PowerPoint EEFF.\n%s",
            result.returncode, details[-6000:],
        )
        if "MODULE_NOT_FOUND" in details or "Cannot find module" in details:
            frappe.throw(
                _("Faltan componentes del generador de PowerPoint en el servidor. Contacta al administrador."),
                title=_("Generador no disponible"),
            )
        frappe.throw(
            _("No se pudo generar la presentación. El detalle quedó registrado para el administrador."),
            title=_("Error al generar PowerPoint"),
        )

    if not target.is_file() or target.stat().st_size == 0:
        frappe.logger("mfi_tools").error(
            "El generador de PowerPoint EEFF terminó correctamente, pero no produjo un archivo PPTX."
        )
        frappe.throw(
            _("No se pudo generar la presentación. El detalle quedó registrado para el administrador."),
            title=_("Error al generar PowerPoint"),
        )


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=60)
def generate_powerpoint(company: str, cutoff: str, currency: str, snapshot_id: str, comments: str = "", scale: str = "1000"):
    data = _dashboard(company, cutoff, currency)
    if snapshot_id != data["snapshot_id"]:
        frappe.throw("Las balanzas disponibles cambiaron. Actualiza el tablero antes de exportar.")
    if str(scale) not in {"1", "1000", "1000000"} or len(comments) > 5000:
        frappe.throw("Revisa la escala y la longitud de los comentarios.")
    if not any(period["available"] for period in data["months"]):
        frappe.throw("No hay balanzas disponibles para generar el informe.")
    data.update(comments=comments, scale=int(scale))
    script = Path(frappe.get_app_path("mfi_tools")).parent / "scripts" / "informe_financiero.cjs"
    with tempfile.TemporaryDirectory(prefix="mfi-informe-") as temp:
        source, target = Path(temp) / "datos.json", Path(temp) / "informe.pptx"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _run_powerpoint_generator(script, source, target)
        return {"cutoff": data["meta"]["cutoff"], "content": base64.b64encode(target.read_bytes()).decode("ascii")}
