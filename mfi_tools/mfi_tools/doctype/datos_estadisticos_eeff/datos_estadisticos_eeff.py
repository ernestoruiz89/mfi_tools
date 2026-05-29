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
            row.es_manual = cint(getattr(row, "es_manual", 1) if getattr(row, "es_manual", None) is not None else 1)
            row.calculo_automatico = cint(getattr(row, "calculo_automatico", 0) or 0)
            row.no_imprimir = cint(getattr(row, "no_imprimir", 0) or 0)
            row.origen_dato = cstr(getattr(row, "origen_dato", "Manual") or "Manual").strip() or "Manual"
            row.valor_actual = flt(getattr(row, "valor_actual", 0) or 0)
            if row.formula_datos and not row.calculo_automatico:
                row.calculo_automatico = 1
                row.es_manual = 0

            if not row.codigo_dato:
                frappe.throw("Cada linea debe tener codigo de dato.", title="Dato Invalido")
            if row.codigo_dato in seen:
                frappe.throw(f"El dato estadistico con codigo {row.codigo_dato} esta duplicado.", title="Codigo Duplicado")
            seen.add(row.codigo_dato)
