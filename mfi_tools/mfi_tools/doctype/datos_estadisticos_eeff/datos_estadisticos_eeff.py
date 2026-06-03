import frappe
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

class DatosEstadisticosEEFF(Document):
    def autoname(self):
        self._sync_period_fields()
        if self.nombre_datos_estadisticos:
            self.name = self.nombre_datos_estadisticos

    def validate(self):
        self._sync_period_fields()
        self._normalizar_lineas()
        self.total_lineas = len(self.get("lineas") or [])

    def _sync_period_fields(self):
        company = cstr(self.company or "").strip()
        mes = cstr(self.mes or "").strip()
        anio = cint(self.anio or 0)
        if not company or not mes or not anio:
            return

        self.periodo_nombre = f"{company}-{mes}-{anio}"
        self.nombre_datos_estadisticos = self.nombre_datos_estadisticos or f"Datos-{self.periodo_nombre}"

    def _normalizar_lineas(self):
        seen = set()
        for idx, row in enumerate(self.get("lineas") or [], start=1):
            row.orden = cint(getattr(row, "orden", idx) or idx)
            row.codigo_dato = cstr(getattr(row, "codigo_dato", "") or frappe.scrub(getattr(row, "descripcion", "") or f"dato_{idx}")).strip().upper()
            row.descripcion = cstr(getattr(row, "descripcion", "") or row.codigo_dato or f"Dato {idx}").strip()
            row.categoria = cstr(getattr(row, "categoria", "") or "").strip()
            row.unidad_medida = cstr(getattr(row, "unidad_medida", "") or "").strip()
            row.formula_datos = cstr(getattr(row, "formula_datos", "") or "").strip().upper()
            row.no_imprimir = cint(getattr(row, "no_imprimir", 0) or 0)
            row.origen_dato = cstr(getattr(row, "origen_dato", "Manual") or "Manual").strip() or "Manual"
            row.valor_actual = flt(getattr(row, "valor_actual", 0) or 0)
            if row.formula_datos and row.origen_dato != "Formula":
                row.origen_dato = "Formula"

            if not row.codigo_dato:
                frappe.throw("Cada linea debe tener codigo de dato.", title="Dato Invalido")
            if row.codigo_dato in seen:
                frappe.throw(f"El dato estadistico con codigo {row.codigo_dato} esta duplicado.", title="Codigo Duplicado")
            seen.add(row.codigo_dato)


@frappe.whitelist()
def duplicar_a_moneda(docname, moneda_destino, tasa_cambio, operacion):
    from frappe import _
    if not frappe.db.exists("Datos Estadisticos EEFF", docname):
        frappe.throw(_("El documento de datos estadisticos indicado no existe."))
        
    doc = frappe.get_doc("Datos Estadisticos EEFF", docname)
    moneda_destino = cstr(moneda_destino or "").strip().upper()
    tasa_cambio = flt(tasa_cambio or 1)
    if tasa_cambio <= 0:
        frappe.throw(_("La tasa de cambio debe ser mayor a cero."))
        
    new_doc = frappe.copy_doc(doc)
    new_doc.moneda = moneda_destino
    new_doc.nombre_datos_estadisticos = f"{doc.nombre_datos_estadisticos} - {moneda_destino}"

    
    for row in new_doc.get("lineas") or []:
        if operacion == "Multiplicar":
            row.valor_actual = flt(row.valor_actual) * tasa_cambio
        else:
            row.valor_actual = flt(row.valor_actual) / tasa_cambio
            
    new_doc.save(ignore_permissions=True)
    return new_doc.name
