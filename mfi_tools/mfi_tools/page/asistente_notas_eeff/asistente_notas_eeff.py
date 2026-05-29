import frappe
from frappe import _
from frappe.utils import cint, cstr

from mfi_tools.mfi_tools.utils.customer import get_customer_display, get_customer_display_map
from mfi_tools.mfi_tools.utils.nota_eeff import build_note_identifier, get_package_note_rows, normalize_note_number

MESES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
NOTE_EDITABLE_FIELDS = (
    "numero_nota",
    "sub_nota",
    "titulo",
    "tamano_letra_impresion",
    "ancho_tabla_impresion",
    "alineacion_tabla_impresion",
    "estado_aprobacion",
    "estructura_nota",
    "contenido_narrativo",
    "observaciones",
)
NOTE_CHILD_TABLES = ("cifras_nota",)
SECTION_EDITABLE_FIELDS = (
    "codigo_seccion",
    "tipo_seccion",
    "titulo_seccion",
    "orden",
    "mostrar_titulo",
    "contenido_narrativo",
    "observaciones",
)
SECTION_CHILD_TABLES = (
    "columnas_tabulares",
    "filas_tabulares",
    "celdas_tabulares",
)
CHILD_META_FIELDS = {
    "doctype",
    "name",
    "parent",
    "parentfield",
    "parenttype",
    "idx",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "__islocal",
    "__unsaved",
    "_user_tags",
    "_comments",
    "_assign",
    "_liked_by",
    "_seen",
}


def _clean(value):
    return cstr(value or "").strip()


def _ensure_page_access(write=False):
    required = [
        ("Paquete EEFF", "read"),
        ("Nota EEFF", "read"),
        ("Seccion Nota EEFF", "read"),
    ]
    if write:
        required.extend(
            [
                ("Nota EEFF", "write"),
                ("Seccion Nota EEFF", "write"),
            ]
        )
    for doctype, ptype in required:
        if frappe.has_permission(doctype, ptype=ptype):
            continue
        frappe.throw(
            _("No tienes permisos para usar el editor de notas EEFF."),
            frappe.PermissionError,
        )


def _build_filters(cliente=None, anio=None, mes=None):
    filters = {}
    if _clean(cliente):
        filters["cliente"] = _clean(cliente)
    if cint(anio or 0):
        filters["anio"] = cint(anio)
    if _clean(mes):
        filters["mes"] = _clean(mes)
    return filters


def _serialize_child_row(row):
    values = row.as_dict(no_nulls=False) if hasattr(row, "as_dict") else dict(row or {})
    return {key: value for key, value in values.items() if key not in CHILD_META_FIELDS and not str(key).startswith("_")}


def _clean_payload_row(row):
    if not row:
        return {}
    values = row.as_dict(no_nulls=False) if hasattr(row, "as_dict") else dict(row)
    return {key: value for key, value in values.items() if key not in CHILD_META_FIELDS and not str(key).startswith("_")}


def _serialize_note_rows(package_name):
    rows = get_package_note_rows(
        package_name,
        fields=["estructura_nota", "estado_aprobacion", "total_secciones_complejas"],
        limit_page_length=1000,
    )
    return [
        {
            "name": row.name,
            "numero_nota": row.numero_nota,
            "sub_nota": row.sub_nota,
            "identificador_nota": build_note_identifier(row.numero_nota, row.sub_nota),
            "titulo": row.titulo,
            "estructura_nota": row.estructura_nota or "Simple",
            "estado_aprobacion": row.estado_aprobacion or "Borrador",
            "total_secciones_complejas": cint(row.total_secciones_complejas or 0),
            "label": _("Nota {0}. {1}").format(
                build_note_identifier(row.numero_nota, row.sub_nota) or "-",
                row.titulo or _("Sin titulo"),
            ),
        }
        for row in rows
    ]


def _next_note_number(note_rows):
    max_number = 0
    for row in note_rows or []:
        max_number = max(max_number, cint(normalize_note_number(row.get("numero_nota")) or 0))
    return max_number + 1 if max_number else 1


def _get_clients():
    rows = frappe.get_all(
        "Paquete EEFF",
        fields=["cliente"],
        filters={"cliente": ["is", "set"]},
        distinct=True,
        order_by="cliente asc",
        limit_page_length=2000,
    )
    names = sorted({_clean(row.cliente) for row in rows if _clean(row.cliente)})
    label_map = get_customer_display_map(names)
    return [{"value": name, "label": label_map.get(name, name)} for name in names]


def _build_package_label(row, customer_label):
    return f"{row.name} | {customer_label or row.cliente or '-'} | {row.mes or '-'} {row.anio or '-'} | {row.estado_preparacion or 'Borrador'}"


def _get_packages(cliente=None, anio=None, mes=None):
    rows = frappe.get_all(
        "Paquete EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes),
        fields=["name", "cliente", "anio", "mes", "periodo_nombre", "estado_preparacion", "modified"],
        order_by="modified desc",
        limit_page_length=500,
    )
    label_map = get_customer_display_map([row.cliente for row in rows])
    output = []
    for row in rows:
        customer_label = label_map.get(row.cliente, row.cliente)
        output.append(
            {
                "value": row.name,
                "label": _build_package_label(row, customer_label),
                "cliente": row.cliente,
                "cliente_label": customer_label,
                "anio": row.anio,
                "mes": row.mes,
                "periodo_nombre": row.periodo_nombre,
                "estado_preparacion": row.estado_preparacion,
            }
        )
    return output


def _build_summary(package_name):
    package_name = _clean(package_name)
    if not package_name or not frappe.db.exists("Paquete EEFF", package_name):
        return None

    package_values = frappe.db.get_value(
        "Paquete EEFF",
        package_name,
        ["cliente", "anio", "mes", "periodo_nombre", "estado_preparacion", "total_notas"],
        as_dict=True,
    ) or {}
    note_rows = _serialize_note_rows(package_name)
    total_notas = len(note_rows)
    total_subnotas = sum(1 for row in note_rows if _clean(row.get("sub_nota")))
    total_principales = total_notas - total_subnotas
    total_complejas = sum(1 for row in note_rows if row.get("estructura_nota") == "Compleja")
    return {
        "package_name": package_name,
        "cliente": package_values.get("cliente"),
        "cliente_label": get_customer_display(package_values.get("cliente")),
        "anio": cint(package_values.get("anio") or 0),
        "mes": package_values.get("mes"),
        "periodo_nombre": package_values.get("periodo_nombre"),
        "estado_preparacion": package_values.get("estado_preparacion") or "Borrador",
        "total_notas": total_notas,
        "total_notas_principales": total_principales,
        "total_subnotas": total_subnotas,
        "total_notas_complejas": total_complejas,
        "next_numero_nota": _next_note_number(note_rows),
        "notes": note_rows,
    }


def _serialize_section(section_doc):
    section = {field: section_doc.get(field) for field in SECTION_EDITABLE_FIELDS}
    section.update(
        {
            "doctype": section_doc.doctype,
            "name": section_doc.name,
            "nombre_seccion": section_doc.nombre_seccion,
            "_client_id": section_doc.name,
            "total_columnas": cint(section_doc.total_columnas or 0),
            "total_filas": cint(section_doc.total_filas or 0),
            "total_celdas": cint(section_doc.total_celdas or 0),
            "columnas_tabulares": [_serialize_child_row(row) for row in (section_doc.columnas_tabulares or [])],
            "filas_tabulares": [_serialize_child_row(row) for row in (section_doc.filas_tabulares or [])],
            "celdas_tabulares": sorted(
                [_serialize_child_row(row) for row in (section_doc.celdas_tabulares or [])],
                key=lambda row: (
                    cstr(row.get("codigo_tabla") or ""),
                    cstr(row.get("codigo_fila") or ""),
                    cstr(row.get("codigo_columna") or ""),
                ),
            ),
        }
    )
    return section


def _serialize_note(note_doc):
    if not note_doc:
        return None

    package_values = frappe.db.get_value(
        "Paquete EEFF",
        note_doc.paquete_eeff,
        ["cliente", "anio", "mes", "periodo_nombre", "estado_preparacion"],
        as_dict=True,
    ) or {}
    section_names = frappe.get_all(
        "Seccion Nota EEFF",
        filters={"nota_eeff": note_doc.name},
        pluck="name",
        order_by="orden asc, modified asc",
        limit_page_length=300,
    )
    sections = [_serialize_section(frappe.get_doc("Seccion Nota EEFF", name)) for name in section_names]
    note = {field: note_doc.get(field) for field in NOTE_EDITABLE_FIELDS}
    note.update(
        {
            "doctype": note_doc.doctype,
            "name": note_doc.name,
            "nombre_nota": note_doc.nombre_nota,
            "paquete_eeff": note_doc.paquete_eeff,
            "identificador_nota": build_note_identifier(note_doc.numero_nota, note_doc.sub_nota),
            "cliente": package_values.get("cliente"),
            "cliente_label": get_customer_display(package_values.get("cliente")),
            "anio": cint(package_values.get("anio") or 0),
            "mes": package_values.get("mes"),
            "periodo_nombre": package_values.get("periodo_nombre"),
            "estado_preparacion_paquete": package_values.get("estado_preparacion") or "Borrador",
            "total_secciones_complejas": cint(note_doc.total_secciones_complejas or 0),
            "total_cifras": cint(note_doc.total_cifras or 0),
            "cifras_nota": [_serialize_child_row(row) for row in (note_doc.cifras_nota or [])],
        }
    )
    return {"doc": note, "sections": sections}


def _apply_note_payload(note_doc, payload):
    for fieldname in NOTE_EDITABLE_FIELDS:
        if fieldname not in payload:
            continue
        note_doc.set(fieldname, payload.get(fieldname))

    for fieldname in NOTE_CHILD_TABLES:
        if fieldname not in payload:
            continue
        note_doc.set(fieldname, [])
        for row in payload.get(fieldname) or []:
            sanitized = _clean_payload_row(row)
            if sanitized:
                note_doc.append(fieldname, sanitized)


def _apply_section_payload(section_doc, payload, note_doc):
    section_doc.nota_eeff = note_doc.name
    section_doc.paquete_eeff = note_doc.paquete_eeff
    for fieldname in SECTION_EDITABLE_FIELDS:
        if fieldname not in payload:
            continue
        section_doc.set(fieldname, payload.get(fieldname))

    for fieldname in SECTION_CHILD_TABLES:
        if fieldname not in payload:
            continue
        section_doc.set(fieldname, [])
        for row in payload.get(fieldname) or []:
            sanitized = _clean_payload_row(row)
            if sanitized:
                section_doc.append(fieldname, sanitized)


def _new_default_section(index=1):
    code = f"SEC_{index:02d}"
    return {
        "codigo_seccion": code,
        "tipo_seccion": "Tabla",
        "titulo_seccion": _("Seccion {0}").format(index),
        "orden": index,
        "mostrar_titulo": 1,
        "contenido_narrativo": "",
        "observaciones": "",
        "columnas_tabulares": [],
        "filas_tabulares": [],
        "celdas_tabulares": [],
    }


def _sync_note_sections(note_doc, sections_payload):
    existing_names = set(
        frappe.get_all(
            "Seccion Nota EEFF",
            filters={"nota_eeff": note_doc.name},
            pluck="name",
            limit_page_length=500,
        )
    )
    keep_names = set()
    payload_rows = list(sections_payload or [])
    payload_rows.sort(key=lambda row: (cint((row or {}).get("orden") or 0), cstr((row or {}).get("codigo_seccion") or "")))

    for idx, payload in enumerate(payload_rows, start=1):
        payload = dict(payload or {})
        if not cint(payload.get("orden") or 0):
            payload["orden"] = idx

        section_name = _clean(payload.get("name"))
        if section_name and frappe.db.exists("Seccion Nota EEFF", {"name": section_name, "nota_eeff": note_doc.name}):
            section_doc = frappe.get_doc("Seccion Nota EEFF", section_name)
            _apply_section_payload(section_doc, payload, note_doc)
            section_doc.save()
        else:
            section_doc = frappe.get_doc({"doctype": "Seccion Nota EEFF"})
            _apply_section_payload(section_doc, payload, note_doc)
            section_doc.insert()
        keep_names.add(section_doc.name)

    for stale_name in sorted(existing_names - keep_names):
        frappe.delete_doc("Seccion Nota EEFF", stale_name, ignore_permissions=True, force=1)


def _build_bootstrap_payload(cliente=None, anio=None, mes=None, package_name=None, note_doc=None):
    package_name = _clean(package_name) or (_clean(getattr(note_doc, "paquete_eeff", "")) if note_doc else "")

    package_values = None
    if package_name and frappe.db.exists("Paquete EEFF", package_name):
        package_values = frappe.db.get_value(
            "Paquete EEFF",
            package_name,
            ["cliente", "anio", "mes"],
            as_dict=True,
        ) or {}
        cliente = package_values.get("cliente") or cliente
        anio = package_values.get("anio") or anio
        mes = package_values.get("mes") or mes

    clients = _get_clients()
    packages = _get_packages(cliente=cliente, anio=anio, mes=mes)
    notes = _serialize_note_rows(package_name) if package_name else []
    return {
        "cliente": cliente or "",
        "anio": cint(anio or 0),
        "mes": mes or "",
        "package_name": package_name or "",
        "clients": clients,
        "packages": packages,
        "meses": list(MESES),
        "notes": notes,
        "summary": _build_summary(package_name),
        "note": _serialize_note(note_doc) if note_doc else None,
    }


def _create_note_doc(
    package_name,
    numero_nota,
    sub_nota=None,
    titulo=None,
    estructura_nota="Simple",
    contenido_narrativo=None,
    observaciones=None,
    tamano_letra_impresion=12,
    ancho_tabla_impresion="100%",
    alineacion_tabla_impresion="Centro",
):
    if not frappe.db.exists("Paquete EEFF", package_name):
        frappe.throw(_("Debes seleccionar un paquete valido."), title=_("Paquete Invalido"))

    number = normalize_note_number(numero_nota)
    if not number:
        frappe.throw(_("Debes indicar un numero de nota valido."), title=_("Numero Requerido"))

    doc = frappe.get_doc(
        {
            "doctype": "Nota EEFF",
            "paquete_eeff": package_name,
            "numero_nota": number,
            "sub_nota": sub_nota,
            "titulo": titulo or _("Nota {0}").format(number),
            "estructura_nota": cstr(estructura_nota or "Simple").strip() or "Simple",
            "contenido_narrativo": contenido_narrativo or "",
            "observaciones": observaciones or "",
            "tamano_letra_impresion": tamano_letra_impresion or 12,
            "ancho_tabla_impresion": ancho_tabla_impresion or "100%",
            "alineacion_tabla_impresion": alineacion_tabla_impresion or "Centro",
            "estado_aprobacion": "Borrador",
        }
    )
    doc.insert()
    return doc


@frappe.whitelist()
def get_note_editor_bootstrap(cliente=None, anio=None, mes=None, package_name=None, note_name=None):
    _ensure_page_access()

    note_doc = None
    if _clean(note_name):
        if not frappe.db.exists("Nota EEFF", note_name):
            frappe.throw(_("La nota indicada no existe."), title=_("Nota Invalida"))
        note_doc = frappe.get_doc("Nota EEFF", note_name)
        package_name = note_doc.paquete_eeff

    return _build_bootstrap_payload(
        cliente=cliente,
        anio=anio,
        mes=mes,
        package_name=package_name,
        note_doc=note_doc,
    )


@frappe.whitelist()
def create_note_for_editor(
    package_name,
    numero_nota,
    sub_nota=None,
    titulo=None,
    estructura_nota="Simple",
    contenido_narrativo=None,
    observaciones=None,
    tamano_letra_impresion=12,
    ancho_tabla_impresion="100%",
    alineacion_tabla_impresion="Centro",
):
    _ensure_page_access(write=True)

    note_doc = _create_note_doc(
        package_name=package_name,
        numero_nota=numero_nota,
        sub_nota=sub_nota,
        titulo=titulo,
        estructura_nota=estructura_nota,
        contenido_narrativo=contenido_narrativo,
        observaciones=observaciones,
        tamano_letra_impresion=tamano_letra_impresion,
        ancho_tabla_impresion=ancho_tabla_impresion,
        alineacion_tabla_impresion=alineacion_tabla_impresion,
    )
    if cstr(note_doc.estructura_nota or "Simple").strip() == "Compleja":
        _sync_note_sections(note_doc, [_new_default_section(1)])
        note_doc.reload()

    return _build_bootstrap_payload(package_name=package_name, note_doc=note_doc)


@frappe.whitelist()
def save_note_editor(note_payload):
    _ensure_page_access(write=True)

    payload = frappe.parse_json(note_payload) if isinstance(note_payload, str) else note_payload
    payload = payload or {}
    doc_payload = payload.get("doc") if isinstance(payload, dict) and payload.get("doc") else payload
    sections_payload = payload.get("sections") if isinstance(payload, dict) else None

    note_name = _clean((doc_payload or {}).get("name"))
    if not note_name or not frappe.db.exists("Nota EEFF", note_name):
        frappe.throw(_("La nota indicada no existe."), title=_("Nota Invalida"))

    note_doc = frappe.get_doc("Nota EEFF", note_name)
    _apply_note_payload(note_doc, doc_payload or {})
    note_doc.save()

    if cstr(note_doc.estructura_nota or "Simple").strip() == "Compleja":
        _sync_note_sections(note_doc, sections_payload or [])
    else:
        _sync_note_sections(note_doc, [])

    note_doc.reload()
    return _build_bootstrap_payload(package_name=note_doc.paquete_eeff, note_doc=note_doc)


@frappe.whitelist()
def get_note_wizard_bootstrap(cliente=None, anio=None, mes=None, package_name=None):
    data = get_note_editor_bootstrap(cliente=cliente, anio=anio, mes=mes, package_name=package_name)
    return {
        "cliente": data.get("cliente"),
        "anio": data.get("anio"),
        "mes": data.get("mes"),
        "package_name": data.get("package_name"),
        "clients": data.get("clients") or [],
        "packages": data.get("packages") or [],
        "meses": data.get("meses") or list(MESES),
        "status": data.get("summary"),
        "notes": data.get("notes") or [],
        "note": data.get("note"),
    }


@frappe.whitelist()
def crear_nota_desde_asistente(
    package_name,
    numero_nota,
    sub_nota=None,
    titulo=None,
    estructura_nota="Simple",
    contenido_narrativo=None,
    observaciones=None,
    secciones=None,
):
    _ensure_page_access(write=True)

    note_doc = _create_note_doc(
        package_name=package_name,
        numero_nota=numero_nota,
        sub_nota=sub_nota,
        titulo=titulo,
        estructura_nota=estructura_nota,
        contenido_narrativo=contenido_narrativo,
        observaciones=observaciones,
    )

    section_payloads = frappe.parse_json(secciones) if isinstance(secciones, str) and _clean(secciones) else (secciones or [])
    if cstr(note_doc.estructura_nota or "Simple").strip() == "Compleja":
        _sync_note_sections(note_doc, section_payloads or [_new_default_section(1)])
        note_doc.reload()

    return {
        "note_name": note_doc.name,
        "estructura_nota": note_doc.estructura_nota,
        "secciones_creadas": len(section_payloads or []),
        "status": _build_summary(package_name),
    }
