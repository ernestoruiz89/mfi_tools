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

    return format_accounting_number(value, fmt, trim_plain=(fmt == "Numero"), none_as="")


def format_accounting_number(value, format_type="Numero", trim_plain=True, none_as="-"):
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
        text = f"{abs_number:,.2f}"
    elif fmt == "Porcentaje":
        text = f"{abs_number:,.2f}%"
    else:
        text = f"{abs_number:,.2f}"
        if trim_plain and "." in text:
            text = text.rstrip("0").rstrip(".")

    return f"({text})" if number < 0 else text
