import calendar
import csv
import io
import re
import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt
from mfi_tools.mfi_tools.utils.customer import get_customer_display

MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

BALANCE_AMOUNT_FIELDS = (
    "debe_saldo_anterior",
    "haber_saldo_anterior",
    "debe_mes",
    "haber_mes",
    "debe_saldo",
    "haber_saldo",
)


def _normalize_header(value):
    normalized = unicodedata.normalize("NFKD", cstr(value or ""))
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", "_", ascii_value.strip().lower())
    return cleaned.strip("_")


def _normalize_csv_row(row):
    return {
        _normalize_header(key): value
        for key, value in (row or {}).items()
        if cstr(key or "").strip()
    }


def _csv_value(row, *aliases):
    for alias in aliases:
        key = _normalize_header(alias)
        if key in row and cstr(row.get(key) or "").strip():
            return row.get(key)
    return None


def _normalize_signed_balance(debe, haber):
    debe = flt(debe or 0)
    haber = flt(haber or 0)
    if debe < 0 or haber < 0:
        neto = debe - haber
        return (neto, 0.0) if neto >= 0 else (0.0, abs(neto))
    return debe, haber


def _warning_negative_debe_with_haber(idx, etiqueta, debe, haber):
    if flt(debe or 0) < 0 and flt(haber or 0) > 0:
        return _(
            "Linea {0}: {1} tiene Debe negativo y Haber con valor. Si tu origen separa Debe/Haber, carga ambos campos y evita negativos en Debe."
        ).format(idx, etiqueta)
    return None


class BalanzaComprobacionEEFF(Document):
    def autoname(self):
        self._sync_period_fields()
        if self.nombre_balanza:
            self.name = self.nombre_balanza

    def validate(self):
        self._sync_period_fields()
        self._normalizar_moneda()
        self._normalizar_tasas_cambio()
        self._normalizar_lineas()

    def _normalizar_moneda(self):
        moneda = cstr(getattr(self, "moneda", "") or "").strip().upper()
        if not moneda:
            moneda = cstr(frappe.db.get_default("currency") or frappe.defaults.get_global_default("currency") or "USD").strip().upper()

        if not moneda:
            moneda = "USD"

        if not frappe.db.exists("Currency", moneda):
            frappe.throw(
                _("La moneda {0} no existe en el catalogo de monedas.").format(moneda),
                title=_("Moneda Invalida"),
            )
        self.moneda = moneda

    def _sync_period_fields(self):
        cliente = cstr(self.cliente or "").strip()
        mes = cstr(self.mes or "").strip()
        anio = cint(self.anio or 0)
        if not cliente or not mes or not anio:
            return

        cliente_display = get_customer_display(cliente)
        periodo = f"{cliente_display or cliente}-{mes}-{anio}"
        self.periodo_nombre = periodo
        self.nombre_balanza = self.nombre_balanza or periodo

        month_num = MESES.get(mes.lower())
        if month_num:
            last_day = calendar.monthrange(anio, month_num)[1]
            self.fecha_corte = f"{anio:04d}-{month_num:02d}-{last_day:02d}"

    def _normalizar_lineas(self):
        total_debe = 0.0
        total_haber = 0.0
        advertencias = []

        for idx, row in enumerate(self.lineas or [], start=1):
            row.codigo_cuenta = cstr(row.codigo_cuenta or "").strip().upper()
            row.descripcion_cuenta = cstr(row.descripcion_cuenta or "").strip()
            row.centro_costo = cstr(getattr(row, "centro_costo", "") or "").strip()
            row.moneda = cstr(self.moneda or "").strip().upper()
            for fieldname in BALANCE_AMOUNT_FIELDS:
                setattr(row, fieldname, flt(getattr(row, fieldname, 0) or 0))
            for warning in (
                _warning_negative_debe_with_haber(
                    idx,
                    _("Saldo Anterior"),
                    row.debe_saldo_anterior,
                    row.haber_saldo_anterior,
                ),
                _warning_negative_debe_with_haber(
                    idx,
                    _("Saldo Final"),
                    row.debe_saldo,
                    row.haber_saldo,
                ),
            ):
                if warning:
                    advertencias.append(warning)

            row.debe_saldo_anterior, row.haber_saldo_anterior = _normalize_signed_balance(
                row.debe_saldo_anterior,
                row.haber_saldo_anterior,
            )
            row.saldo_anterior = flt(row.debe_saldo_anterior or 0) - flt(row.haber_saldo_anterior or 0)
            row.movimiento_del_mes = flt(row.debe_mes or 0) - flt(row.haber_mes or 0)
            row.debe_saldo, row.haber_saldo = _normalize_signed_balance(row.debe_saldo, row.haber_saldo)
            row.saldo = flt(row.debe_saldo or 0) - flt(row.haber_saldo or 0)

            if not row.descripcion_cuenta:
                frappe.throw(
                    _("La linea {0} no tiene descripcion de cuenta.").format(idx),
                    title=_("Descripcion Requerida"),
                )

            total_debe += flt(row.debe_saldo)
            total_haber += flt(row.haber_saldo)

        self.total_lineas = len(self.lineas or [])
        self.total_debe = total_debe
        self.total_haber = total_haber
        self.cuadra = 1 if abs(total_debe - total_haber) < 0.0001 else 0
        if advertencias:
            frappe.msgprint("<br>".join(advertencias), title=_("Advertencias de Carga"), indicator="orange")

    def _normalizar_tasas_cambio(self):
        seen = set()
        for idx, row in enumerate(self.get("tasas_cambio") or [], start=1):
            moneda = cstr(getattr(row, "moneda", "") or "").strip().upper()
            if not moneda:
                frappe.throw(
                    _("La linea de tasa de cambio #{0} no tiene moneda.").format(idx),
                    title=_("Moneda Requerida"),
                )
            if moneda in seen:
                frappe.throw(
                    _("La moneda {0} esta duplicada en tasas de cambio.").format(moneda),
                    title=_("Moneda Duplicada"),
                )
            seen.add(moneda)
            row.moneda = moneda

            value = flt(getattr(row, "tasa_cambio", 0) or 0)
            row.tasa_cambio = value if value > 0 else 1

    def get_tasas_cambio_map(self):
        output = {}
        for row in self.get("tasas_cambio") or []:
            moneda = cstr(getattr(row, "moneda", "") or "").strip().upper()
            if not moneda:
                continue
            output[moneda] = flt(getattr(row, "tasa_cambio", 0) or 0) or 1
        return output

    def get_tasa_cambio(self, moneda=None, fallback=1):
        tasas_map = self.get_tasas_cambio_map()
        if not tasas_map:
            return flt(fallback or 1) or 1

        moneda = cstr(moneda or "").strip().upper()
        if moneda and moneda in tasas_map:
            return flt(tasas_map.get(moneda) or 1)

        first = next(iter(tasas_map.values()), fallback)
        return flt(first or fallback or 1) or 1


def _upsert_tasa_cambio(doc, moneda, tasa_cambio):
    moneda = cstr(moneda or "").strip().upper() or "USD"
    tasa_cambio = flt(tasa_cambio or 0)
    tasa_cambio = tasa_cambio if tasa_cambio > 0 else 1

    for row in doc.get("tasas_cambio") or []:
        row_moneda = cstr(getattr(row, "moneda", "") or "").strip().upper()
        if row_moneda == moneda:
            row.moneda = moneda
            row.tasa_cambio = tasa_cambio
            return

    doc.append(
        "tasas_cambio",
        {
            "moneda": moneda,
            "tasa_cambio": tasa_cambio,
        },
    )


@frappe.whitelist()
def cargar_balanza_csv(balanza_name, csv_content, tasa_cambio=None, moneda=None):
    if not frappe.db.exists("Balanza Comprobacion EEFF", balanza_name):
        frappe.throw(_("La balanza indicada no existe."), title=_("Balanza Invalida"))

    doc = frappe.get_doc("Balanza Comprobacion EEFF", balanza_name)
    if moneda:
        doc.moneda = cstr(moneda or "").strip().upper()
    if tasa_cambio not in (None, ""):
        _upsert_tasa_cambio(doc, moneda=moneda, tasa_cambio=tasa_cambio)
    data = cstr(csv_content or "").strip()
    if not data:
        frappe.throw(_("Debes enviar el contenido CSV."), title=_("CSV Requerido"))

    reader = csv.DictReader(io.StringIO(data))
    rows = []
    for row in reader:
        normalized_row = _normalize_csv_row(row)
        cuenta = cstr(_csv_value(normalized_row, "cuenta", "codigo_cuenta", "account", "account_code") or "").strip()
        descripcion = cstr(
            _csv_value(normalized_row, "descripcion", "descripcion_cuenta", "account_name", "description") or ""
        ).strip()
        centro_costo = cstr(_csv_value(normalized_row, "centro_costo", "cost_center") or "").strip()
        debe_saldo_anterior = flt(_csv_value(normalized_row, "debe_saldo_anterior", "opening_debit") or 0)
        haber_saldo_anterior = flt(_csv_value(normalized_row, "haber_saldo_anterior", "opening_credit") or 0)
        debe_mes = flt(_csv_value(normalized_row, "debe_mes", "movement_debit", "period_debit") or 0)
        haber_mes = flt(_csv_value(normalized_row, "haber_mes", "movement_credit", "period_credit") or 0)
        saldo_firmado = flt(_csv_value(normalized_row, "saldo", "balance", "closing_balance") or 0)
        debe_saldo = flt(_csv_value(normalized_row, "debe_saldo", "debe", "debit", "closing_debit") or saldo_firmado)
        haber_saldo = flt(_csv_value(normalized_row, "haber_saldo", "haber", "credit", "closing_credit") or 0)
        if not cuenta and not descripcion:
            continue
        rows.append(
            {
                "codigo_cuenta": cuenta,
                "descripcion_cuenta": descripcion,
                "centro_costo": centro_costo,
                "debe_saldo_anterior": debe_saldo_anterior,
                "haber_saldo_anterior": haber_saldo_anterior,
                "debe_mes": debe_mes,
                "haber_mes": haber_mes,
                "debe_saldo": debe_saldo,
                "haber_saldo": haber_saldo,
            }
        )

    doc.set("lineas", [])
    for row in rows:
        doc.append("lineas", row)

    doc.save(ignore_permissions=True)
    return {
        "balanza": doc.name,
        "periodo_nombre": doc.periodo_nombre,
        "total_lineas": cint(doc.total_lineas),
        "total_debe": flt(doc.total_debe),
        "total_haber": flt(doc.total_haber),
        "cuadra": cint(doc.cuadra),
        "moneda": cstr(getattr(doc, "moneda", "") or "").strip().upper(),
        "moneda_tasa_cambio": cstr(moneda or "").strip().upper() or "USD",
        "tasa_cambio": flt(doc.get_tasa_cambio(moneda=moneda, fallback=1) or 1),
        "tasas_cambio": [
            {
                "moneda": cstr(getattr(row, "moneda", "") or "").strip().upper(),
                "tasa_cambio": flt(getattr(row, "tasa_cambio", 0) or 0),
            }
            for row in (doc.get("tasas_cambio") or [])
            if cstr(getattr(row, "moneda", "") or "").strip()
        ],
    }
