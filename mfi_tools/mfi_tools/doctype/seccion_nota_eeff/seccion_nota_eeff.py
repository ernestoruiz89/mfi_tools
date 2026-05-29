import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

from mfi_tools.mfi_tools.utils.nota_tablas import (
    DEFAULT_COLUMN_CODE,
    TABLE_ALIGNMENTS,
    TABLE_COLUMN_TYPES,
    TABLE_ROW_TYPES,
    build_complex_section_tables,
    normalize_column_code,
    normalize_row_code,
    normalize_table_code,
    parse_formula_tokens,
)


class SeccionNotaEEFF(Document):
    def autoname(self):
        if self.nombre_seccion:
            self.name = self.nombre_seccion
            return
        base = cstr(self.titulo_seccion or self.codigo_seccion or "Seccion").strip().upper()
        self.nombre_seccion = f"{base} - {self.nota_eeff or frappe.generate_hash(length=6)}"
        self.name = self.nombre_seccion

    def validate(self):
        self._sync_links()
        self._normalizar_meta()
        self._normalizar_columnas()
        self._normalizar_filas()
        self._normalizar_celdas()
        self._asegurar_estructura_tabular()
        self._validar_formulas_tabulares()
        self._calcular_tablas()
        self._ajustar_tipo_seccion_por_contenido()
        self._validar_codigo_unico()
        self._sync_totals()

    def get_render_tables(self):
        return build_complex_section_tables(self)

    def render_contenido_narrativo(self, extra_context=None):
        template = cstr(getattr(self, "contenido_narrativo", "") or "").strip()
        if not template:
            return ""

        context = {
            "doc": self,
            "section_doc": self,
            "seccion_doc": self,
        }
        if self.nota_eeff and frappe.db.exists("Nota EEFF", self.nota_eeff):
            note_doc = frappe.get_doc("Nota EEFF", self.nota_eeff)
            context["note_doc"] = note_doc
            context["nota_doc"] = note_doc
            if cstr(getattr(note_doc, "paquete_eeff", "") or "").strip() and frappe.db.exists("Paquete EEFF", note_doc.paquete_eeff):
                context["package"] = frappe.get_doc("Paquete EEFF", note_doc.paquete_eeff)
        if isinstance(extra_context, dict):
            context.update(extra_context)

        try:
            return frappe.render_template(template, context)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                _("Error renderizando contenido narrativo de Seccion Nota EEFF {0}").format(self.name),
            )
            return template

    def after_insert(self):
        self._sync_note_summary()

    def on_update(self):
        self._sync_note_summary()

    def on_trash(self):
        active_rules = frappe.get_all(
            "Regla Mapeo Contable EEFF",
            filters={
                "paquete_eeff": self.paquete_eeff,
                "activo": 1,
                "destino_tipo": "Celda Seccion Nota",
                "seccion_nota_eeff": self.name,
            },
            fields=["name", "destino_tipo", "destino_codigo_tabla", "destino_codigo_fila", "destino_codigo_columna"],
            order_by="modified desc",
            limit_page_length=20,
        )
        if active_rules:
            refs = ", ".join(
                f"{row.name} -> {cstr(row.destino_codigo_tabla or '-').strip() or '-'}"
                for row in active_rules[:5]
            )
            if len(active_rules) > 5:
                refs = f"{refs}, ..."
            frappe.throw(
                _(
                    "No puedes eliminar la seccion {0} porque tiene reglas de mapeo activas vinculadas. "
                    "Desactiva, elimina o actualiza esas reglas primero. Reglas detectadas: {1}"
                ).format(self.name, refs),
                title=_("Seccion Referenciada"),
            )

        if self.nota_eeff and frappe.db.exists("Nota EEFF", self.nota_eeff):
            current = frappe.db.count("Seccion Nota EEFF", {"nota_eeff": self.nota_eeff})
            frappe.db.set_value(
                "Nota EEFF",
                self.nota_eeff,
                "total_secciones_complejas",
                max(current - 1, 0),
                update_modified=False,
            )

    def _sync_links(self):
        if not self.nota_eeff or not frappe.db.exists("Nota EEFF", self.nota_eeff):
            frappe.throw(_("La seccion debe estar vinculada a una Nota EEFF valida."), title=_("Nota Requerida"))

        note_values = frappe.db.get_value("Nota EEFF", self.nota_eeff, ["paquete_eeff", "estructura_nota"], as_dict=True) or {}
        note_package = cstr(note_values.get("paquete_eeff") or "").strip()
        if not note_package:
            frappe.throw(_("La nota vinculada no tiene paquete asociado."), title=_("Nota Invalida"))

        self.paquete_eeff = note_package
        if cstr(note_values.get("estructura_nota") or "Simple").strip() != "Compleja":
            frappe.db.set_value("Nota EEFF", self.nota_eeff, "estructura_nota", "Compleja", update_modified=False)

    def _normalizar_meta(self):
        self.codigo_seccion = cstr(self.codigo_seccion or frappe.scrub(self.titulo_seccion or "seccion")).strip().upper()
        self.tipo_seccion = cstr(self.tipo_seccion or "Narrativa").strip()
        self.titulo_seccion = cstr(self.titulo_seccion or self.codigo_seccion or "Seccion").strip()
        self.orden = cint(self.orden or 0)
        self.mostrar_titulo = cint(self.mostrar_titulo if self.mostrar_titulo is not None else 1)
        self.observaciones = cstr(self.observaciones or "").strip()

        if self.tipo_seccion not in ("Narrativa", "Tabla", "Mixta"):
            self.tipo_seccion = "Narrativa"

    def _normalizar_columnas(self):
        seen = set()
        for idx, row in enumerate(self.columnas_tabulares or [], start=1):
            row.codigo_tabla = normalize_table_code(getattr(row, "codigo_tabla", None))
            row.codigo_columna = normalize_column_code(getattr(row, "codigo_columna", None), f"COL_{idx:02d}")
            row.etiqueta = cstr(getattr(row, "etiqueta", "") or row.codigo_columna or f"Columna {idx}").strip()
            row.tipo_dato = cstr(getattr(row, "tipo_dato", "Numero") or "Numero").strip()
            row.alineacion = cstr(getattr(row, "alineacion", "Right") or "Right").strip()
            row.grupo_columna = cstr(getattr(row, "grupo_columna", "") or "").strip()
            row.redondear_entero = cint(getattr(row, "redondear_entero", 0) or 0)
            row.calculo_automatico = cint(getattr(row, "calculo_automatico", 0) or 0)
            row.formula_columnas = cstr(getattr(row, "formula_columnas", "") or "").strip().upper()
            row.es_total = cint(getattr(row, "es_total", 0) or 0)

            if row.tipo_dato not in TABLE_COLUMN_TYPES:
                row.tipo_dato = "Numero"
            if row.alineacion not in TABLE_ALIGNMENTS:
                row.alineacion = "Right" if row.tipo_dato != "Texto" else "Left"
            if row.formula_columnas and not row.calculo_automatico:
                row.calculo_automatico = 1
            if row.calculo_automatico and row.tipo_dato == "Texto":
                frappe.throw(
                    _("La columna {0} no puede calcularse automaticamente porque su tipo es Texto.").format(row.codigo_columna),
                    title=_("Columna Invalida"),
                )

            signature = (row.codigo_tabla, row.codigo_columna)
            if signature in seen:
                frappe.throw(
                    _("La columna {0} esta duplicada dentro de la tabla {1}.").format(row.codigo_columna, row.codigo_tabla),
                    title=_("Codigo Duplicado"),
                )
            seen.add(signature)

    def _normalizar_filas(self):
        seen = set()
        for idx, row in enumerate(self.filas_tabulares or [], start=1):
            row.codigo_tabla = normalize_table_code(getattr(row, "codigo_tabla", None))
            row.codigo_fila = normalize_row_code(getattr(row, "codigo_fila", None), f"FILA_{idx:02d}")
            row.descripcion = cstr(getattr(row, "descripcion", "") or row.codigo_fila or f"Fila {idx}").strip()
            row.nivel = max(cint(getattr(row, "nivel", 1) or 1), 1)
            row.tipo_fila = cstr(getattr(row, "tipo_fila", "Detalle") or "Detalle").strip()
            row.calculo_automatico = cint(getattr(row, "calculo_automatico", 0) or 0)
            row.formula_filas = cstr(getattr(row, "formula_filas", "") or "").strip().upper()
            row.negrita = cint(getattr(row, "negrita", 0) or 0)
            row.subrayado = cint(getattr(row, "subrayado", 0) or 0)

            if row.tipo_fila not in TABLE_ROW_TYPES:
                row.tipo_fila = "Detalle"
            if row.tipo_fila == "Titulo":
                row.calculo_automatico = 0
                row.formula_filas = ""
                row.negrita = 1
            elif row.formula_filas and not row.calculo_automatico:
                row.calculo_automatico = 1
            elif row.tipo_fila in ("Subtotal", "Total") and not row.negrita:
                row.negrita = 1

            signature = (row.codigo_tabla, row.codigo_fila)
            if signature in seen:
                frappe.throw(
                    _("La fila {0} esta duplicada dentro de la tabla {1}.").format(row.codigo_fila, row.codigo_tabla),
                    title=_("Codigo Duplicado"),
                )
            seen.add(signature)

    def _normalizar_celdas(self):
        seen = set()
        for idx, row in enumerate(self.celdas_tabulares or [], start=1):
            row.codigo_tabla = normalize_table_code(getattr(row, "codigo_tabla", None))
            row.codigo_fila = normalize_row_code(getattr(row, "codigo_fila", None), f"FILA_{idx:02d}")
            row.codigo_columna = normalize_column_code(getattr(row, "codigo_columna", None), DEFAULT_COLUMN_CODE)
            row.valor_numero = None if getattr(row, "valor_numero", None) in ("", None) else flt(getattr(row, "valor_numero", 0) or 0)
            row.valor_texto = cstr(getattr(row, "valor_texto", "") or "").strip()
            row.formato_numero = cstr(getattr(row, "formato_numero", "") or "").strip()
            row.redondear_entero = cint(getattr(row, "redondear_entero", 0) or 0)
            row.es_manual = cint(getattr(row, "es_manual", 0) or 0)
            row.origen_dato = cstr(getattr(row, "origen_dato", "Manual") or "Manual").strip() or "Manual"
            row.ultima_regla_mapeo = cstr(getattr(row, "ultima_regla_mapeo", "") or "").strip()
            row.comentario = cstr(getattr(row, "comentario", "") or "").strip()

            if row.formato_numero and row.formato_numero not in TABLE_COLUMN_TYPES:
                row.formato_numero = ""

            signature = (row.codigo_tabla, row.codigo_fila, row.codigo_columna)
            if signature in seen:
                frappe.throw(
                    _("La celda {0}/{1}/{2} esta duplicada dentro de la seccion.").format(*signature),
                    title=_("Celda Duplicada"),
                )
            seen.add(signature)

    def _asegurar_estructura_tabular(self):
        row_map = {(row.codigo_tabla, row.codigo_fila): row for row in self.filas_tabulares or []}
        column_map = {(row.codigo_tabla, row.codigo_columna): row for row in self.columnas_tabulares or []}
        cell_map = {(row.codigo_tabla, row.codigo_fila, row.codigo_columna): row for row in self.celdas_tabulares or []}

        for idx, cell in enumerate(self.celdas_tabulares or [], start=1):
            row_key = (cell.codigo_tabla, cell.codigo_fila)
            col_key = (cell.codigo_tabla, cell.codigo_columna)
            if row_key not in row_map:
                self.append(
                    "filas_tabulares",
                    {
                        "codigo_tabla": cell.codigo_tabla,
                        "codigo_fila": cell.codigo_fila,
                        "descripcion": cell.codigo_fila,
                        "nivel": 1,
                        "tipo_fila": "Detalle",
                    },
                )
                row_map[row_key] = self.filas_tabulares[-1]
            if col_key not in column_map:
                self.append(
                    "columnas_tabulares",
                    {
                        "codigo_tabla": cell.codigo_tabla,
                        "codigo_columna": cell.codigo_columna,
                        "etiqueta": cell.codigo_columna,
                        "tipo_dato": cstr(cell.formato_numero or "Numero") or "Numero",
                        "alineacion": "Right",
                        "redondear_entero": cint(cell.redondear_entero or 0),
                    },
                )
                column_map[col_key] = self.columnas_tabulares[-1]

        tables = {}
        for row in self.filas_tabulares or []:
            tables.setdefault(row.codigo_tabla, {"rows": [], "columns": []})
            tables[row.codigo_tabla]["rows"].append(row)
        for row in self.columnas_tabulares or []:
            tables.setdefault(row.codigo_tabla, {"rows": [], "columns": []})
            tables[row.codigo_tabla]["columns"].append(row)

        for table_code, meta in tables.items():
            rows = sorted(meta["rows"], key=lambda row: (cint(row.idx or 0), row.codigo_fila))
            columns = sorted(meta["columns"], key=lambda row: (cint(row.idx or 0), row.codigo_columna))
            if not rows or not columns:
                continue
            for row in rows:
                for column in columns:
                    signature = (table_code, row.codigo_fila, column.codigo_columna)
                    if signature in cell_map:
                        cell = cell_map[signature]
                        if not cstr(getattr(cell, "formato_numero", "") or "").strip():
                            cell.formato_numero = cstr(column.tipo_dato or "Numero")
                        if not cint(getattr(cell, "redondear_entero", 0) or 0) and cint(column.redondear_entero or 0):
                            cell.redondear_entero = cint(column.redondear_entero or 0)
                        continue
                    self.append(
                        "celdas_tabulares",
                        {
                            "codigo_tabla": table_code,
                            "codigo_fila": row.codigo_fila,
                            "codigo_columna": column.codigo_columna,
                            "valor_numero": None,
                            "valor_texto": "",
                            "formato_numero": cstr(column.tipo_dato or "Numero"),
                            "redondear_entero": cint(column.redondear_entero or 0),
                            "es_manual": 0,
                            "origen_dato": "Manual",
                        },
                    )
                    cell_map[signature] = self.celdas_tabulares[-1]

    def _validar_formulas_tabulares(self):
        row_map = {(row.codigo_tabla, row.codigo_fila): row for row in self.filas_tabulares or []}
        column_map = {(row.codigo_tabla, row.codigo_columna): row for row in self.columnas_tabulares or []}

        for row in self.filas_tabulares or []:
            formula = cstr(getattr(row, "formula_filas", "") or "").strip().upper()
            if not formula:
                continue
            for _, ref_code in parse_formula_tokens(formula):
                if (row.codigo_tabla, ref_code) not in row_map:
                    frappe.throw(
                        _("La fila {0} referencia la fila inexistente {1} en la tabla {2}.").format(
                            row.codigo_fila, ref_code, row.codigo_tabla
                        ),
                        title=_("Formula Invalida"),
                    )

        for row in self.columnas_tabulares or []:
            formula = cstr(getattr(row, "formula_columnas", "") or "").strip().upper()
            if not formula:
                continue
            for _, ref_code in parse_formula_tokens(formula):
                if (row.codigo_tabla, ref_code) not in column_map:
                    frappe.throw(
                        _("La columna {0} referencia la columna inexistente {1} en la tabla {2}.").format(
                            row.codigo_columna, ref_code, row.codigo_tabla
                        ),
                        title=_("Formula Invalida"),
                    )

    def _calcular_tablas(self):
        row_map = {(row.codigo_tabla, row.codigo_fila): row for row in self.filas_tabulares or []}
        column_map = {(row.codigo_tabla, row.codigo_columna): row for row in self.columnas_tabulares or []}
        cell_map = {(row.codigo_tabla, row.codigo_fila, row.codigo_columna): row for row in self.celdas_tabulares or []}
        table_rows = {}
        table_columns = {}

        for row in self.filas_tabulares or []:
            table_rows.setdefault(row.codigo_tabla, []).append(row.codigo_fila)
        for row in self.columnas_tabulares or []:
            table_columns.setdefault(row.codigo_tabla, []).append(row.codigo_columna)

        def get_or_create_cell(table_code, row_code, column_code):
            key = (table_code, row_code, column_code)
            if key in cell_map:
                return cell_map[key]
            self.append(
                "celdas_tabulares",
                {
                    "codigo_tabla": table_code,
                    "codigo_fila": row_code,
                    "codigo_columna": column_code,
                    "valor_numero": None,
                    "valor_texto": "",
                    "formato_numero": cstr(getattr(column_map.get((table_code, column_code)), "tipo_dato", "Numero") or "Numero"),
                    "redondear_entero": cint(getattr(column_map.get((table_code, column_code)), "redondear_entero", 0) or 0),
                    "es_manual": 0,
                    "origen_dato": "Manual",
                },
            )
            cell_map[key] = self.celdas_tabulares[-1]
            return cell_map[key]

        cache = {}

        def resolve_cell(table_code, row_code, column_code, stack=None):
            key = (table_code, row_code, column_code)
            if key in cache:
                return cache[key]

            row_def = row_map.get((table_code, row_code))
            column_def = column_map.get((table_code, column_code))
            cell = get_or_create_cell(table_code, row_code, column_code)

            if row_def and cstr(getattr(row_def, "tipo_fila", "Detalle") or "Detalle").strip() == "Titulo":
                cell.valor_numero = None
                cell.valor_texto = ""
                cell.origen_dato = "Manual"
                cache[key] = None
                return None

            stack = stack or set()
            if key in stack:
                frappe.throw(_("Se detecto una referencia circular en formulas tabulares."), title=_("Formula Invalida"))

            next_stack = set(stack)
            next_stack.add(key)

            column_formula = cstr(getattr(column_def, "formula_columnas", "") or "").strip().upper() if column_def else ""
            row_formula = cstr(getattr(row_def, "formula_filas", "") or "").strip().upper() if row_def else ""

            if column_def and cint(getattr(column_def, "calculo_automatico", 0) or 0) and column_formula:
                total = 0.0
                for sign, ref_code in parse_formula_tokens(column_formula):
                    total += sign * flt(resolve_cell(table_code, row_code, ref_code, next_stack) or 0)
                cell.valor_numero = total
                cell.valor_texto = ""
                cell.formato_numero = cstr(cell.formato_numero or column_def.tipo_dato or "Numero")
                cell.redondear_entero = cint(getattr(cell, "redondear_entero", 0) or getattr(column_def, "redondear_entero", 0) or 0)
                cell.es_manual = 0
                cell.origen_dato = "Formula"
                cache[key] = total
                return total

            if row_def and cint(getattr(row_def, "calculo_automatico", 0) or 0) and row_formula:
                total = 0.0
                for sign, ref_code in parse_formula_tokens(row_formula):
                    total += sign * flt(resolve_cell(table_code, ref_code, column_code, next_stack) or 0)
                cell.valor_numero = total
                cell.valor_texto = ""
                if column_def and not cstr(cell.formato_numero or "").strip():
                    cell.formato_numero = cstr(column_def.tipo_dato or "Numero")
                    cell.redondear_entero = cint(getattr(cell, "redondear_entero", 0) or getattr(column_def, "redondear_entero", 0) or 0)
                cell.es_manual = 0
                cell.origen_dato = "Formula"
                cache[key] = total
                return total

            if column_def and not cstr(getattr(cell, "formato_numero", "") or "").strip():
                cell.formato_numero = cstr(getattr(column_def, "tipo_dato", "Numero") or "Numero")
                cell.redondear_entero = cint(getattr(cell, "redondear_entero", 0) or getattr(column_def, "redondear_entero", 0) or 0)

            value_text = cstr(getattr(cell, "valor_texto", "") or "").strip()
            if value_text:
                cache[key] = None
                return None

            value = None if getattr(cell, "valor_numero", None) in (None, "") else flt(getattr(cell, "valor_numero", 0) or 0)
            cache[key] = value
            return value

        for table_code, row_codes in table_rows.items():
            for column_code in table_columns.get(table_code, []):
                for row_code in row_codes:
                    resolve_cell(table_code, row_code, column_code, set())

    def _ajustar_tipo_seccion_por_contenido(self):
        has_table = bool((self.columnas_tabulares or []) or (self.filas_tabulares or []) or (self.celdas_tabulares or []))
        narrative_text = re.sub(r"<[^>]+>", "", cstr(self.contenido_narrativo or ""))
        has_narrative = bool(cstr(narrative_text or "").strip())

        if has_table and has_narrative:
            self.tipo_seccion = "Mixta"
        elif has_table:
            self.tipo_seccion = "Tabla"
        elif has_narrative:
            self.tipo_seccion = "Narrativa"

    def _validar_codigo_unico(self):
        filters = {
            "nota_eeff": self.nota_eeff,
            "codigo_seccion": self.codigo_seccion,
            "name": ["!=", self.name or ""],
        }
        if frappe.db.exists("Seccion Nota EEFF", filters):
            frappe.throw(
                _("Ya existe otra seccion con codigo {0} para la nota {1}.").format(self.codigo_seccion, self.nota_eeff),
                title=_("Codigo Duplicado"),
            )

    def _sync_totals(self):
        self.total_columnas = len(self.columnas_tabulares or [])
        self.total_filas = len(self.filas_tabulares or [])
        self.total_celdas = len(self.celdas_tabulares or [])

    def _sync_note_summary(self):
        if not self.nota_eeff or not frappe.db.exists("Nota EEFF", self.nota_eeff):
            return
        total = frappe.db.count("Seccion Nota EEFF", {"nota_eeff": self.nota_eeff})
        frappe.db.set_value("Nota EEFF", self.nota_eeff, "total_secciones_complejas", total, update_modified=False)
