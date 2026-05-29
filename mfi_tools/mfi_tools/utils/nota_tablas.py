import re

import frappe
from frappe.utils import cint, cstr, flt

FORMULA_SPLIT_RE = re.compile(r"[\n,;]+")
DEFAULT_TABLE_CODE = "TABLA_01"
DEFAULT_ROW_CODE = "FILA"
DEFAULT_COLUMN_CODE = "COLUMNA"
TABLE_COLUMN_TYPES = ("Numero", "Moneda", "Porcentaje", "Texto")
TABLE_ALIGNMENTS = ("Left", "Center", "Right")
TABLE_ROW_TYPES = ("Detalle", "Subtotal", "Total", "Titulo")


def normalize_table_code(value, default=DEFAULT_TABLE_CODE):
    return cstr(value or default).strip().upper() or default


def normalize_row_code(value, default=DEFAULT_ROW_CODE):
    return cstr(value or default).strip().upper() or default


def normalize_column_code(value, default=DEFAULT_COLUMN_CODE):
    return cstr(value or default).strip().upper() or default


def parse_formula_tokens(expression):
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


def format_complex_note_value(cell=None, column=None):
    if not cell:
        return "-"

    value_text = cstr(getattr(cell, "valor_texto", "") or "").strip()
    value_number = getattr(cell, "valor_numero", None)
    format_type = _resolve_cell_format_type(cell, column, value_text=value_text)

    if format_type == "Texto":
        return value_text or "-"

    if value_text and value_number in (None, ""):
        return value_text

    if value_number in (None, ""):
        return "-"

    rounded = cint(getattr(cell, "redondear_entero", 0) or getattr(column, "redondear_entero", 0) or 0)
    number = flt(value_number or 0)
    decimals = 0 if rounded else 2

    if format_type == "Porcentaje":
        return _format_accounting_number(number, decimals=decimals, suffix="%")
    if format_type == "Moneda":
        return _format_accounting_number(number, decimals=decimals)
    if rounded:
        return _format_accounting_number(number, decimals=0)

    return _format_accounting_number(number, decimals=2, trim=True)


def _resolve_cell_format_type(cell=None, column=None, value_text=None):
    text_value = cstr(value_text if value_text is not None else getattr(cell, "valor_texto", "") or "").strip()
    format_type = cstr(getattr(cell, "formato_numero", "") or getattr(column, "tipo_dato", "") or "").strip()
    if format_type not in TABLE_COLUMN_TYPES:
        return "Texto" if text_value else "Numero"
    return format_type


def build_complex_section_tables(section_doc):
    if isinstance(section_doc, str):
        section_doc = frappe.get_doc("Seccion Nota EEFF", section_doc)

    columns_by_table = {}
    rows_by_table = {}
    cells_by_key = {}
    table_order = []

    for idx, row in enumerate(getattr(section_doc, "columnas_tabulares", None) or [], start=1):
        table_code = normalize_table_code(getattr(row, "codigo_tabla", None))
        if table_code not in table_order:
            table_order.append(table_code)
        columns_by_table.setdefault(table_code, []).append(
            {
                "codigo_tabla": table_code,
                "codigo_columna": normalize_column_code(getattr(row, "codigo_columna", None), f"COL_{idx:02d}"),
                "etiqueta": cstr(getattr(row, "etiqueta", "") or getattr(row, "codigo_columna", "") or f"Columna {idx}").strip(),
                "tipo_dato": cstr(getattr(row, "tipo_dato", "Numero") or "Numero").strip(),
                "alineacion": cstr(getattr(row, "alineacion", "Right") or "Right").strip(),
                "grupo_columna": cstr(getattr(row, "grupo_columna", "") or "").strip(),
                "es_total": cint(getattr(row, "es_total", 0) or 0),
                "redondear_entero": cint(getattr(row, "redondear_entero", 0) or 0),
                "idx": cint(getattr(row, "idx", idx) or idx),
            }
        )

    for idx, row in enumerate(getattr(section_doc, "filas_tabulares", None) or [], start=1):
        table_code = normalize_table_code(getattr(row, "codigo_tabla", None))
        if table_code not in table_order:
            table_order.append(table_code)
        row_type = cstr(getattr(row, "tipo_fila", "Detalle") or "Detalle").strip()
        rows_by_table.setdefault(table_code, []).append(
            {
                "codigo_tabla": table_code,
                "codigo_fila": normalize_row_code(getattr(row, "codigo_fila", None), f"FILA_{idx:02d}"),
                "descripcion": cstr(getattr(row, "descripcion", "") or getattr(row, "codigo_fila", "") or f"Fila {idx}").strip(),
                "nivel": max(cint(getattr(row, "nivel", 1) or 1), 1),
                "tipo_fila": row_type if row_type in TABLE_ROW_TYPES else "Detalle",
                "negrita": cint(getattr(row, "negrita", 0) or 0),
                "subrayado": cint(getattr(row, "subrayado", 0) or 0),
                "idx": cint(getattr(row, "idx", idx) or idx),
            }
        )

    for idx, cell in enumerate(getattr(section_doc, "celdas_tabulares", None) or [], start=1):
        table_code = normalize_table_code(getattr(cell, "codigo_tabla", None))
        row_code = normalize_row_code(getattr(cell, "codigo_fila", None), f"FILA_{idx:02d}")
        column_code = normalize_column_code(getattr(cell, "codigo_columna", None), DEFAULT_COLUMN_CODE)
        if table_code not in table_order:
            table_order.append(table_code)
        cells_by_key[(table_code, row_code, column_code)] = cell

    output = []
    for table_code in table_order:
        columns = columns_by_table.get(table_code) or _derive_columns_from_cells(cells_by_key, table_code)
        rows = rows_by_table.get(table_code) or _derive_rows_from_cells(cells_by_key, table_code)
        columns = sorted(columns, key=lambda row: (cint(row.get("idx", 0)), row.get("codigo_columna")))
        rows = sorted(rows, key=lambda row: (cint(row.get("idx", 0)), row.get("codigo_fila")))

        rendered_rows = []
        for row_meta in rows:
            row_type = cstr(row_meta.get("tipo_fila") or "Detalle").strip()
            cells = []
            for col_meta in columns:
                cell = cells_by_key.get((table_code, row_meta["codigo_fila"], col_meta["codigo_columna"]))
                format_type = _resolve_cell_format_type(cell, _DictWrapper(col_meta))
                text = "" if row_type == "Titulo" else format_complex_note_value(cell, _DictWrapper(col_meta))
                cells.append(
                    {
                        "codigo_columna": col_meta["codigo_columna"],
                        "texto": text,
                        "formato_numero": format_type,
                        "es_moneda": format_type == "Moneda",
                        "alineacion": col_meta["alineacion"] if col_meta["alineacion"] in TABLE_ALIGNMENTS else "Right",
                        "comentario": cstr(getattr(cell, "comentario", "") or "").strip() if cell else "",
                    }
                )
            rendered_rows.append(
                {
                    **row_meta,
                    "texto": row_meta["descripcion"],
                    "es_total": row_type == "Total",
                    "es_subtotal": row_type == "Subtotal",
                    "es_titulo": row_type == "Titulo",
                    "celdas": cells,
                }
            )

        group_headers = _build_column_groups(columns)
        output.append(
            {
                "codigo_tabla": table_code,
                "columnas": columns,
                "filas": rendered_rows,
                "grupos_columnas": group_headers,
                "tiene_grupos": any(group["label"] for group in group_headers),
            }
        )

    return output


def _derive_columns_from_cells(cells_by_key, table_code):
    columns = []
    seen = set()
    for key in cells_by_key:
        cell_table, _, column_code = key
        if cell_table != table_code or column_code in seen:
            continue
        seen.add(column_code)
        columns.append(
            {
                "codigo_tabla": table_code,
                "codigo_columna": column_code,
                "etiqueta": column_code,
                "tipo_dato": "Numero",
                "alineacion": "Right",
                "grupo_columna": "",
                "es_total": 0,
                "redondear_entero": 0,
                "idx": len(columns) + 1,
            }
        )
    return columns


def _derive_rows_from_cells(cells_by_key, table_code):
    rows = []
    seen = set()
    for key in cells_by_key:
        cell_table, row_code, _ = key
        if cell_table != table_code or row_code in seen:
            continue
        seen.add(row_code)
        rows.append(
            {
                "codigo_tabla": table_code,
                "codigo_fila": row_code,
                "descripcion": row_code,
                "nivel": 1,
                "tipo_fila": "Detalle",
                "negrita": 0,
                "subrayado": 0,
                "idx": len(rows) + 1,
            }
        )
    return rows


def _build_column_groups(columns):
    groups = []
    for column in columns:
        label = cstr(column.get("grupo_columna", "") or "").strip()
        key = label or f"__{column.get('codigo_columna')}"
        if groups and groups[-1]["key"] == key:
            groups[-1]["span"] += 1
            continue
        groups.append({"key": key, "label": label, "span": 1})
    return groups


class _DictWrapper:
    def __init__(self, values):
        self._values = values or {}

    def __getattr__(self, item):
        return self._values.get(item)


def _format_accounting_number(value, decimals=2, suffix="", trim=False):
    number = flt(value or 0)
    if abs(number) < 0.0000001:
        return "-"

    text = f"{abs(number):,.{decimals}f}"
    if trim and "." in text:
        text = text.rstrip("0").rstrip(".")
    if suffix:
        text = f"{text}{suffix}"
    return f"({text})" if number < 0 else text
