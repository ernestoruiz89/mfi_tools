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
