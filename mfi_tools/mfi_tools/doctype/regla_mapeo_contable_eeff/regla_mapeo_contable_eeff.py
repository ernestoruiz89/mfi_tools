import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.utils.nota_eeff import build_note_identifier

BALANCE_FIELDS = ("codigo_cuenta", "descripcion_cuenta")
FIGURE_VALUE_PERIODS = (
    "Actual",
    "Comparativo",
    "Saldo Anterior Actual",
    "Movimiento Mes Actual",
    "Saldo Anterior Comparativo",
    "Movimiento Mes Comparativo",
)
SECTION_CELL_PERIODS = (
    "Actual",
    "Comparativo",
    "Base Actual",
    "Base Comparativo",
    "Saldo Anterior Actual",
    "Movimiento Mes Actual",
    "Saldo Anterior Comparativo",
    "Movimiento Mes Comparativo",
)


class ReglaMapeoContableEEFF(Document):
    def autoname(self):
        explicit_name = cstr(self.nombre_regla or "").strip()
        if explicit_name:
            self.nombre_regla = _build_unique_rule_name(explicit_name, current_name=self.name if not self.is_new() else None)
            self.name = self.nombre_regla
            return
        base_name = self._build_name_base()
        self.nombre_regla = _build_unique_rule_name(base_name, current_name=self.name if not self.is_new() else None)
        self.name = self.nombre_regla

    def validate(self):
        self._sync_display_name()
        self._normalizar_cuentas()
        self._validar_fuente()
        self._validar_destino()

    def on_update(self):
        self._rename_if_needed()

    def _build_name_base(self):
        destino = cstr(self.destino_tipo or "Regla").strip().replace(" ", "-")
        return f"{destino}-{self.company or frappe.generate_hash(length=6)}-{cint(self.orden or 0):03d}"

    def _sync_display_name(self):
        if self.is_new():
            return
        current = cstr(self.name or "").strip()
        if current and cstr(self.nombre_regla or "").strip() != current:
            self.nombre_regla = current

    def _rename_if_needed(self):
        if self.is_new() or getattr(self.flags, "in_auto_rename", False):
            return

        current_name = cstr(self.name or "").strip()
        if not current_name:
            return

        desired_base = self._build_name_base()
        if _name_matches_base(current_name, desired_base):
            if cstr(self.nombre_regla or "").strip() != current_name:
                frappe.db.set_value(self.doctype, current_name, "nombre_regla", current_name, update_modified=False)
            return

        new_name = _build_unique_rule_name(desired_base, current_name=current_name)
        if not new_name or new_name == current_name:
            return

        self.flags.in_auto_rename = True
        try:
            rename_doc(self.doctype, current_name, new_name, force=True, merge=False, ignore_permissions=True)
            _update_last_rule_references(current_name, new_name)
            frappe.db.set_value(self.doctype, new_name, "nombre_regla", new_name, update_modified=False)
            self.name = new_name
            self.nombre_regla = new_name
        finally:
            self.flags.in_auto_rename = False

    def _validar_fuente(self):
        self.fuente_tipo = cstr(self.fuente_tipo or "Balanza").strip()
        if self.fuente_tipo not in ("Balanza", "Dato Estadistico"):
            frappe.throw(_("La fuente de la regla no es valida."), title=_("Fuente Invalida"))

    def _normalizar_destinos_estables(self):
        self.destino_codigo_estado = cstr(getattr(self, "destino_codigo_estado", "") or "").strip().upper()
        self.destino_codigo_factsheet = cstr(getattr(self, "destino_codigo_factsheet", "") or "").strip().upper()
        self.destino_codigo_linea = _extract_code_token(getattr(self, "destino_codigo_linea", ""))
        self.destino_numero_nota = cstr(getattr(self, "destino_numero_nota", "") or "").strip().upper()
        self.destino_codigo_seccion = _extract_code_token(getattr(self, "destino_codigo_seccion", ""))
        self.destino_codigo_tabla = _extract_code_token(getattr(self, "destino_codigo_tabla", ""))
        self.destino_codigo_cifra = _extract_code_token(getattr(self, "destino_codigo_cifra", ""))
        self.usar_periodos_especiales_cifra = cint(getattr(self, "usar_periodos_especiales_cifra", 0) or 0)
        self.destino_periodo_cifra_actual = cstr(getattr(self, "destino_periodo_cifra_actual", "") or "Actual").strip()
        if self.destino_periodo_cifra_actual not in FIGURE_VALUE_PERIODS:
            self.destino_periodo_cifra_actual = "Actual"
        self.destino_periodo_cifra_comparativo = cstr(
            getattr(self, "destino_periodo_cifra_comparativo", "") or "Comparativo"
        ).strip()
        if self.destino_periodo_cifra_comparativo not in FIGURE_VALUE_PERIODS:
            self.destino_periodo_cifra_comparativo = "Comparativo"
        self.destino_seccion_id = cstr(getattr(self, "destino_seccion_id", "") or "").strip().upper()
        self.destino_codigo_fila = _extract_code_token(getattr(self, "destino_codigo_fila", ""))
        self.destino_codigo_columna = _extract_code_token(getattr(self, "destino_codigo_columna", ""))
        self.destino_periodo_celda = cstr(getattr(self, "destino_periodo_celda", "") or "Actual").strip()
        if self.destino_periodo_celda not in SECTION_CELL_PERIODS:
            self.destino_periodo_celda = "Actual"
        destino_tipo = cstr(getattr(self, "destino_tipo", "") or "").strip()
        if destino_tipo != "Cifra Nota" or self.fuente_tipo != "Balanza":
            self.usar_periodos_especiales_cifra = 0
        if not self.usar_periodos_especiales_cifra:
            self.destino_periodo_cifra_actual = "Actual"
            self.destino_periodo_cifra_comparativo = "Comparativo"

    def _normalizar_cuentas(self):
        if not self.cuentas:
            frappe.throw(_("La regla debe tener al menos una cuenta en el child table."), title=_("Cuentas Requeridas"))
        for row in self.cuentas:
            row.cuenta = cstr(row.cuenta or "").strip()
            row.campo_balanza = cstr(getattr(row, "campo_balanza", "codigo_cuenta") or "codigo_cuenta").strip()
            if row.campo_balanza not in BALANCE_FIELDS:
                row.campo_balanza = "codigo_cuenta"
            row.operacion = cstr(row.operacion or "+").strip()
            row.centro_costo = cstr(getattr(row, "centro_costo", "") or "").strip()
            if row.operacion not in ("+", "-"):
                row.operacion = "+"
            row.porcentaje = flt(row.porcentaje or 100)
            if not row.cuenta:
                frappe.throw(_("Hay una fila de cuentas sin valor de origen."), title=_("Cuenta Requerida"))

    def _validar_destino(self):
        self._normalizar_destinos_estables()
        destino = cstr(self.destino_tipo or "").strip()
        if destino == "Linea Estado":
            if not cstr(self.destino_codigo_estado or "").strip() or not cstr(self.destino_codigo_linea or "").strip():
                frappe.throw(_("Para Linea Estado debes indicar estado y codigo de linea destino."), title=_("Destino Incompleto"))
        elif destino == "Cifra Nota":
            if not cstr(self.destino_numero_nota or "").strip() or not cstr(self.destino_codigo_cifra or "").strip():
                frappe.throw(_("Para Cifra Nota debes indicar numero de nota y codigo de cifra destino."), title=_("Destino Incompleto"))
        elif destino == "Celda Seccion Nota":
            if (
                not cstr(self.destino_numero_nota or "").strip()
                or not cstr(self.destino_codigo_seccion or "").strip()
                or not cstr(self.destino_codigo_tabla or "").strip()
                or not cstr(self.destino_codigo_fila or "").strip()
                or not cstr(self.destino_codigo_columna or "").strip()
            ):
                frappe.throw(
                    _("Para Celda Seccion Nota debes indicar nota, seccion, tabla, fila y columna destino."),
                    title=_("Destino Incompleto"),
                )
        elif destino == "Linea Factsheet":
            if not cstr(self.destino_codigo_factsheet or "").strip() or not cstr(self.destino_codigo_linea or "").strip():
                frappe.throw(_("Para Linea Factsheet debes indicar codigo de factsheet y codigo de linea destino."), title=_("Destino Incompleto"))
        else:
            frappe.throw(_("El destino de la regla no es valido."), title=_("Destino Invalido"))


def _extract_code_token(value):
    token = cstr(value or "").strip()
    if not token:
        return ""
    if " - " in token:
        token = token.split(" - ", 1)[0].strip()
    return token.upper()


def _build_unique_rule_name(base_name, current_name=None):
    base = cstr(base_name or "").strip()
    if not base:
        base = frappe.generate_hash(length=8)

    candidate = base
    sequence = 1
    while frappe.db.exists("Regla Mapeo Contable EEFF", candidate) and cstr(candidate) != cstr(current_name or ""):
        candidate = f"{base}-{sequence:03d}"
        sequence += 1

    return candidate


def _name_matches_base(current_name, base_name):
    current = cstr(current_name or "").strip()
    base = cstr(base_name or "").strip()
    if not current or not base:
        return False
    if current == base:
        return True
    return bool(current.startswith(f"{base}-") and current[len(base) + 1 :].isdigit())


def _update_last_rule_references(old_name, new_name):
    old_value = cstr(old_name or "").strip()
    new_value = cstr(new_name or "").strip()
    if not old_value or not new_value or old_value == new_value:
        return

    frappe.db.sql(
        """
        update `tabCelda Seccion Nota EEFF`
        set ultima_regla_mapeo = %(new_name)s
        where ifnull(ultima_regla_mapeo, '') = %(old_name)s
        """,
        {"old_name": old_value, "new_name": new_value},
    )
