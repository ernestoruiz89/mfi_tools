import frappe


def execute():
    from mfi_tools.mfi_tools.services.report_periods import MONTHS, configure_default_periods

    frappe.reload_doc("mfi_tools", "doctype", "paquete_eeff", force=True)
    frappe.reload_doc("mfi_tools", "doctype", "estado_financiero_eeff", force=True)
    for name in frappe.get_all("Estado Financiero EEFF", pluck="name"):
        doc = frappe.get_doc("Estado Financiero EEFF", name)
        if doc.get("periodicidad_configurada"):
            continue
        configure_default_periods(doc)
        fields = ["emitir_todos_meses", "periodicidad_configurada", *["emitir_" + month.lower() for month in MONTHS]]
        frappe.db.set_value(doc.doctype, doc.name, {field: doc.get(field) for field in fields}, update_modified=False)
    frappe.db.set_value("Paquete EEFF", {}, {
        "mapeo_desactualizado": 1,
        "detalle_mapeo": "Ejecuta el mapeo para confirmar que el paquete utiliza las fuentes actuales.",
    }, update_modified=False)
    frappe.clear_cache()
