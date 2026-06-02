import re
import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.utils.nota_eeff import (
    build_note_autoname,
    normalize_note_number,
    normalize_sub_note,
    normalize_sub_note_key,
)
from mfi_tools.mfi_tools.utils.nota_tablas import TABLE_COLUMN_TYPES
from mfi_tools.mfi_tools.utils.estado_line_format import format_accounting_number

FORMULA_SPLIT_RE = re.compile(r"[\n,;]+")
FIGURE_FORMATS = tuple(TABLE_COLUMN_TYPES)


def _clear_title_figure_amounts(row):
    row.monto_actual = None
    row.monto_comparativo = None
    row.valor_texto_actual = ""
    row.valor_texto_comparativo = ""


def _clear_blank_figure_amounts(row):
    row.monto_actual = None
    row.monto_comparativo = None
    row.valor_texto_actual = ""
    row.valor_texto_comparativo = ""


class NotaEEFF(Document):
    def autoname(self):
        if self.nombre_nota:
            self.name = self.nombre_nota
            return
        self.nombre_nota = build_note_autoname(self.numero_nota, self.sub_nota, self.paquete_eeff)
        self.name = self.nombre_nota

    def validate(self):
        self.numero_nota = normalize_note_number(self.numero_nota)
        self.sub_nota = normalize_sub_note(self.sub_nota)
        if not self.numero_nota:
            frappe.throw(_("Debes indicar un numero de nota."), title=_("Numero Requerido"))
        self.tamano_letra_impresion = self.get_print_font_size()
        self.ancho_tabla_impresion = self.get_print_table_width()
        self.alineacion_tabla_impresion = self.get_print_table_alignment()
        self.estructura_nota = cstr(self.estructura_nota or "Simple").strip() or "Simple"
        if self.estructura_nota not in ("Simple", "Compleja"):
            self.estructura_nota = "Simple"
        self._validar_unicidad_numero()
        self._normalizar_cifras()
        self._calcular_cifras_formula()
        self._sync_complex_sections_summary()

    def on_trash(self):
        company = ""
        if self.paquete_eeff and frappe.db.exists("Paquete EEFF", self.paquete_eeff):
            company = cstr(frappe.db.get_value("Paquete EEFF", self.paquete_eeff, "company") or "").strip()
        nota_identifier = build_note_identifier(self.numero_nota, self.sub_nota) if self.numero_nota else ""
        active_rules = frappe.get_all(
            "Regla Mapeo Contable EEFF",
            filters={
                "company": company,
                "activo": 1,
                "destino_tipo": ["in", ["Cifra Nota", "Celda Seccion Nota"]],
                "destino_numero_nota": nota_identifier,
            },
            fields=[
                "name",
                "destino_tipo",
                "destino_codigo_tabla",
                "destino_codigo_cifra",
                "destino_codigo_fila",
                "destino_codigo_columna",
            ],
            order_by="modified desc",
            limit_page_length=20,
        )
        if active_rules:
            refs = ", ".join(
                f"{row.name} -> "
                f"{cstr(row.destino_codigo_cifra or row.destino_codigo_tabla or row.destino_codigo_fila or '-').strip() or '-'}"
                for row in active_rules[:5]
            )
            if len(active_rules) > 5:
                refs = f"{refs}, ..."
            frappe.throw(
                _(
                    "No puedes eliminar la nota {0} porque tiene reglas de mapeo activas vinculadas. "
                    "Desactiva, elimina o actualiza esas reglas primero. Reglas detectadas: {1}"
                ).format(self.name, refs),
                title=_("Nota Referenciada"),
            )

        self._delete_linked_complex_sections()

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

    def get_print_heading(self):
        title = cstr(getattr(self, "titulo", "") or "").strip() or _("Sin titulo")
        sub_nota = cstr(getattr(self, "sub_nota", "") or "").strip()
        numero_nota = cstr(getattr(self, "numero_nota", "") or "").strip() or "-"
        if sub_nota:
            return f"({sub_nota}) - {title}"
        return f"Nota {numero_nota}. {title}"

    def get_figure_number_format(self, row):
        fmt = cstr(getattr(row, "formato_numero", "") or "").strip().title()
        return fmt if fmt in FIGURE_FORMATS else "Moneda"

    def is_text_figure(self, row):
        if cint(getattr(row, "es_linea_blanco", 0)) or cint(getattr(row, "es_titulo", 0)):
            return False
        return self.get_figure_number_format(row) == "Texto"

    def format_figure_amount(self, value, format_type="Moneda", decimals=2):
        fmt = cstr(format_type or "").strip().title()
        if fmt not in FIGURE_FORMATS:
            fmt = "Moneda"

        if value in (None, ""):
            return "-"
        if fmt == "Texto":
            return cstr(value)

        return format_accounting_number(value, fmt, trim_plain=(fmt == "Numero"), none_as="-", decimals=decimals)

    def format_figure_value(self, row, fieldname):
        if not row:
            return "-"
        if cint(getattr(row, "es_linea_blanco", 0)) or cint(getattr(row, "es_titulo", 0)):
            return ""
        fmt = self.get_figure_number_format(row)
        if fmt == "Texto":
            text_field = "valor_texto_actual" if fieldname == "monto_actual" else "valor_texto_comparativo"
            text_value = cstr(getattr(row, text_field, "") or "").strip()
            if text_value:
                return text_value
            raw_value = getattr(row, fieldname, None)
            return cstr(raw_value) if raw_value not in (None, "") else "-"
        decimals = 0 if cint(getattr(row, "redondear_entero", 0)) else 2
        return self.format_figure_amount(getattr(row, fieldname, None), fmt, decimals=decimals)

    def get_figures_total_format(self, rows=None):
        rows = rows or (self.cifras_nota or [])
        formats = set()
        for row in rows:
            if cint(getattr(row, "no_imprimir", 0)):
                continue
            if cint(getattr(row, "es_linea_blanco", 0)) or cint(getattr(row, "es_titulo", 0)):
                continue
            if cint(getattr(row, "es_total", 0)) or cint(getattr(row, "es_subtotal", 0)):
                continue
            fmt = self.get_figure_number_format(row)
            if fmt == "Texto":
                continue
            formats.add(fmt)
        if not formats:
            return "Moneda"
        if len(formats) == 1:
            return next(iter(formats))
        return "Numero"

    def render_contenido_narrativo(self, extra_context=None):
        return self._render_template_field(
            "contenido_narrativo",
            _("Error renderizando contenido narrativo de Nota EEFF {0}").format(self.name),
            extra_context=extra_context,
        )

    def render_observaciones(self, extra_context=None):
        return self._render_template_field(
            "observaciones",
            _("Error renderizando observaciones de Nota EEFF {0}").format(self.name),
            extra_context=extra_context,
        )

    def _render_template_field(self, fieldname, log_title, extra_context=None):
        template = cstr(getattr(self, fieldname, "") or "").strip()
        if not template:
            return ""

        context = {
            "doc": self,
            "note_doc": self,
            "nota_doc": self,
        }
        if self.paquete_eeff and frappe.db.exists("Paquete EEFF", self.paquete_eeff):
            context["package"] = frappe.get_doc("Paquete EEFF", self.paquete_eeff)
        if isinstance(extra_context, dict):
            context.update(extra_context)

        try:
            return frappe.render_template(template, context)
        except Exception:
            frappe.log_error(frappe.get_traceback(), log_title)
            return template

    def _normalizar_cifras(self):
        seen = set()
        for idx, row in enumerate(self.cifras_nota or [], start=1):
            row.codigo_cifra = cstr(row.codigo_cifra or frappe.scrub(row.concepto or f"cifra_{idx}")).strip().upper()
            row.nivel = max(cint(getattr(row, "nivel", 1) or 1), 1)
            row.formula_cifras = cstr(row.formula_cifras or "").strip().upper()
            row.formato_numero = self.get_figure_number_format(row)
            row.valor_texto_actual = cstr(getattr(row, "valor_texto_actual", "") or "").strip()
            row.valor_texto_comparativo = cstr(getattr(row, "valor_texto_comparativo", "") or "").strip()
            row.es_manual = cint(row.es_manual or 0)
            row.calculo_automatico = cint(row.calculo_automatico or 0)
            row.no_imprimir = cint(row.no_imprimir or 0)
            row.negrita = cint(row.negrita or 0)
            row.subrayado = cint(row.subrayado or 0)
            row.es_titulo = cint(getattr(row, "es_titulo", 0) or 0)
            row.es_linea_blanco = cint(getattr(row, "es_linea_blanco", 0) or 0)
            row.es_total = cint(row.es_total or 0)
            row.es_subtotal = cint(row.es_subtotal or 0)
            row.origen_dato = cstr(row.origen_dato or "Manual").strip() or "Manual"
            if row.formato_numero != "Texto":
                row.monto_actual = None if row.monto_actual in ("", None) else flt(row.monto_actual)
                row.monto_comparativo = None if row.monto_comparativo in ("", None) else flt(row.monto_comparativo)

            if row.formato_numero == "Texto":
                row.es_manual = 1
                row.calculo_automatico = 0
                row.formula_cifras = ""
            elif row.formula_cifras and not row.calculo_automatico:
                row.calculo_automatico = 1

            if row.es_linea_blanco:
                row.concepto = ""
                row.formato_numero = "Numero"
                row.es_titulo = 0
                row.es_total = 0
                row.es_subtotal = 0
                row.negrita = 0
                row.subrayado = 0
                row.calculo_automatico = 0
                row.es_manual = 0
                row.formula_cifras = ""
                row.origen_dato = "Manual"
                _clear_blank_figure_amounts(row)
                if not row.codigo_cifra:
                    row.codigo_cifra = f"BLANK_LINE_{idx}"
            elif row.es_titulo:
                row.es_total = 0
                row.es_subtotal = 0
                row.calculo_automatico = 0
                row.formula_cifras = ""
                row.origen_dato = "Manual"
                _clear_title_figure_amounts(row)

            if row.codigo_cifra in seen:
                frappe.throw(_("La cifra con codigo {0} esta duplicada.").format(row.codigo_cifra), title=_("Codigo Duplicado"))
            seen.add(row.codigo_cifra)

        self.total_cifras = len(self.cifras_nota or [])

    def _validar_unicidad_numero(self):
        existing_notes = frappe.get_all(
            "Nota EEFF",
            filters={
                "paquete_eeff": self.paquete_eeff,
                "numero_nota": self.numero_nota,
                "name": ["!=", self.name or ""],
            },
            fields=["name", "sub_nota"],
            limit_page_length=50,
        )
        current_sub_key = normalize_sub_note_key(self.sub_nota)
        if any(normalize_sub_note_key(getattr(row, "sub_nota", "")) == current_sub_key for row in existing_notes):
            frappe.throw(
                _("Ya existe otra nota con identificador {0}{1} dentro del paquete {2}.").format(
                    self.numero_nota,
                    f" ({self.sub_nota})" if self.sub_nota else "",
                    self.paquete_eeff or "-",
                ),
                title=_("Nota Duplicada"),
            )

    def _calcular_cifras_formula(self):
        row_map = {cstr(row.codigo_cifra).strip().upper(): row for row in self.cifras_nota or []}

        def parse_formula(expression):
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
                    refs.append((sign, token))
            return refs

        cache = {}

        def get_value(code, fieldname, stack=None):
            key = (code, fieldname)
            if key in cache:
                return cache[key]
            row = row_map.get(code)
            if not row:
                return 0.0
            if cint(getattr(row, "es_linea_blanco", 0)):
                _clear_blank_figure_amounts(row)
                cache[key] = 0.0
                return 0.0
            if cint(getattr(row, "es_titulo", 0)):
                _clear_title_figure_amounts(row)
                cache[key] = 0.0
                return 0.0
            if self.is_text_figure(row):
                cache[key] = 0.0
                return 0.0
            stack = stack or set()
            if key in stack:
                frappe.throw(_("Se detecto una referencia circular en formulas de cifras."), title=_("Formula Invalida"))

            if cint(row.es_manual):
                value = flt(getattr(row, fieldname, 0))
            elif cint(row.calculo_automatico) and cstr(row.formula_cifras or "").strip():
                from mfi_tools.mfi_tools.services.formula_engine import has_data_functions
                if has_data_functions(row.formula_cifras):
                    value = flt(getattr(row, fieldname, 0))
                else:
                    value = 0.0
                    next_stack = set(stack)
                    next_stack.add(key)
                    for sign, ref_code in parse_formula(row.formula_cifras):
                        value += sign * flt(get_value(ref_code, fieldname, next_stack))
                setattr(row, fieldname, value)
                row.origen_dato = "Formula"
            else:
                value = flt(getattr(row, fieldname, 0))

            cache[key] = value
            return value

        for row in self.cifras_nota or []:
            if cint(getattr(row, "es_linea_blanco", 0)):
                _clear_blank_figure_amounts(row)
                continue
            if cint(getattr(row, "es_titulo", 0)):
                _clear_title_figure_amounts(row)
                continue
            if self.is_text_figure(row):
                continue
            if cint(row.calculo_automatico) and cstr(row.formula_cifras or "").strip():
                code = cstr(row.codigo_cifra or "").strip().upper()
                if not code:
                    continue
                get_value(code, "monto_actual", set())
                get_value(code, "monto_comparativo", set())

    def _sync_complex_sections_summary(self):
        if not self.name:
            self.total_secciones_complejas = 0
            return
        self.total_secciones_complejas = frappe.db.count("Seccion Nota EEFF", {"nota_eeff": self.name})

    def _delete_linked_complex_sections(self):
        section_names = frappe.get_all(
            "Seccion Nota EEFF",
            filters={"nota_eeff": self.name},
            pluck="name",
            limit_page_length=500,
        )
        for section_name in section_names:
            frappe.delete_doc("Seccion Nota EEFF", section_name, ignore_permissions=True, force=1)
