# Copyright (c) 2026, MFI Tools and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

VAR_REGEX = re.compile(r"\b([A-Z_][A-Z0-9_]*)\b")

class Factsheet(Document):
    def autoname(self):
        self.codigo_factsheet = cstr(self.codigo_factsheet or "").strip().upper()
        base = self.codigo_factsheet or "FACTSHEET"
        self.nombre_factsheet = f"{base} - {self.paquete_eeff or frappe.generate_hash(length=6)}"
        self.name = self.nombre_factsheet

    def validate(self):
        self.codigo_factsheet = cstr(self.codigo_factsheet or "").strip().upper()
        if not self.company and self.paquete_eeff:
            self.company = frappe.db.get_value("Paquete EEFF", self.paquete_eeff, "company")
        self._normalizar_lineas()
        self._calcular_formulas()

    def _normalizar_lineas(self):
        seen = set()
        for idx, row in enumerate(self.lineas or [], start=1):
            row.codigo_linea = cstr(row.codigo_linea or f"LINEA_{idx}").strip().upper()
            row.origen_dato = cstr(row.origen_dato or "Manual").strip() or "Manual"
            if row.origen_dato == "Manual":
                row.es_manual = 1
                row.formula = ""
            elif row.origen_dato == "Mapeo":
                row.es_manual = 0
                row.formula = ""
            elif row.origen_dato == "Formula":
                row.es_manual = 0
                row.formula = cstr(row.formula or "").strip().upper()
            
            row.formato_presentacion = cstr(row.formato_presentacion or "Numero").strip()
            
            if row.codigo_linea in seen:
                frappe.throw(_("El codigo de linea {0} esta duplicado en el Factsheet.").format(row.codigo_linea))
            seen.add(row.codigo_linea)

    def _calcular_formulas(self):
        row_map = {row.codigo_linea: row for row in self.lineas or []}
        cache_act = {}
        cache_comp = {}

        MONTH_NUMBER = {
            "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4,
            "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8,
            "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12
        }
        mes_act = 1
        mes_comp = 1
        anio_act = 2026
        anio_comp = 2025
        
        if self.paquete_eeff:
            paquete = frappe.db.get_value("Paquete EEFF", self.paquete_eeff, ["mes", "anio", "balanza_comparativa_eeff"], as_dict=True)
            if paquete:
                mes_act = MONTH_NUMBER.get(paquete.get("mes"), 1)
                anio_act = paquete.get("anio") or 2026
                if paquete.get("balanza_comparativa_eeff"):
                    comp = frappe.db.get_value("Balanza Comprobacion EEFF", paquete.get("balanza_comparativa_eeff"), ["mes", "anio"], as_dict=True)
                    if comp:
                        mes_comp = MONTH_NUMBER.get(comp.get("mes"), mes_act)
                        anio_comp = comp.get("anio") or anio_act
                else:
                    mes_comp = mes_act
                    anio_comp = anio_act

        def get_value(code, fieldname, stack):
            is_comp = (fieldname == "monto_comparativo")
            cache = cache_comp if is_comp else cache_act
            
            if code in cache:
                return cache[code]
            
            row = row_map.get(code)
            if not row:
                return 0.0

            if code in stack:
                frappe.throw(_("Referencia circular detectada en la linea {0}.").format(code))
            
            if row.origen_dato in ("Manual", "Mapeo"):
                val = flt(getattr(row, fieldname, 0))
                cache[code] = val
                return val

            # Origen: Formula
            formula_str = row.formula
            if not formula_str:
                cache[code] = 0.0
                return 0.0

            next_stack = set(stack)
            next_stack.add(code)

            # Reemplazar variables en la formula
            def replacer(match):
                var_name = match.group(1)
                
                if var_name == "MES_ACTUAL": return str(mes_act)
                if var_name == "MES_COMPARATIVO": return str(mes_comp)
                if var_name == "ANIO_ACTUAL": return str(anio_act)
                if var_name == "ANIO_COMPARATIVO": return str(anio_comp)

                # Soportar prefijos ej: COMP_EMPLEADOS
                target_field = fieldname
                target_var = var_name
                
                # Para simplificar la sintaxis si alguien pone ACT_EMPLEADOS
                if var_name.startswith("COMP_"):
                    target_field = "monto_comparativo"
                    target_var = var_name[5:]
                elif var_name.startswith("ACT_"):
                    target_field = "monto_actual"
                    target_var = var_name[4:]
                
                val = get_value(target_var, target_field, next_stack)
                return str(val)

            expr = VAR_REGEX.sub(replacer, formula_str)
            try:
                # safe evaluation of math expression
                result = eval(expr, {"__builtins__": None}, {})
                val = flt(result)
            except ZeroDivisionError:
                val = 0.0
            except Exception as e:
                frappe.throw(_("Error evaluando formula '{0}' en linea {1}: {2}").format(formula_str, code, str(e)))

            setattr(row, fieldname, val)
            cache[code] = val
            return val

        # Evaluar todas las lineas
        for row in self.lineas or []:
            if row.origen_dato == "Formula":
                get_value(row.codigo_linea, "monto_actual", set())
                get_value(row.codigo_linea, "monto_comparativo", set())

    def on_trash(self):
        # Validar si tiene reglas de mapeo asociadas
        active_rules = frappe.get_all(
            "Regla Mapeo Contable EEFF",
            filters={
                "company": self.company,
                "activo": 1,
                "destino_tipo": "Linea Factsheet"
            },
            fields=["name"]
        )
        if active_rules:
            # We can't easily know if they map to THIS factsheet since it's resolved dynamically,
            # but we can warn. For now, since rules are company-wide and rely on codes, we don't strictly prevent trash.
            pass
