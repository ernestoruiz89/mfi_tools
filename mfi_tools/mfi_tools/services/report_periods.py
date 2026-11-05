import frappe
from frappe.utils import cint

MONTHS = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def configure_default_periods(doc):
    if cint(doc.get("periodicidad_configurada")):
        return
    # Explicit month selections from an API/import are respected as well.
    custom = any(cint(doc.get("emitir_" + month.lower())) for month in MONTHS)
    custom |= doc.get("emitir_todos_meses") in (0, "0")
    if not custom:
        selected = None
        if doc.get("tipo_estado") == "Estado de Cambios en el Patrimonio":
            selected = {"Junio", "Diciembre"}
        elif doc.get("tipo_estado") == "Estado de Flujos de Efectivo":
            selected = {"Diciembre"}
        doc.emitir_todos_meses = int(selected is None)
        for month in MONTHS:
            doc.set("emitir_" + month.lower(), int(month in (selected or set())))
    doc.periodicidad_configurada = 1


def should_emit(doc, month):
    if not cint(doc.get("periodicidad_configurada")):
        # Handles installations immediately before the metadata migration.
        if doc.get("tipo_estado") == "Estado de Cambios en el Patrimonio":
            return month in ("Junio", "Diciembre")
        if doc.get("tipo_estado") == "Estado de Flujos de Efectivo":
            return month == "Diciembre"
        return True
    if cint(doc.get("emitir_todos_meses")):
        return True
    return month in MONTHS and bool(cint(doc.get("emitir_" + month.lower())))


def get_states_for_period(package_name, month):
    return [row for row in frappe.get_all(
        "Estado Financiero EEFF", filters={"paquete_eeff": package_name},
        fields=["*"], order_by="orden_presentacion asc, creation asc",
    ) if should_emit(row, month)]
