from frappe.utils import cint, cstr, flt

PRESENTATION_FORMATS = ("Numero", "Moneda", "Porcentaje", "Texto")


def normalize_estado_line_format(value):
    fmt = cstr(value or "").strip().title()
    return fmt if fmt in PRESENTATION_FORMATS else "Numero"


def is_text_estado_line(linea):
    return normalize_estado_line_format(getattr(linea, "formato_presentacion", "Numero")) == "Texto"


def format_estado_line_value(linea, fieldname):
    if cint(getattr(linea, "es_titulo", 0)):
        return ""

    fmt = normalize_estado_line_format(getattr(linea, "formato_presentacion", "Numero"))
    if fmt == "Texto":
        return cstr(getattr(linea, "valor_texto", "") or "").strip()

    value = getattr(linea, fieldname, None)
    if value in (None, ""):
        return ""

    decimals = 0 if cint(getattr(linea, "redondear_entero", 0)) else 2
    return format_accounting_number(value, fmt, none_as="", decimals=decimals)


def format_accounting_number(value, format_type="Numero", trim_plain=False, none_as="-", decimals=2):
    if value in (None, ""):
        return none_as

    try:
        number = flt(value)
    except Exception:
        return cstr(value)

    if abs(number) < 0.0000001:
        return "-"

    fmt = normalize_estado_line_format(format_type)
    abs_number = abs(number)

    if fmt == "Moneda":
        text = f"{abs_number:,.{decimals}f}"
    elif fmt == "Porcentaje":
        text = f"{abs_number:,.{decimals}f}%"
    else:
        text = f"{abs_number:,.{decimals}f}"

    return f"({text})" if number < 0 else text
