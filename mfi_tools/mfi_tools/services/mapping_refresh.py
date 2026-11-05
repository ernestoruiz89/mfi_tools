"""Keep package calculations in sync without losing a successful import or copy."""

import json

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime

PACKAGE = "Paquete EEFF"
BALANCE = "Balanza Comprobacion EEFF"
BALANCE_LINKS = (
    "balanza_comprobacion_eeff", "balanza_comparativa_eeff",
    "balanza_base_actual_eeff", "balanza_base_comparativa_eeff",
)
SOURCE_FIELDS = BALANCE_LINKS + (
    "datos_estadisticos_actual_eeff", "datos_estadisticos_comparativo_eeff",
    "company", "moneda", "anio", "mes",
)
HISTORICAL_PATTERN = r"(YTD|YTD_ANT|ANUAL|ANUAL_ANT|CIERRE_ANT|MES_AÑO_ANT|MES_ANIO_ANT)[[:space:]]*[(]"


def status_available():
    return frappe.db.has_column(PACKAGE, "mapeo_desactualizado")


def mark_pending(name, reason):
    if status_available():
        frappe.db.set_value(PACKAGE, name, {
            "mapeo_desactualizado": 1, "detalle_mapeo": reason,
        }, update_modified=False)


def record_mapping_result(name, alerts):
    if status_available():
        frappe.db.set_value(PACKAGE, name, {
            "mapeo_desactualizado": int(bool(alerts)),
            "ultimo_mapeo": now_datetime(),
            "detalle_mapeo": (_("Mapeo ejecutado con advertencias. Revisa las reglas pendientes.")
                               if alerts else _("Mapeo actualizado.")),
        }, update_modified=False)


def package_sources_saved(doc):
    previous = doc.get_doc_before_save()
    if not previous or any(doc.get(field) != previous.get(field) for field in SOURCE_FIELDS):
        reason = _("Las fuentes del paquete cambiaron. Ejecuta el mapeo para actualizar los importes.")
        mark_pending(doc.name, reason)
        doc.mapeo_desactualizado = 1
        doc.detalle_mapeo = reason


def recalculate_package(name):
    """Rollback only the mapping on failure; leave the imported/copied data intact."""
    from mfi_tools.mfi_tools.services.mapeo import aplicar_mapeo_paquete

    mark_pending(name, _("Mapeo pendiente de recalculo."))
    savepoint = "mapping_" + frappe.generate_hash(length=10)
    messages = list(getattr(frappe.local, "message_log", None) or [])
    frappe.db.savepoint(savepoint)
    try:
        package = frappe.get_doc(PACKAGE, name)
        package.check_permission("write")
        package.save()
        result = aplicar_mapeo_paquete(name)
        result["mapeo_desactualizado"] = bool(result.get("alertas"))
    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        frappe.local.message_log = messages
        reason = _("No se pudo actualizar el mapeo: {0}").format(cstr(exc)[:500])
        mark_pending(name, reason)
        if not isinstance(exc, frappe.PermissionError):
            frappe.log_error(title="Error de mapeo automatico EEFF", message=frappe.get_traceback())
        result = {"paquete": name, "mapeo_desactualizado": True, "error": reason, "alertas": []}
    finally:
        frappe.db.release_savepoint(savepoint)
    return result


def _balance_signature(doc):
    from mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff import BALANCE_AMOUNT_FIELDS

    line_fields = ("codigo_cuenta", "descripcion_cuenta", "centro_costo") + tuple(BALANCE_AMOUNT_FIELDS)
    data = {field: doc.get(field) for field in ("company", "moneda", "anio", "mes")}
    data["lineas"] = [{field: row.get(field) for field in line_fields} for row in doc.get("lineas") or []]
    data["tasas_cambio"] = [{field: row.get(field) for field in ("moneda", "tasa_cambio")}
                            for row in doc.get("tasas_cambio") or []]
    return json.dumps(data, sort_keys=True, default=str)


def _has_historical_formulas(package_name):
    for parent, child, formula in (
        ("Estado Financiero EEFF", "Linea Estado Financiero EEFF", "formula_lineas"),
        ("Nota EEFF", "Cifra Nota EEFF", "formula_cifras"),
        ("Seccion Nota EEFF", "Celda Seccion Nota EEFF", "formula_celda"),
        ("Estado Financiero EEFF", "Celda Seccion Nota EEFF", "formula_celda"),
        ("Factsheet", "Linea Factsheet", "formula"),
    ):
        if frappe.db.sql(
            f"""SELECT 1 FROM `tab{child}` c JOIN `tab{parent}` p ON p.name = c.parent
                WHERE p.paquete_eeff = %s AND c.parenttype = %s
                  AND UPPER(c.`{formula}`) REGEXP %s LIMIT 1""",
            (package_name, parent, HISTORICAL_PATTERN),
        ):
            return True
    return False


def _mark_historical_packages(changed_versions, directly_updated):
    companies = list({doc.get("company") for doc in changed_versions if doc.get("company")})
    if not companies:
        return
    packages = frappe.get_all(PACKAGE, filters={"company": ["in", companies]},
                              fields=["name", *BALANCE_LINKS])
    source_cache = {}
    for package in packages:
        if package.name in directly_updated:
            continue
        affected = False
        for field in BALANCE_LINKS[:2]:
            source = package.get(field)
            if not source:
                continue
            if source not in source_cache:
                source_cache[source] = frappe.db.get_value(BALANCE, source, ["company", "moneda", "anio"], as_dict=True)
            values = source_cache[source]
            if values and any(values.company == doc.get("company") and values.moneda == doc.get("moneda")
                              and int(values.anio) - int(doc.get("anio") or 0) in (0, 1)
                              for doc in changed_versions):
                affected = True
        if affected and _has_historical_formulas(package.name):
            mark_pending(package.name, _("Cambio una balanza que puede afectar a las formulas historicas. Ejecuta el mapeo."))


def balance_saved(doc):
    if not status_available():
        return []
    previous = doc.get_doc_before_save()
    if previous and not doc.flags.get("refresh_mapping") and _balance_signature(previous) == _balance_signature(doc):
        return []
    names = frappe.get_all(PACKAGE, or_filters={field: doc.name for field in BALANCE_LINKS},
                           pluck="name", order_by="name")
    results = [recalculate_package(name) for name in names]
    _mark_historical_packages([d for d in (doc, previous) if d], set(names))
    doc.flags.mapping_results = results
    if results:
        failed = any(result["mapeo_desactualizado"] for result in results)
        pending = sum(bool(result["mapeo_desactualizado"]) for result in results)
        frappe.msgprint(
            _("Balanza guardada. Paquetes actualizados: {0}. Paquetes pendientes: {1}.").format(
                len(results) - pending, pending),
            title=_("Actualizacion de paquetes"), indicator="orange" if failed else "green",
        )
    return results
