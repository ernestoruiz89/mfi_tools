import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

from mfi_tools.mfi_tools.services.mapeo import aplicar_mapeo_paquete
from mfi_tools.mfi_tools.utils.nota_eeff import get_package_note_rows
from mfi_tools.mfi_tools.utils.word_export import build_paquete_eeff_word_content, export_paquete_eeff_to_word

FORMULA_SPLIT_RE = re.compile(r"[\n,;]+")


class PaqueteEEFF(Document):
    @property
    def cliente(self):
        val = self.__dict__.get("cliente")
        if not val and hasattr(self, "_data") and isinstance(self._data, dict):
            val = self._data.get("cliente")
        return val or getattr(self, "company", None)

    @cliente.setter
    def cliente(self, value):
        self.__dict__["cliente"] = value

    def get_entity_display(self):
        company = cstr(getattr(self, "company", "") or "").strip()
        if company:
            company_name = frappe.db.get_value("Company", company, "company_name")
            return cstr(company_name or company).strip()
        cliente = cstr(self.__dict__.get("cliente") or (self._data.get("cliente") if hasattr(self, "_data") and isinstance(self._data, dict) else "") or "").strip()
        if cliente:
            customer_name = frappe.db.get_value("Customer", cliente, "customer_name")
            return cstr(customer_name or cliente).strip()
        return ""

    def autoname(self):
        self._sync_names()
        self._validar_paquete_unico()
        if self.nombre_paquete:
            self.name = self.nombre_paquete

    def validate(self):
        self._sync_names()
        self._validar_paquete_unico()
        self._sync_linked_datos_estadisticos()
        self._normalizar_datos_estadisticos()
        self._calcular_datos_formula()
        self._sync_totals()

    def _validar_paquete_unico(self):
        if self.is_new() and self.nombre_paquete:
            if frappe.db.exists("Paquete EEFF", self.nombre_paquete):
                frappe.throw(
                    _("Ya existe un Paquete EEFF para {0} correspondiente a {1} {2}.").format(
                        self.company or "", self.mes or "", self.anio or ""
                    ),
                    title=_("Paquete Duplicado"),
                )

    def _sync_names(self):
        company = cstr(self.company or "").strip()
        mes = cstr(self.mes or "").strip()
        anio = cint(self.anio or 0)
        if company and mes and anio:
            self.periodo_nombre = f"{company}-{mes}-{anio}"
            self.nombre_paquete = f"EEFF - {company} - {mes} {anio}"

    def _sync_totals(self):
        if not self.name:
            self.total_estados = 0
            self.total_notas = 0
            self.total_datos_estadisticos = len(self.get("datos_estadisticos") or [])
            return
        self.total_estados = frappe.db.count("Estado Financiero EEFF", {"paquete_eeff": self.name})
        self.total_notas = frappe.db.count("Nota EEFF", {"paquete_eeff": self.name})
        self.total_datos_estadisticos = len(self.get("datos_estadisticos") or [])

    def _normalizar_datos_estadisticos(self):
        seen = set()
        for idx, row in enumerate(self.get("datos_estadisticos") or [], start=1):
            row.orden = cint(row.orden or idx)
            row.codigo_dato = cstr(row.codigo_dato or frappe.scrub(row.descripcion or f"dato_{idx}")).strip().upper()
            row.descripcion = cstr(row.descripcion or row.codigo_dato or f"Dato {idx}").strip()
            row.categoria = cstr(row.categoria or "").strip()
            row.unidad_medida = cstr(row.unidad_medida or "").strip()
            row.formula_datos = _normalize_formula_expression(row.formula_datos)
            row.no_imprimir = cint(row.no_imprimir or 0)
            row.origen_dato = cstr(row.origen_dato or "Manual").strip() or "Manual"

            if row.formula_datos and row.origen_dato != "Formula":
                row.origen_dato = "Formula"

            if row.codigo_dato in seen:
                frappe.throw(
                    _("El dato estadistico con codigo {0} esta duplicado.").format(row.codigo_dato),
                    title=_("Codigo Duplicado"),
                )
            seen.add(row.codigo_dato)

    def _sync_linked_datos_estadisticos(self):
        actual_name = cstr(getattr(self, "datos_estadisticos_actual_eeff", "") or "").strip()
        if not actual_name:
            return

        merged_rows = {}

        def absorb(source_name):
            if not source_name or not frappe.db.exists("Datos Estadisticos EEFF", source_name):
                return
            source_doc = frappe.get_doc("Datos Estadisticos EEFF", source_name)
            for idx, row in enumerate(source_doc.get("lineas") or [], start=1):
                code = cstr(getattr(row, "codigo_dato", "") or frappe.scrub(getattr(row, "descripcion", "") or f"dato_{idx}")).strip().upper()
                if not code:
                    continue
                target = merged_rows.setdefault(
                    code,
                    {
                        "codigo_dato": code,
                        "descripcion": cstr(getattr(row, "descripcion", "") or code).strip(),
                        "categoria": cstr(getattr(row, "categoria", "") or "").strip(),
                        "unidad_medida": cstr(getattr(row, "unidad_medida", "") or "").strip(),
                        "orden": cint(getattr(row, "orden", idx) or idx),                        "formula_datos": cstr(getattr(row, "formula_datos", "") or "").strip(),
                        "no_imprimir": cint(getattr(row, "no_imprimir", 0) or 0),
                        "valor_actual": 0,
                        "origen_dato": cstr(getattr(row, "origen_dato", "Manual") or "Manual").strip() or "Manual",
                        "comentario": cstr(getattr(row, "comentario", "") or "").strip(),
                    },
                )

                if not target.get("descripcion"):
                    target["descripcion"] = cstr(getattr(row, "descripcion", "") or code).strip()
                if not target.get("categoria"):
                    target["categoria"] = cstr(getattr(row, "categoria", "") or "").strip()
                if not target.get("unidad_medida"):
                    target["unidad_medida"] = cstr(getattr(row, "unidad_medida", "") or "").strip()
                if not target.get("formula_datos"):
                    target["formula_datos"] = cstr(getattr(row, "formula_datos", "") or "").strip()
                if not target.get("comentario"):
                    target["comentario"] = cstr(getattr(row, "comentario", "") or "").strip()

                target["valor_actual"] = flt(getattr(row, "valor_actual", 0) or 0)

        absorb(actual_name)

        self.set("datos_estadisticos", [])
        for row in sorted(merged_rows.values(), key=lambda item: (cint(item.get("orden", 0)), cstr(item.get("codigo_dato", "")))):
            self.append("datos_estadisticos", row)

    def _calcular_datos_formula(self):
        rows = list(self.get("datos_estadisticos") or [])
        row_map = {cstr(row.codigo_dato or "").strip().upper(): row for row in rows if cstr(row.codigo_dato or "").strip()}

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
            stack = stack or set()
            if key in stack:
                frappe.throw(_("Se detecto una referencia circular en formulas de datos estadisticos."), title=_("Formula Invalida"))

            if getattr(row, 'origen_dato', 'Manual') == 'Manual':
                value = flt(getattr(row, fieldname, 0))
            elif getattr(row, "origen_dato", "Manual") == "Formula" and cstr(row.formula_datos or "").strip():
                value = 0.0
                next_stack = set(stack)
                next_stack.add(key)
                for sign, ref_code in parse_formula(row.formula_datos):
                    value += sign * flt(get_value(ref_code, fieldname, next_stack))
                setattr(row, fieldname, value)
                row.origen_dato = "Formula"
            else:
                value = flt(getattr(row, fieldname, 0))

            cache[key] = value
            return value

        for row in rows:
            if getattr(row, "origen_dato", "Manual") == "Formula" and cstr(row.formula_datos or "").strip():
                code = cstr(row.codigo_dato or "").strip().upper()
                if not code:
                    continue
                get_value(code, "valor_actual", set())

    def get_datos_estadisticos_comparativos_map(self):
        cache_key = "_stats_comparative_map_cache"
        cached = getattr(self, cache_key, None)
        if cached is not None:
            return cached

        comparative_name = cstr(getattr(self, "datos_estadisticos_comparativo_eeff", "") or "").strip()
        output = {}
        if comparative_name and frappe.db.exists("Datos Estadisticos EEFF", comparative_name):
            comparative_doc = frappe.get_doc("Datos Estadisticos EEFF", comparative_name)
            for idx, row in enumerate(comparative_doc.get("lineas") or [], start=1):
                code = cstr(getattr(row, "codigo_dato", "") or frappe.scrub(getattr(row, "descripcion", "") or f"dato_{idx}")).strip().upper()
                if not code:
                    continue
                output[code] = output.get(code, 0.0) + flt(getattr(row, "valor_actual", 0) or 0)

        setattr(self, cache_key, output)
        return output

    def tiene_comparativo(self):
        return bool(cstr(getattr(self, "balanza_comparativa_eeff", "") or "").strip())

    def excluir_lineas_sin_movimientos(self):
        return bool(cint(getattr(self, "excluir_lineas_sin_movimientos", 0)))

    def get_column_labels(self):
        mes = cstr(self.mes or "").strip() or _("Actual")
        anio = cint(self.anio or 0)
        if anio:
            return {
                "actual": f"{mes} {anio}",
                "comparativo": f"{mes} {anio - 1}" if self.tiene_comparativo() else "",
            }
        return {
            "actual": mes,
            "comparativo": _("Comparativo") if self.tiene_comparativo() else "",
        }

    def get_currency_context(self):
        cache_key = "_currency_context_cache"
        cached = getattr(self, cache_key, None)
        if cached is not None:
            return cached

        currency = cstr(getattr(self, "moneda", "") or "").strip().upper()
        symbol = ""
        if currency and frappe.db.exists("Currency", currency):
            symbol = cstr(frappe.db.get_value("Currency", currency, "symbol") or "").strip()

        if not symbol:
            symbol = "$"

        output = {
            "currency": currency,
            "symbol": symbol,
        }
        setattr(self, cache_key, output)
        return output


@frappe.whitelist()
def ejecutar_mapeo(paquete_name):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))
    
    # Asegurarnos que el paquete este guardado para que sincronice los datos estadisticos mas recientes
    doc = frappe.get_doc("Paquete EEFF", paquete_name)
    doc.save(ignore_permissions=True)
    
    return aplicar_mapeo_paquete(paquete_name)


@frappe.whitelist()
def exportar_paquete_word(paquete_name):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))
    return export_paquete_eeff_to_word(paquete_name)


@frappe.whitelist()
def descargar_paquete_word(paquete_name):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete indicado no existe."), title=_("Paquete Invalido"))

    file_name, content = build_paquete_eeff_word_content(paquete_name)
    frappe.local.response.filename = file_name
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"
    frappe.local.response.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _normalize_formula_expression(expression):
    expr = cstr(expression or "").strip().upper()
    if not expr:
        return ""

    if any(token in expr for token in ("\n", ",", ";")):
        parts = [cstr(item).strip() for item in re.split(r"[\n,;]+", expr) if cstr(item).strip()]
        return ", ".join(parts)

    tokens = re.findall(r"[+-]?\s*[A-Z][A-Z0-9_]*", expr)
    if not tokens:
        return expr
    return ", ".join(item.replace(" ", "") for item in tokens)


def _delete_package_estados(package_name):
    estados = frappe.get_all("Estado Financiero EEFF", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=500)
    for estado_name in estados:
        frappe.delete_doc("Estado Financiero EEFF", estado_name, ignore_permissions=True, force=1)


def _delete_package_notas(package_name):
    secciones = frappe.get_all(
        "Seccion Nota EEFF",
        filters={"paquete_eeff": package_name},
        pluck="name",
        limit_page_length=1000,
    )
    for seccion_name in secciones:
        frappe.delete_doc("Seccion Nota EEFF", seccion_name, ignore_permissions=True, force=1)

    notas = frappe.get_all("Nota EEFF", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=1000)
    for nota_name in notas:
        frappe.delete_doc("Nota EEFF", nota_name, ignore_permissions=True, force=1)


def _delete_package_factsheets(package_name):
    factsheets = frappe.get_all("Factsheet", filters={"paquete_eeff": package_name}, pluck="name", limit_page_length=500)
    for fs_name in factsheets:
        frappe.delete_doc("Factsheet", fs_name, ignore_permissions=True, force=1)


def _clear_package_datos_estadisticos(package_name):
    package_doc = frappe.get_doc("Paquete EEFF", package_name)
    package_doc.set("datos_estadisticos", [])
    package_doc.save(ignore_permissions=True)


@frappe.whitelist()
def copiar_eeff_y_notas_desde_paquete(paquete_name, paquete_fuente, limpiar_existentes=0, limpiar_notas=None):
    if not frappe.db.exists("Paquete EEFF", paquete_name):
        frappe.throw(_("El paquete destino no existe."), title=_("Paquete Invalido"))
    if not frappe.db.exists("Paquete EEFF", paquete_fuente):
        frappe.throw(_("El paquete fuente no existe."), title=_("Paquete Invalido"))
    if paquete_name == paquete_fuente:
        frappe.throw(_("Debes seleccionar un paquete fuente distinto al destino."), title=_("Paquete Invalido"))

    destino = frappe.get_doc("Paquete EEFF", paquete_name)
    fuente = frappe.get_doc("Paquete EEFF", paquete_fuente)
    if cstr(destino.company or "").strip() and cstr(fuente.company or "").strip() and destino.company != fuente.company:
        frappe.throw(_("Solo puedes copiar EEFF y notas entre paquetes de la misma compania."), title=_("Compania Inconsistente"))

    limpiar = cint(limpiar_existentes) or cint(limpiar_notas or 0)
    if limpiar:
        _delete_package_estados(paquete_name)
        _delete_package_notas(paquete_name)
        _delete_package_factsheets(paquete_name)

    # 1. Copiar Estados Financieros
    estados_fuente = frappe.get_all(
        "Estado Financiero EEFF",
        filters={"paquete_eeff": paquete_fuente},
        pluck="name",
        order_by="orden_presentacion asc, creation asc",
        limit_page_length=500,
    )

    created_estados = []
    for state_name in estados_fuente:
        source_estado = frappe.get_doc("Estado Financiero EEFF", state_name)
        if not limpiar:
            existing_estados = frappe.get_all(
                "Estado Financiero EEFF",
                filters={
                    "paquete_eeff": paquete_name,
                    "codigo_estado": source_estado.codigo_estado,
                },
                pluck="name",
                limit_page_length=10,
            )
            for existing_estado in existing_estados:
                frappe.delete_doc("Estado Financiero EEFF", existing_estado, ignore_permissions=True, force=1)

        new_estado = frappe.copy_doc(source_estado, ignore_no_copy=False)
        new_estado.name = None
        new_estado.nombre_del_estado = None
        new_estado.paquete_eeff = paquete_name
        new_estado.estado_aprobacion = "Borrador"
        new_estado.insert(ignore_permissions=True)
        created_estados.append(new_estado.name)

    # 2. Copiar Notas EEFF
    notas_fuente = get_package_note_rows(paquete_fuente, fields=[], limit_page_length=1000)

    created_notas = []
    for row in notas_fuente:
        source_note = frappe.get_doc("Nota EEFF", row.name)
        if not limpiar:
            existing_notes = frappe.get_all(
                "Nota EEFF",
                filters={
                    "paquete_eeff": paquete_name,
                    "numero_nota": source_note.numero_nota,
                    "sub_nota": source_note.sub_nota or "",
                },
                pluck="name",
                limit_page_length=10,
            )
            for existing_note in existing_notes:
                frappe.delete_doc("Nota EEFF", existing_note, ignore_permissions=True, force=1)

        new_note = frappe.copy_doc(source_note, ignore_no_copy=False)
        new_note.name = None
        new_note.nombre_nota = None
        new_note.paquete_eeff = paquete_name
        new_note.estado_aprobacion = "Borrador"
        new_note.insert(ignore_permissions=True)

        if cstr(getattr(source_note, "estructura_nota", "Simple") or "Simple").strip() == "Compleja":
            source_sections = frappe.get_all(
                "Seccion Nota EEFF",
                filters={"nota_eeff": source_note.name},
                fields=["name"],
                order_by="orden asc, creation asc",
                limit_page_length=500,
            )
            for section_row in source_sections:
                source_section = frappe.get_doc("Seccion Nota EEFF", section_row.name)
                new_section = frappe.copy_doc(source_section, ignore_no_copy=False)
                new_section.name = None
                new_section.nombre_seccion = None
                new_section.paquete_eeff = paquete_name
                new_section.nota_eeff = new_note.name
                new_section.insert(ignore_permissions=True)

        created_notas.append(new_note.name)

    # 3. Copiar Factsheets (si existen)
    factsheets_fuente = frappe.get_all(
        "Factsheet",
        filters={"paquete_eeff": paquete_fuente},
        pluck="name",
        order_by="numero_factsheet asc, codigo_factsheet asc",
        limit_page_length=500,
    )
    created_factsheets = []
    for fs_name in factsheets_fuente:
        source_fs = frappe.get_doc("Factsheet", fs_name)
        if not limpiar:
            existing_fs = frappe.get_all(
                "Factsheet",
                filters={
                    "paquete_eeff": paquete_name,
                    "codigo_factsheet": source_fs.codigo_factsheet,
                },
                pluck="name",
                limit_page_length=10,
            )
            for existing_item in existing_fs:
                frappe.delete_doc("Factsheet", existing_item, ignore_permissions=True, force=1)

        new_fs = frappe.copy_doc(source_fs, ignore_no_copy=False)
        new_fs.name = None
        new_fs.nombre_factsheet = None
        new_fs.paquete_eeff = paquete_name
        new_fs.insert(ignore_permissions=True)
        created_factsheets.append(new_fs.name)

    destino.save(ignore_permissions=True)
    return {
        "paquete_destino": paquete_name,
        "paquete_fuente": paquete_fuente,
        "estados_copiados": len(created_estados),
        "notas_copiadas": len(created_notas),
        "factsheets_copiados": len(created_factsheets),
        "estados": created_estados,
        "notas": created_notas,
        "factsheets": created_factsheets,
    }


@frappe.whitelist()
def copiar_notas_desde_paquete(paquete_name, paquete_fuente, limpiar_notas=0):
    return copiar_eeff_y_notas_desde_paquete(
        paquete_name, paquete_fuente, limpiar_existentes=limpiar_notas
    )


