import calendar
import csv
import io
import os
import re
import unicodedata
import urllib.parse

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

BALANCE_EXPORT_COLUMNS = (
    ("codigo_cuenta", "Codigo Cuenta"),
    ("descripcion_cuenta", "Descripcion Cuenta"),
    ("centro_costo", "Centro Costo"),
    ("moneda", "Moneda"),
    ("debe_saldo_anterior", "Debe Saldo Anterior"),
    ("haber_saldo_anterior", "Haber Saldo Anterior"),
    ("saldo_anterior", "Saldo Anterior"),
    ("debe_mes", "Debe Mes"),
    ("haber_mes", "Haber Mes"),
    ("movimiento_del_mes", "Movimiento del Mes"),
    ("debe_saldo", "Debe Saldo"),
    ("haber_saldo", "Haber Saldo"),
    ("saldo", "Saldo"),
)

HEADER_KEYWORDS = {
    "cuenta",
    "codigo_cuenta",
    "codigo",
    "codigo_de_cuenta",
    "codigo_de_la_cuenta",
    "cod_cuenta",
    "cod",
    "account",
    "account_code",
    "no_cuenta",
    "numero_cuenta",
    "numero_de_cuenta",
    "cve_cuenta",
    "cve",
    "descripcion",
    "descripcion_cuenta",
    "descripcion_de_cuenta",
    "descripcion_de_la_cuenta",
    "account_name",
    "description",
    "nombre_cuenta",
    "nombre_de_la_cuenta",
    "nombre_de_cuenta",
    "nombre",
    "concepto",
    "centro_costo",
    "cost_center",
    "centro_de_costo",
    "debe",
    "haber",
    "saldo",
    "debit",
    "credit",
    "balance",
    "inicial",
    "anterior",
    "movimiento",
    "cargos",
    "abonos",
    "final",
    "mes",
}


def _normalize_header(value):
    normalized = unicodedata.normalize("NFKD", cstr(value or ""))
    ascii_value = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", "_", ascii_value.strip().lower())
    return cleaned.strip("_")


def _clean_cell_str(val):
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return cstr(val).strip()


def _clean_cell_flt(val):
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return flt(val)
    s = cstr(val).strip()
    if not s:
        return 0.0
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    s = re.sub(r"[^\d,\.\-]", "", s)
    if not s:
        return 0.0
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        res = flt(s)
        return -res if is_negative else res
    except Exception:
        return 0.0


def _normalize_csv_row(row):
    return {
        _normalize_header(key): value
        for key, value in (row or {}).items()
        if cstr(key or "").strip()
    }


def _row_val(row, *aliases):
    for alias in aliases:
        key = _normalize_header(alias)
        if key in row and row.get(key) not in (None, ""):
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


def _detect_file_format(file_bytes, ext=""):
    ext = cstr(ext or "").strip().lower()
    if ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        return "xlsx"
    if ext in (".xls", ".xlt"):
        return "xls"
    if ext in (".csv", ".tsv", ".txt"):
        return "csv"

    if file_bytes:
        if file_bytes.startswith(b"PK\x03\x04"):
            return "xlsx"
        if file_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return "xls"

    return "csv"


def _get_file_bytes_and_ext(file_url=None, csv_content=None):
    if csv_content:
        if isinstance(csv_content, bytes):
            return csv_content, ".csv"
        return cstr(csv_content).encode("utf-8"), ".csv"

    if not file_url:
        return None, ""

    file_url = cstr(file_url).strip()

    if file_url.startswith("data:"):
        parts = file_url.split(",", 1)
        if len(parts) == 2:
            import base64

            header, b64data = parts
            file_bytes = base64.b64decode(b64data)
            ext = ""
            if "spreadsheetml" in header or "xlsx" in header:
                ext = ".xlsx"
            elif "excel" in header or "xls" in header:
                ext = ".xls"
            elif "csv" in header:
                ext = ".csv"
            return file_bytes, ext

    clean_url = file_url.split("?")[0]
    filename = clean_url.split("/")[-1]
    ext = os.path.splitext(filename)[1].lower()

    file_docs = frappe.get_all(
        "File",
        filters={"file_url": clean_url},
        fields=["name", "file_name", "file_url"],
        limit=1,
    )
    if not file_docs and "%" in clean_url:
        decoded_url = urllib.parse.unquote(clean_url)
        file_docs = frappe.get_all(
            "File",
            filters={"file_url": decoded_url},
            fields=["name", "file_name", "file_url"],
            limit=1,
        )

    if file_docs:
        fdoc = frappe.get_doc("File", file_docs[0].name)
        file_bytes = fdoc.get_content()
        f_name = fdoc.file_name or filename
        ext = os.path.splitext(f_name)[1].lower() or ext
        return file_bytes, ext

    site_path = None
    if clean_url.startswith("/files/"):
        rel_path = clean_url[len("/files/"):]
        site_path = frappe.get_site_path("public", "files", rel_path)
    elif clean_url.startswith("/private/files/"):
        rel_path = clean_url[len("/private/files/"):]
        site_path = frappe.get_site_path("private", "files", rel_path)
    elif os.path.isabs(clean_url) and os.path.exists(clean_url):
        site_path = clean_url
    else:
        site_path = frappe.get_site_path(clean_url.lstrip("/"))

    if site_path and os.path.exists(site_path):
        with open(site_path, "rb") as f:
            file_bytes = f.read()
        return file_bytes, ext

    return None, ext


def _extract_dict_rows(raw_rows):
    if not raw_rows:
        return []

    header_idx = -1
    headers = []
    for idx, row in enumerate(raw_rows):
        normalized_cells = [_normalize_header(c) for c in row if c is not None and cstr(c).strip()]
        matches = [c for c in normalized_cells if c in HEADER_KEYWORDS]
        if len(matches) >= 2 or (
            len(matches) >= 1
            and any(k in matches for k in ("codigo_cuenta", "cuenta", "codigo"))
        ):
            header_idx = idx
            headers = [_normalize_header(c) if c is not None else "" for c in row]
            break

    if header_idx == -1:
        for idx, row in enumerate(raw_rows):
            if any(c is not None and cstr(c).strip() for c in row):
                header_idx = idx
                headers = [_normalize_header(c) if c is not None else "" for c in row]
                break

    if header_idx == -1 or not headers:
        return []

    dict_rows = []
    for row in raw_rows[header_idx + 1:]:
        if not any(c is not None and cstr(c).strip() for c in row):
            continue
        row_dict = {}
        for col_idx, col_name in enumerate(headers):
            if col_name and col_idx < len(row):
                row_dict[col_name] = row[col_idx]
        dict_rows.append(row_dict)

    return dict_rows


def _parse_xlsx_bytes_to_dict_rows(file_bytes):
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    sheet = None
    for s in wb.worksheets:
        if re.search(r"balanza|trial|comprobaci[oó]n", s.title, re.I):
            sheet = s
            break
    if not sheet:
        sheet = wb.active or wb.worksheets[0]

    raw_rows = []
    for row in sheet.iter_rows(values_only=True):
        raw_rows.append(list(row))
    wb.close()
    return _extract_dict_rows(raw_rows)


def _parse_xls_bytes_to_dict_rows(file_bytes):
    import xlrd

    book = xlrd.open_workbook(file_contents=file_bytes)
    sheet = None
    for s in book.sheets():
        if re.search(r"balanza|trial|comprobaci[oó]n", s.name, re.I):
            sheet = s
            break
    if not sheet:
        sheet = book.sheet_by_index(0)

    raw_rows = []
    for row_idx in range(sheet.nrows):
        raw_rows.append(sheet.row_values(row_idx))
    return _extract_dict_rows(raw_rows)


def _parse_csv_bytes_to_dict_rows(csv_text_or_bytes):
    if isinstance(csv_text_or_bytes, bytes):
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                csv_text = csv_text_or_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            csv_text = csv_text_or_bytes.decode("utf-8", errors="replace")
    else:
        csv_text = cstr(csv_text_or_bytes or "")

    csv_text = csv_text.strip()
    if not csv_text:
        return []

    sample = csv_text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        delimiter = dialect.delimiter
    except Exception:
        first_line = csv_text.splitlines()[0] if csv_text else ""
        if ";" in first_line and first_line.count(";") >= first_line.count(","):
            delimiter = ";"
        elif "\t" in first_line:
            delimiter = "\t"

    reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
    raw_rows = list(reader)
    return _extract_dict_rows(raw_rows)


def _map_row_to_balance_line(row):
    cuenta = _clean_cell_str(
        _row_val(
            row,
            "codigo_cuenta",
            "cuenta",
            "codigo",
            "codigo_de_cuenta",
            "codigo_de_la_cuenta",
            "cod_cuenta",
            "cod",
            "account",
            "account_code",
            "no_cuenta",
            "numero_cuenta",
            "numero_de_cuenta",
            "cve_cuenta",
            "cve",
        )
    )
    descripcion = _clean_cell_str(
        _row_val(
            row,
            "descripcion_cuenta",
            "descripcion",
            "descripcion_de_cuenta",
            "descripcion_de_la_cuenta",
            "account_name",
            "description",
            "nombre_cuenta",
            "nombre_de_la_cuenta",
            "nombre_de_cuenta",
            "nombre",
            "concepto",
        )
    )
    centro_costo = _clean_cell_str(
        _row_val(
            row,
            "centro_costo",
            "cost_center",
            "centro_de_costo",
            "centro_de_costos",
            "centros_de_costo",
            "cc",
            "c_costo",
            "segmento",
        )
    )

    debe_saldo_anterior = _clean_cell_flt(
        _row_val(
            row,
            "debe_saldo_anterior",
            "opening_debit",
            "saldo_anterior_debe",
            "saldo_inicial_debe",
            "debe_inicial",
            "debe_anterior",
        )
    )
    haber_saldo_anterior = _clean_cell_flt(
        _row_val(
            row,
            "haber_saldo_anterior",
            "opening_credit",
            "saldo_anterior_haber",
            "saldo_inicial_haber",
            "haber_inicial",
            "haber_anterior",
        )
    )
    if debe_saldo_anterior == 0 and haber_saldo_anterior == 0:
        saldo_ant = _clean_cell_flt(
            _row_val(
                row,
                "saldo_anterior",
                "saldo_inicial",
                "saldo_de_apertura",
                "saldo_apertura",
                "opening_balance",
                "saldo_ant",
                "balance_anterior",
            )
        )
        if saldo_ant > 0:
            debe_saldo_anterior = saldo_ant
        elif saldo_ant < 0:
            haber_saldo_anterior = abs(saldo_ant)

    debe_mes = _clean_cell_flt(
        _row_val(
            row,
            "debe_mes",
            "movement_debit",
            "period_debit",
            "debe_movimiento",
            "movimientos_debe",
            "cargos",
            "debe_del_mes",
            "cargo",
        )
    )
    haber_mes = _clean_cell_flt(
        _row_val(
            row,
            "haber_mes",
            "movement_credit",
            "period_credit",
            "haber_movimiento",
            "movimientos_haber",
            "abonos",
            "haber_del_mes",
            "abono",
        )
    )
    if debe_mes == 0 and haber_mes == 0:
        mov_mes = _clean_cell_flt(
            _row_val(
                row,
                "movimiento_del_mes",
                "movimiento",
                "movimientos_del_mes",
                "movimientos",
                "net_movement",
                "period_movement",
            )
        )
        if mov_mes > 0:
            debe_mes = mov_mes
        elif mov_mes < 0:
            haber_mes = abs(mov_mes)

    saldo_firmado = _clean_cell_flt(
        _row_val(
            row,
            "saldo",
            "balance",
            "closing_balance",
            "saldo_final",
            "saldo_cierre",
            "saldo_actual",
        )
    )
    debe_saldo = _clean_cell_flt(
        _row_val(
            row,
            "debe_saldo",
            "debe",
            "debit",
            "closing_debit",
            "saldo_final_debe",
            "debe_final",
            "saldo_debe",
        )
    )
    haber_saldo = _clean_cell_flt(
        _row_val(
            row,
            "haber_saldo",
            "haber",
            "credit",
            "closing_credit",
            "saldo_final_haber",
            "haber_final",
            "saldo_haber",
        )
    )

    if debe_saldo == 0 and haber_saldo == 0 and saldo_firmado != 0:
        if saldo_firmado > 0:
            debe_saldo = saldo_firmado
        else:
            haber_saldo = abs(saldo_firmado)

    if not cuenta and not descripcion:
        return None

    return {
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


def _parse_balance_rows(file_bytes, ext="csv"):
    fmt = _detect_file_format(file_bytes, ext=ext)
    if fmt == "xlsx":
        dict_rows = _parse_xlsx_bytes_to_dict_rows(file_bytes)
    elif fmt == "xls":
        dict_rows = _parse_xls_bytes_to_dict_rows(file_bytes)
    else:
        dict_rows = _parse_csv_bytes_to_dict_rows(file_bytes)

    mapped_rows = []
    for r in dict_rows:
        mapped = _map_row_to_balance_line(r)
        if mapped:
            mapped_rows.append(mapped)

    return mapped_rows


class BalanzaComprobacionEEFF(Document):
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
        cliente = cstr(
            self.__dict__.get("cliente")
            or (self._data.get("cliente") if hasattr(self, "_data") and isinstance(self._data, dict) else "")
            or ""
        ).strip()
        if cliente:
            customer_name = frappe.db.get_value("Customer", cliente, "customer_name")
            return cstr(customer_name or cliente).strip()
        return ""

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
            moneda = cstr(
                frappe.db.get_default("currency")
                or frappe.defaults.get_global_default("currency")
                or "USD"
            ).strip().upper()

        if not moneda:
            moneda = "USD"

        if not frappe.db.exists("Currency", moneda):
            frappe.throw(
                _("La moneda {0} no existe en el catalogo de monedas.").format(moneda),
                title=_("Moneda Invalida"),
            )
        self.moneda = moneda

    def _sync_period_fields(self):
        company = cstr(self.company or "").strip()
        mes = cstr(self.mes or "").strip()
        anio = cint(self.anio or 0)
        if not company or not mes or not anio:
            return

        periodo = f"{company}-{mes}-{anio}"
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
def cargar_balanza_archivo(balanza_name, file_url=None, csv_content=None, tasa_cambio=None, moneda=None):
    if not frappe.db.exists("Balanza Comprobacion EEFF", balanza_name):
        frappe.throw(_("La balanza indicada no existe."), title=_("Balanza Invalida"))

    doc = frappe.get_doc("Balanza Comprobacion EEFF", balanza_name)
    doc.check_permission("write")

    if moneda:
        doc.moneda = cstr(moneda or "").strip().upper()
    if tasa_cambio not in (None, ""):
        _upsert_tasa_cambio(doc, moneda=moneda or doc.moneda, tasa_cambio=tasa_cambio)

    file_bytes, ext = _get_file_bytes_and_ext(file_url=file_url, csv_content=csv_content)
    if not file_bytes:
        frappe.throw(_("No se encontro contenido o archivo para importar."), title=_("Archivo Requerido"))

    rows = _parse_balance_rows(file_bytes, ext=ext)
    if not rows:
        frappe.throw(
            _("No se encontraron lineas validas en el archivo importado. Verifica los encabezados del archivo."),
            title=_("Archivo Sin Datos"),
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


@frappe.whitelist()
def cargar_balanza_csv(balanza_name, csv_content, tasa_cambio=None, moneda=None):
    return cargar_balanza_archivo(
        balanza_name=balanza_name,
        csv_content=csv_content,
        tasa_cambio=tasa_cambio,
        moneda=moneda,
    )


def _build_balance_excel_template(doc=None):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Plantilla Balanza")
    for index, width in enumerate((20, 60, 22, 12) + (22,) * 9, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    header = []
    for _fieldname, label in BALANCE_EXPORT_COLUMNS:
        cell = WriteOnlyCell(sheet, value=_(label))
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
        header.append(cell)
    sheet.append(header)

    sample_rows = [
        ("1101", "Caja General", "ADM", "1500.00", "0.00", "1500.00", "250.00", "100.00", "150.00", "1650.00", "0.00", "1650.00"),
        ("1201", "Cuentas por Cobrar", "COM", "2000.00", "0.00", "2000.00", "500.00", "200.00", "300.00", "2300.00", "0.00", "2300.00"),
        ("2101", "Proveedores", "BOD", "0.00", "1800.00", "-1800.00", "400.00", "900.00", "-500.00", "0.00", "2300.00", "-2300.00"),
        ("3101", "Capital Social", "", "0.00", "1650.00", "-1650.00", "0.00", "0.00", "0.00", "0.00", "1650.00", "-1650.00"),
        ("4101", "Ingresos Operativos", "", "0.00", "0.00", "0.00", "0.00", "500.00", "-500.00", "0.00", "500.00", "-500.00"),
        ("6101", "Gasto Administrativo", "ADM", "0.00", "0.00", "0.00", "300.00", "0.00", "300.00", "300.00", "0.00", "300.00"),
    ]

    moneda = (doc.moneda if doc and hasattr(doc, "moneda") else "USD") or "USD"
    for r in sample_rows:
        cells = []
        c = WriteOnlyCell(sheet, value=r[0])
        c.data_type = "s"
        cells.append(c)

        c = WriteOnlyCell(sheet, value=r[1])
        c.data_type = "s"
        cells.append(c)

        c = WriteOnlyCell(sheet, value=r[2])
        c.data_type = "s"
        cells.append(c)

        c = WriteOnlyCell(sheet, value=moneda)
        c.data_type = "s"
        cells.append(c)

        for val in r[3:]:
            num = flt(val)
            c = WriteOnlyCell(sheet, value=num)
            c.number_format = '#,##0.00;[Red](#,##0.00);0.00'
            cells.append(c)
        sheet.append(cells)

    with io.BytesIO() as output:
        workbook.save(output)
        return output.getvalue()


def _build_balance_excel(doc):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Balanza")
    sheet.freeze_panes = "E2"
    sheet.auto_filter.ref = f"A1:M{len(doc.lineas) + 1}"
    for index, width in enumerate((20, 60, 22, 12) + (22,) * 9, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    header = []
    for _fieldname, label in BALANCE_EXPORT_COLUMNS:
        cell = WriteOnlyCell(sheet, value=_(label))
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
        header.append(cell)
    sheet.append(header)

    for row in doc.lineas:
        cells = []
        for index, (fieldname, _label) in enumerate(BALANCE_EXPORT_COLUMNS):
            value = row.get(fieldname)
            if index < 4:
                if fieldname == "moneda":
                    value = value or doc.moneda
                cell = WriteOnlyCell(sheet, value=cstr(value or ""))
                cell.data_type = "s"
                cell.number_format = "@"
            else:
                cell = WriteOnlyCell(sheet, value=flt(value or 0))
                cell.number_format = '#,##0.00;[Red](#,##0.00);0.00'
            cells.append(cell)
        sheet.append(cells)

    with io.BytesIO() as output:
        workbook.save(output)
        return output.getvalue()


@frappe.whitelist()
def descargar_balanza_excel(balanza_name):
    doc = frappe.get_doc("Balanza Comprobacion EEFF", balanza_name)
    doc.check_permission("read")
    doc.check_permission("export")
    if not doc.get("lineas"):
        content = _build_balance_excel_template(doc)
    else:
        content = _build_balance_excel(doc)

    safe_name = re.sub(r'[\\/:*?"<>|\r\n]+', "-", cstr(doc.name)).strip(" .") or "balanza"
    frappe.local.response.filename = f"Balanza-{safe_name[:140]}.xlsx"
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"
    frappe.local.response.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@frappe.whitelist()
def descargar_plantilla_excel(balanza_name=None):
    doc = None
    if balanza_name and frappe.db.exists("Balanza Comprobacion EEFF", balanza_name):
        doc = frappe.get_doc("Balanza Comprobacion EEFF", balanza_name)
    content = _build_balance_excel_template(doc)
    frappe.local.response.filename = "plantilla_balanza_comprobacion.xlsx"
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"
    frappe.local.response.content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@frappe.whitelist()
def duplicar_a_moneda(docname, moneda_destino, tasa_cambio, operacion):
    if not frappe.db.exists("Balanza Comprobacion EEFF", docname):
        frappe.throw(_("La balanza indicada no existe."))

    doc = frappe.get_doc("Balanza Comprobacion EEFF", docname)
    moneda_destino = cstr(moneda_destino or "").strip().upper()
    tasa_cambio = flt(tasa_cambio or 1)
    if tasa_cambio <= 0:
        frappe.throw(_("La tasa de cambio debe ser mayor a cero."))

    new_doc = frappe.copy_doc(doc)
    new_doc.moneda = moneda_destino
    new_doc.nombre_balanza = f"{doc.nombre_balanza} - {moneda_destino}"
    new_doc.set("tasas_cambio", [])

    for row in new_doc.get("lineas") or []:
        if operacion == "Multiplicar":
            row.debe_saldo_anterior = flt(row.debe_saldo_anterior) * tasa_cambio
            row.haber_saldo_anterior = flt(row.haber_saldo_anterior) * tasa_cambio
            row.debe_mes = flt(row.debe_mes) * tasa_cambio
            row.haber_mes = flt(row.haber_mes) * tasa_cambio
            row.debe_saldo = flt(row.debe_saldo) * tasa_cambio
            row.haber_saldo = flt(row.haber_saldo) * tasa_cambio
        else:
            row.debe_saldo_anterior = flt(row.debe_saldo_anterior) / tasa_cambio
            row.haber_saldo_anterior = flt(row.haber_saldo_anterior) / tasa_cambio
            row.debe_mes = flt(row.debe_mes) / tasa_cambio
            row.haber_mes = flt(row.haber_mes) / tasa_cambio
            row.debe_saldo = flt(row.debe_saldo) / tasa_cambio
            row.haber_saldo = flt(row.haber_saldo) / tasa_cambio

    new_doc.save(ignore_permissions=True)
    return new_doc.name
