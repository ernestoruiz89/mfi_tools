import re
import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, formatdate

from mfi_tools.mfi_tools.utils.estado_line_format import (
    format_estado_line_value,
    is_text_estado_line,
    normalize_estado_line_format,
)
from mfi_tools.mfi_tools.utils.customer import get_customer_display

from mfi_tools.mfi_tools.utils.nota_tablas import (
    DEFAULT_COLUMN_CODE,
    TABLE_ALIGNMENTS,
    TABLE_COLUMN_TYPES,
    TABLE_ROW_TYPES,
    normalize_column_code,
    normalize_row_code,
    normalize_table_code,
    parse_formula_tokens as parse_formula_tokens_tabular,
)


FORMULA_SPLIT_RE = re.compile(r"[\n,;]+")
FORMULA_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
FORMULA_FIELD_MAP = {
    "ACT": "monto_actual",
    "MONTO_ACTUAL": "monto_actual",
    "COMP": "monto_comparativo",
    "MONTO_COMPARATIVO": "monto_comparativo",
    "BASE_ACT": "monto_base_actual",
    "MONTO_BASE_ACTUAL": "monto_base_actual",
    "BASE_COMP": "monto_base_comparativo",
    "MONTO_BASE_COMPARATIVO": "monto_base_comparativo",
}
FORMULA_BASE_FIELD_BY_TARGET = {
    "monto_actual": "monto_base_actual",
    "monto_comparativo": "monto_base_comparativo",
    "monto_base_actual": "monto_base_actual",
    "monto_base_comparativo": "monto_base_comparativo",
}


def _clear_title_amounts(row):
    row.monto_actual = None
    row.monto_comparativo = None
    row.monto_base_actual = None
    row.monto_base_comparativo = None


def _clear_blank_line_amounts(row):
    row.monto_actual = None
    row.monto_comparativo = None
    row.monto_base_actual = None
    row.monto_base_comparativo = None
    row.valor_texto = ""


class EstadoFinancieroEEFF(Document):
    def autoname(self):
        self.codigo_estado = cstr(self.codigo_estado or "").strip().upper()
        base = self.codigo_estado or cstr(self.titulo or self.tipo_estado or "ESTADO_EEFF").strip().upper()
        self.nombre_del_estado = f"{base} - {self.paquete_eeff or frappe.generate_hash(length=6)}"
        self.name = self.nombre_del_estado

    def validate(self):
        self.estructura_estado = cstr(getattr(self, "estructura_estado", "Simple") or "Simple").strip()
        self.codigo_estado = cstr(self.codigo_estado or "").strip().upper()
        self.subtitulo = cstr(getattr(self, "subtitulo", "") or "").strip()
        self.tamano_letra_impresion = self.get_print_font_size()
        self.ancho_tabla_impresion = self.get_print_table_width()
        self.alineacion_tabla_impresion = self.get_print_table_alignment()
        if self.estructura_estado == "Compleja":
            self._normalizar_columnas()
            self._normalizar_filas()
            self._normalizar_celdas()
            self._asegurar_estructura_tabular()
            self._validar_formulas_tabulares()
            self._calcular_tablas()
            self._sync_totals()
        else:
            self._normalizar_lineas()
            self._calcular_lineas_formula()

    def format_line_value(self, row, fieldname):
        return format_estado_line_value(row, fieldname)

    def is_text_line(self, row):
        if cint(getattr(row, "es_linea_blanco", 0)):
            return False
        return is_text_estado_line(row)

    def get_print_font_size(self):
        value = flt(getattr(self, "tamano_letra_impresion", 0) or 12)
        if not math.isfinite(value):
            value = 12
        value = max(8.0, min(value, 18.0))
        return int(value) if abs(value - int(value)) < 0.001 else round(value, 2)

    def get_print_table_width(self):
        value = cstr(getattr(self, "ancho_tabla_impresion", "") or "").strip()
        if not value:
            return "100%"
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"%{2,}", "%", value)
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            value = f"{value}%"
        if re.fullmatch(r"\d+(?:\.\d+)?(?:%|px|cm|mm|in|pt|pc|rem|em|vw)", value, flags=re.IGNORECASE):
            return value
        return "100%"

    def get_print_table_alignment(self):
        value = cstr(getattr(self, "alineacion_tabla_impresion", "") or "").strip()
        if value not in ("Izquierda", "Centro", "Derecha"):
            return "Centro"
        return value

    def get_print_table_alignment_css(self):
        alignment = self.get_print_table_alignment()
        if alignment == "Izquierda":
            return "left"
        if alignment == "Derecha":
            return "right"
        return "center"

    def get_print_header(self):
        package = frappe.get_doc("Paquete EEFF", self.paquete_eeff) if self.paquete_eeff else None
        customer_name = get_customer_display(package.cliente) if package and package.cliente else cstr(getattr(package, "cliente", "") or "").strip()
        target_date = self._resolve_package_cutoff_date(package) if package else ""
        header = {
            "cliente": customer_name or "-",
            "titulo": cstr(self.titulo or self.tipo_estado or "").strip() or "-",
            "periodo": "",
            "subtitulo": cstr(getattr(self, "subtitulo", "") or "").strip(),
        }
        if target_date:
            header["periodo"] = self._format_header_period(target_date)
        return header

    def _resolve_package_cutoff_date(self, package):
        balance_name = cstr(getattr(package, "balanza_comprobacion_eeff", "") or "").strip()
        if balance_name and frappe.db.exists("Balanza Comprobacion EEFF", balance_name):
            return cstr(frappe.db.get_value("Balanza Comprobacion EEFF", balance_name, "fecha_corte") or "").strip()
        return ""

    def _format_header_period(self, target_date):
        pretty_date = formatdate(target_date, "dd 'de' MMMM 'del' YYYY")
        if cstr(self.tipo_estado or "").strip() == "Estado de Situacion Financiera":
            return f"Al {pretty_date}"
        return f"Del 01 de Enero al {pretty_date}"

    def on_trash(self):
        active_rules = frappe.get_all(
            "Regla Mapeo Contable EEFF",
            filters={
                "paquete_eeff": self.paquete_eeff,
                "activo": 1,
                "destino_tipo": "Linea Estado",
                "estado_financiero_eeff": self.name,
            },
            fields=["name", "destino_codigo_linea"],
            order_by="modified desc",
            limit_page_length=20,
        )
        if not active_rules:
            return

        refs = ", ".join(
            f"{row.name} -> {cstr(row.destino_codigo_linea or '-').strip() or '-'}"
            for row in active_rules[:5]
        )
        if len(active_rules) > 5:
            refs = f"{refs}, ..."
        frappe.throw(
            _(
                "No puedes eliminar el estado {0} porque tiene reglas de mapeo activas vinculadas. "
                "Desactiva, elimina o actualiza esas reglas primero. Reglas detectadas: {1}"
            ).format(self.name, refs),
            title=_("Estado Referenciado"),
        )

    def _normalizar_lineas(self):
        seen = set()
        for idx, row in enumerate(self.lineas or [], start=1):
            row.nivel = cint(row.nivel or 1)
            row.codigo_linea = cstr(row.codigo_linea or frappe.scrub(row.descripcion or f"linea_{idx}")).strip().upper()
            row.formula_lineas = cstr(row.formula_lineas or "").strip().upper()
            row.modo_formula = cstr(getattr(row, "modo_formula", "") or "").strip()
            if row.modo_formula not in ("Vertical", "Multicolumna"):
                row.modo_formula = "Vertical"
            row.origen_dato = cstr(row.origen_dato or "Manual").strip() or "Manual"
            row.no_imprimir = cint(row.no_imprimir or 0)
            row.negrita = cint(row.negrita or 0)
            row.subrayado = cint(row.subrayado or 0)
            row.formato_presentacion = normalize_estado_line_format(getattr(row, "formato_presentacion", "Numero"))
            row.valor_texto = cstr(getattr(row, "valor_texto", "") or "").strip()
            row.es_linea_blanco = cint(getattr(row, "es_linea_blanco", 0) or 0)
            row.es_titulo = cint(getattr(row, "es_titulo", 0) or 0)
            row.es_total = cint(row.es_total or 0)
            row.es_subtotal = cint(row.es_subtotal or 0)

            if row.formula_lineas and row.origen_dato != 'Formula':
                row.origen_dato = 'Formula'

            if row.es_linea_blanco:
                row.descripcion = ""
                row.formato_presentacion = "Numero"
                row.es_titulo = 0
                row.es_total = 0
                row.es_subtotal = 0
                row.negrita = 0
                row.subrayado = 0
                row.formula_lineas = ""
                row.modo_formula = "Vertical"
                row.origen_dato = "Manual"
                _clear_blank_line_amounts(row)
                if not row.codigo_linea:
                    row.codigo_linea = f"BLANK_LINE_{idx}"
            elif row.es_titulo:
                _clear_title_amounts(row)
                row.modo_formula = "Vertical"
                row.origen_dato = "Manual"

            if row.codigo_linea in seen:
                frappe.throw(_("La linea con codigo {0} esta duplicada.").format(row.codigo_linea), title=_("Codigo Duplicado"))
            seen.add(row.codigo_linea)

        self.total_lineas = len(self.lineas or [])

    def _calcular_lineas_formula(self):
        row_map = {cstr(row.codigo_linea).strip().upper(): row for row in self.lineas or []}

        def parse_vertical_formula(expression):
            refs = []
            for token in FORMULA_SPLIT_RE.split(cstr(expression or "").strip().upper()):
                token = cstr(token or "").strip().upper()
                if not token:
                    continue
                sign = 1
                if token[0] in "+-":
                    sign = -1 if token[0] == "-" else 1
                    token = token[1:].strip()
                if token:
                    if not FORMULA_CODE_RE.fullmatch(token):
                        frappe.throw(
                            _("Formula invalida. El codigo de linea {0} no es valido.").format(token),
                            title=_("Formula Invalida"),
                        )
                    refs.append((sign, token))
            return refs

        def parse_multicol_formula(expression):
            refs = []
            for token in FORMULA_SPLIT_RE.split(cstr(expression or "").strip().upper()):
                token = cstr(token or "").strip().upper()
                if not token:
                    continue
                sign = 1
                if token[0] in "+-":
                    sign = -1 if token[0] == "-" else 1
                    token = token[1:].strip()
                if not token:
                    continue

                prefix = "SELF"
                code = token
                if "." in token:
                    prefix, code = token.split(".", 1)
                    prefix = cstr(prefix or "").strip().upper()
                    code = cstr(code or "").strip().upper()

                if not code or not FORMULA_CODE_RE.fullmatch(code):
                    frappe.throw(
                        _("Formula invalida: {0}. Usa referencias de codigo validas.").format(token),
                        title=_("Formula Invalida"),
                    )

                if prefix not in ("SELF", "BASE") and prefix not in FORMULA_FIELD_MAP:
                    frappe.throw(
                        _(
                            "Formula invalida: {0}. Usa CODIGO, BASE.CODIGO, "
                            "ACT.CODIGO, COMP.CODIGO, BASE_ACT.CODIGO o BASE_COMP.CODIGO."
                        ).format(
                            token
                        ),
                        title=_("Formula Invalida"),
                    )
                refs.append((sign, code, prefix))
            return refs

        cache = {}

        def get_value(code, fieldname, stack=None):
            key = (code, fieldname)
            if key in cache:
                return cache[key]
            row = row_map.get(code)
            if not row:
                return 0.0
            stack = stack or set()
            if key in stack:
                frappe.throw(_("Se detecto una referencia circular en formulas de lineas."), title=_("Formula Invalida"))

            if cint(getattr(row, "es_linea_blanco", 0)):
                _clear_blank_line_amounts(row)
                cache[key] = 0.0
                return 0.0

            if cint(getattr(row, "es_titulo", 0)):
                _clear_title_amounts(row)
                cache[key] = 0.0
                return 0.0

            if row.origen_dato == 'Manual':
                value = flt(getattr(row, fieldname, 0))
            elif row.origen_dato == "Formula" and cstr(row.formula_lineas or "").strip():
                from mfi_tools.mfi_tools.services.formula_engine import has_data_functions
                if has_data_functions(row.formula_lineas):
                    value = flt(getattr(row, fieldname, 0))
                else:
                    value = 0.0
                    next_stack = set(stack)
                    next_stack.add(key)
                    mode = cstr(getattr(row, "modo_formula", "") or "Vertical").strip()
                    if mode == "Multicolumna":
                        for sign, ref_code, prefix in parse_multicol_formula(row.formula_lineas):
                            if prefix == "SELF":
                                ref_field = fieldname
                            elif prefix == "BASE":
                                ref_field = FORMULA_BASE_FIELD_BY_TARGET.get(fieldname, "monto_base_actual")
                            else:
                                ref_field = FORMULA_FIELD_MAP.get(prefix)
                            if not ref_field:
                                frappe.throw(_("Formula invalida con prefijo no soportado: {0}.").format(prefix), title=_("Formula Invalida"))
                            value += sign * flt(get_value(ref_code, ref_field, next_stack))
                    else:
                        for sign, ref_code in parse_vertical_formula(row.formula_lineas):
                            value += sign * flt(get_value(ref_code, fieldname, next_stack))
                setattr(row, fieldname, value)
                row.origen_dato = "Formula"
            else:
                value = flt(getattr(row, fieldname, 0))

            cache[key] = value
            return value

        for row in self.lineas or []:
            if cint(getattr(row, "es_linea_blanco", 0)):
                _clear_blank_line_amounts(row)
                continue
            if cint(getattr(row, "es_titulo", 0)):
                _clear_title_amounts(row)
                continue
            if row.origen_dato == "Formula" and cstr(row.formula_lineas or "").strip():
                code = cstr(row.codigo_linea or "").strip().upper()
                if not code:
                    continue
                get_value(code, "monto_actual", set())
                get_value(code, "monto_comparativo", set())
                if cstr(getattr(row, "modo_formula", "") or "Vertical").strip() != "Multicolumna":
                    get_value(code, "monto_base_actual", set())
                    get_value(code, "monto_base_comparativo", set())

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
            
            row.formula_columnas = cstr(getattr(row, "formula_columnas", "") or "").strip().upper()
            row.es_total = cint(getattr(row, "es_total", 0) or 0)

            if row.tipo_dato not in TABLE_COLUMN_TYPES:
                row.tipo_dato = "Numero"
            if row.alineacion not in TABLE_ALIGNMENTS:
                row.alineacion = "Right" if row.tipo_dato != "Texto" else "Left"

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
            
            row.formula_filas = cstr(getattr(row, "formula_filas", "") or "").strip().upper()
            row.negrita = cint(getattr(row, "negrita", 0) or 0)
            row.subrayado = cint(getattr(row, "subrayado", 0) or 0)

            if row.tipo_fila not in TABLE_ROW_TYPES:
                row.tipo_fila = "Detalle"
            if row.tipo_fila == "Titulo":
                row.formula_filas = ""
                row.negrita = 1
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
            
            row.origen_dato = cstr(getattr(row, "origen_dato", "Manual") or "Manual").strip() or "Manual"
            row.ultima_regla_mapeo = cstr(getattr(row, "ultima_regla_mapeo", "") or "").strip()
            row.comentario = cstr(getattr(row, "comentario", "") or "").strip()

            if row.formato_numero and row.formato_numero not in TABLE_COLUMN_TYPES:
                row.formato_numero = ""

            signature = (row.codigo_tabla, row.codigo_fila, row.codigo_columna)
            if signature in seen:
                frappe.throw(
                    _("La celda {0}/{1}/{2} esta duplicada dentro del estado.").format(*signature),
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
            for _, ref_code in parse_formula_tokens_tabular(formula):
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
            for _, ref_code in parse_formula_tokens_tabular(formula):
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

            if getattr(cell, "origen_dato", "") == "Formula" and getattr(cell, "formula_celda", ""):
                val = None if getattr(cell, "valor_numero", None) in (None, "") else flt(getattr(cell, "valor_numero", 0) or 0)
                cache[key] = val
                return val

            if column_def and column_formula:
                total = 0.0
                for sign, ref_code in parse_formula_tokens_tabular(column_formula):
                    total += sign * flt(resolve_cell(table_code, row_code, ref_code, next_stack) or 0)
                cell.valor_numero = total
                cell.valor_texto = ""
                cell.formato_numero = cstr(cell.formato_numero or column_def.tipo_dato or "Numero")
                cell.redondear_entero = cint(getattr(cell, "redondear_entero", 0) or getattr(column_def, "redondear_entero", 0) or 0)
                cell.origen_dato = "Formula"
                cache[key] = total
                return total

            if row_def and row_formula:
                total = 0.0
                for sign, ref_code in parse_formula_tokens_tabular(row_formula):
                    total += sign * flt(resolve_cell(table_code, ref_code, column_code, next_stack) or 0)
                cell.valor_numero = total
                cell.valor_texto = ""
                if column_def and not cstr(cell.formato_numero or "").strip():
                    cell.formato_numero = cstr(column_def.tipo_dato or "Numero")
                    cell.redondear_entero = cint(getattr(cell, "redondear_entero", 0) or getattr(column_def, "redondear_entero", 0) or 0)
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

    def _sync_totals(self):
        self.total_columnas = len(self.columnas_tabulares or [])
        self.total_filas = len(self.filas_tabulares or [])
        self.total_celdas = len(self.celdas_tabulares or [])

