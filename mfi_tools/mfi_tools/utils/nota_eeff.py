import re

import frappe
from frappe import _
from frappe.utils import cint, cstr


def clean_note_part(value):
    return cstr(value or "").strip()


def normalize_note_number(value):
    if value in (None, ""):
        return None
    number = cint(value)
    return number if number > 0 else None


def normalize_sub_note(value):
    raw = clean_note_part(value)
    if not raw:
        return ""
    raw = re.sub(r"^\((.*)\)$", r"\1", raw).strip()
    return raw


def normalize_sub_note_key(value):
    return normalize_sub_note(value).upper()


def build_note_identifier(numero_nota, sub_nota=None):
    numero = normalize_note_number(numero_nota)
    sub = normalize_sub_note(sub_nota)
    if not numero:
        return ""
    return f"{numero} ({sub})" if sub else cstr(numero)


def build_note_autoname(numero_nota, sub_nota, package_name):
    identifier = build_note_identifier(numero_nota, sub_nota) or "SN"
    return f"Nota {identifier} - {package_name or frappe.generate_hash(length=6)}"


def parse_note_identifier(value):
    if isinstance(value, int):
        return normalize_note_number(value), ""

    raw = clean_note_part(value)
    if not raw:
        return None, ""

    match = re.fullmatch(r"(\d+)\s*\(([A-Za-z0-9]+)\)", raw)
    if match:
        return normalize_note_number(match.group(1)), normalize_sub_note(match.group(2))
    return normalize_note_number(raw), ""


def note_sort_key(row):
    numero = normalize_note_number(getattr(row, "numero_nota", None) if not isinstance(row, dict) else row.get("numero_nota"))
    sub = normalize_sub_note(getattr(row, "sub_nota", None) if not isinstance(row, dict) else row.get("sub_nota"))
    sub_key = normalize_sub_note_key(sub)

    number_value = numero if numero else 10**9
    sub_rank = 0 if not sub else 1
    return (number_value, sub_rank, sub_key)


def sort_note_rows(rows):
    return sorted(rows or [], key=note_sort_key)


def get_package_note_rows(package_name, fields=None, limit_page_length=500):
    if not clean_note_part(package_name) or not frappe.db.exists("Paquete EEFF", package_name):
        return []

    base_fields = ["name", "numero_nota", "sub_nota", "titulo", "modified", "creation"]
    requested_fields = list(fields or [])
    merged_fields = list(dict.fromkeys(base_fields + requested_fields))
    rows = frappe.get_all(
        "Nota EEFF",
        filters={"paquete_eeff": package_name},
        fields=merged_fields,
        limit_page_length=limit_page_length,
    )
    return sort_note_rows(rows)


def find_note_name(package_name, identifier, allow_subnotes=False):
    numero_nota, sub_nota = parse_note_identifier(identifier)
    if not numero_nota:
        frappe.throw(_("Debes indicar un numero de nota valido."), title=_("Destino Incompleto"))

    filters = {"paquete_eeff": package_name, "numero_nota": numero_nota}
    names = frappe.get_all(
        "Nota EEFF",
        filters=filters,
        fields=["name", "sub_nota", "creation"],
        limit_page_length=20,
    )
    if not names:
        return None, numero_nota, sub_nota

    if sub_nota:
        requested_sub_key = normalize_sub_note_key(sub_nota)
        matching_subnotes = [
            row for row in names if normalize_sub_note_key(getattr(row, "sub_nota", "")) == requested_sub_key
        ]
        if not matching_subnotes:
            return None, numero_nota, sub_nota
        if len(matching_subnotes) > 1:
            frappe.throw(
                _("Existe mas de una Nota EEFF con identificador {0} dentro del paquete {1}.").format(
                    build_note_identifier(numero_nota, sub_nota), package_name
                ),
                title=_("Destino Ambiguo"),
            )
        matched_sub_nota = normalize_sub_note(getattr(matching_subnotes[0], "sub_nota", "")) or sub_nota
        return matching_subnotes[0].name, numero_nota, matched_sub_nota

    blank_sub = [row for row in names if not normalize_sub_note(getattr(row, "sub_nota", ""))]
    if len(blank_sub) == 1:
        return blank_sub[0].name, numero_nota, ""

    if len(names) == 1 and allow_subnotes:
        return names[0].name, numero_nota, normalize_sub_note(getattr(names[0], "sub_nota", ""))

    if len(names) > 1:
        frappe.throw(
            _("Existe mas de una Nota EEFF con numero {0} dentro del paquete {1}. Indica tambien la sub-nota.").format(
                numero_nota, package_name
            ),
            title=_("Destino Ambiguo"),
        )

    return names[0].name, numero_nota, ""
