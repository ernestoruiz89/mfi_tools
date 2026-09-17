import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff import cargar_balanza_csv
from mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff import ejecutar_mapeo
from mfi_tools.mfi_tools.utils.customer import get_customer_display, get_customer_display_map

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


def _clean(value):
    return cstr(value or "").strip()


def _month_or_throw(mes):
    mes = _clean(mes)
    if mes not in MESES:
        frappe.throw(_("Debes seleccionar un mes valido."), title=_("Mes Invalido"))
    return mes


def _year_or_throw(anio):
    anio = cint(anio or 0)
    if anio < 1900 or anio > 2200:
        frappe.throw(_("Debes indicar un anio valido."), title=_("Anio Invalido"))
    return anio


def _get_entity_display(name):
    name = _clean(name)
    if not name:
        return ""
    if frappe.db.exists("Company", name):
        c_name = frappe.db.get_value("Company", name, "company_name")
        return cstr(c_name or name).strip()
    return get_customer_display(name) or name


def _get_entity_display_map(names):
    mapping = {}
    for name in names:
        mapping[name] = _get_entity_display(name)
    return mapping


def _ensure_basic_inputs(cliente, anio, mes):
    cliente = _clean(cliente)
    if not cliente:
        frappe.throw(_("Debes indicar una compañía o cliente."), title=_("Compañía Requerida"))
    return cliente, _year_or_throw(anio), _month_or_throw(mes)


def _get_clients():
    values = set()
    for doctype in ("Paquete EEFF", "Balanza Comprobacion EEFF"):
        meta = frappe.get_meta(doctype)
        field = "company" if meta.has_field("company") else ("cliente" if meta.has_field("cliente") else None)
        if not field:
            continue
        rows = frappe.get_all(
            doctype,
            fields=[field],
            filters={field: ["is", "set"]},
            distinct=True,
            limit_page_length=2000,
        )
        for row in rows:
            val = _clean(row.get(field))
            if val:
                values.add(val)
    if not values and frappe.db.exists("DocType", "Company"):
        for row in frappe.get_all("Company", fields=["name"], limit_page_length=100):
            values.add(row.name)
    output = sorted(values)
    display_map = _get_entity_display_map(output)
    return [{"value": row, "label": display_map.get(row, row)} for row in output]


def _build_filters(cliente=None, anio=None, mes=None, doctype="Paquete EEFF"):
    filters = {}
    if _clean(cliente):
        meta = frappe.get_meta(doctype)
        field = "company" if meta.has_field("company") else "cliente"
        filters[field] = _clean(cliente)
    if cint(anio or 0):
        filters["anio"] = cint(anio)
    if _clean(mes):
        filters["mes"] = _clean(mes)
    return filters


def _get_packages(cliente=None, anio=None, mes=None):
    meta = frappe.get_meta("Paquete EEFF")
    entity_field = "company" if meta.has_field("company") else "cliente"
    rows = frappe.get_all(
        "Paquete EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes, doctype="Paquete EEFF"),
        fields=[
            "name",
            entity_field,
            "anio",
            "mes",
            "periodo_nombre",
            "balanza_comprobacion_eeff",
            "balanza_comparativa_eeff",
            "estado_preparacion",
            "total_estados",
            "total_notas",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=500,
    )
    customer_labels = _get_entity_display_map([row.get(entity_field) for row in rows])
    return [
        {
            "value": row.name,
            "label": f"{row.name} | {customer_labels.get(row.get(entity_field), row.get(entity_field)) or '-'} | {row.mes or '-'} {row.anio or '-'} | {row.estado_preparacion or 'Borrador'}",
            "cliente": row.get(entity_field),
            "cliente_label": customer_labels.get(row.get(entity_field), row.get(entity_field)),
            "anio": row.anio,
            "mes": row.mes,
            "periodo_nombre": row.periodo_nombre,
            "balanza": row.balanza_comprobacion_eeff,
            "balanza_comparativa": row.balanza_comparativa_eeff,
        }
        for row in rows
    ]


def _get_balanzas(cliente=None, anio=None, mes=None):
    meta = frappe.get_meta("Balanza Comprobacion EEFF")
    entity_field = "company" if meta.has_field("company") else "cliente"
    rows = frappe.get_all(
        "Balanza Comprobacion EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes, doctype="Balanza Comprobacion EEFF"),
        fields=[
            "name",
            entity_field,
            "anio",
            "mes",
            "periodo_nombre",
            "total_lineas",
            "cuadra",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=500,
    )
    customer_labels = _get_entity_display_map([row.get(entity_field) for row in rows])
    return [
        {
            "value": row.name,
            "label": f"{row.name} | {customer_labels.get(row.get(entity_field), row.get(entity_field)) or '-'} | {row.mes or '-'} {row.anio or '-'} | Lineas: {cint(row.total_lineas or 0)}",
            "cliente": row.get(entity_field),
            "cliente_label": customer_labels.get(row.get(entity_field), row.get(entity_field)),
            "anio": row.anio,
            "mes": row.mes,
            "periodo_nombre": row.periodo_nombre,
            "total_lineas": cint(row.total_lineas or 0),
            "cuadra": cint(row.cuadra or 0),
        }
        for row in rows
    ]


def _build_status(package_name=None, balanza_name=None):
    status = {
        "package_name": package_name,
        "balanza_name": balanza_name,
        "periodo_nombre": None,
        "estado_preparacion": None,
        "total_estados": 0,
        "total_notas": 0,
        "reglas_activas": 0,
        "total_lineas": 0,
        "total_debe": 0,
        "total_haber": 0,
        "cuadra": 0,
        "moneda_tasa_cambio": "USD",
        "tasa_cambio": 1,
        "total_tasas_cambio": 0,
        "tasas_cambio": [],
    }

    if package_name and frappe.db.exists("Paquete EEFF", package_name):
        package = frappe.get_doc("Paquete EEFF", package_name)
        status["package_name"] = package.name
        status["periodo_nombre"] = package.periodo_nombre
        entity_val = package.get("company") or package.get("cliente")
        status["cliente"] = entity_val
        status["cliente_label"] = _get_entity_display(entity_val)
        status["estado_preparacion"] = package.estado_preparacion
        status["total_estados"] = cint(package.total_estados or 0)
        status["total_notas"] = cint(package.total_notas or 0)
        status["reglas_activas"] = frappe.db.count("Regla Mapeo Contable EEFF", {"company": entity_val, "activo": 1})
        if package.balanza_comprobacion_eeff:
            status["balanza_name"] = package.balanza_comprobacion_eeff

    if status["balanza_name"] and frappe.db.exists("Balanza Comprobacion EEFF", status["balanza_name"]):
        balanza = frappe.get_doc("Balanza Comprobacion EEFF", status["balanza_name"])
        status["balanza_name"] = balanza.name
        status["periodo_nombre"] = status["periodo_nombre"] or balanza.periodo_nombre
        entity_val = status["cliente"] or balanza.get("company") or balanza.get("cliente")
        status["cliente"] = entity_val
        status["cliente_label"] = status.get("cliente_label") or _get_entity_display(entity_val)
        status["total_lineas"] = cint(balanza.total_lineas or 0)
        status["total_debe"] = balanza.total_debe or 0
        status["total_haber"] = balanza.total_haber or 0
        status["cuadra"] = cint(balanza.cuadra or 0)
        tasas = []
        for row in balanza.get("tasas_cambio") or []:
            moneda = cstr(getattr(row, "moneda", "") or "").strip().upper()
            if not moneda:
                continue
            tasas.append(
                {
                    "moneda": moneda,
                    "tasa_cambio": flt(getattr(row, "tasa_cambio", 0) or 0) or 1,
                }
            )

        status["tasas_cambio"] = tasas
        status["total_tasas_cambio"] = len(tasas)
        first_moneda = tasas[0]["moneda"] if tasas else "USD"
        status["moneda_tasa_cambio"] = first_moneda
        status["tasa_cambio"] = balanza.get_tasa_cambio(moneda=first_moneda, fallback=1)

    return status


def _find_or_create_balanza(cliente, anio, mes, balanza_name=None):
    if _clean(balanza_name) and frappe.db.exists("Balanza Comprobacion EEFF", balanza_name):
        return frappe.get_doc("Balanza Comprobacion EEFF", balanza_name)

    meta = frappe.get_meta("Balanza Comprobacion EEFF")
    entity_field = "company" if meta.has_field("company") else "cliente"
    existing = frappe.get_all(
        "Balanza Comprobacion EEFF",
        filters={entity_field: cliente, "anio": anio, "mes": mes},
        pluck="name",
        order_by="modified desc",
        limit_page_length=1,
    )
    if existing:
        return frappe.get_doc("Balanza Comprobacion EEFF", existing[0])

    doc_args = {
        "doctype": "Balanza Comprobacion EEFF",
        entity_field: cliente,
        "anio": anio,
        "mes": mes,
    }
    doc = frappe.get_doc(doc_args)
    doc.insert(ignore_permissions=True)
    return doc


def _find_or_create_package(cliente, anio, mes, balanza_doc, package_name=None):
    if _clean(package_name) and frappe.db.exists("Paquete EEFF", package_name):
        doc = frappe.get_doc("Paquete EEFF", package_name)
    else:
        meta = frappe.get_meta("Paquete EEFF")
        entity_field = "company" if meta.has_field("company") else "cliente"
        existing = frappe.get_all(
            "Paquete EEFF",
            filters={entity_field: cliente, "anio": anio, "mes": mes},
            pluck="name",
            order_by="modified desc",
            limit_page_length=1,
        )
        if existing:
            doc = frappe.get_doc("Paquete EEFF", existing[0])
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "Paquete EEFF",
                    entity_field: cliente,
                    "anio": anio,
                    "mes": mes,
                    "balanza_comprobacion_eeff": balanza_doc.name,
                }
            )
            doc.insert(ignore_permissions=True)

    if doc.balanza_comprobacion_eeff != balanza_doc.name:
        doc.balanza_comprobacion_eeff = balanza_doc.name
        doc.save(ignore_permissions=True)

    return doc


def _prepare_docs(cliente, anio, mes, package_name=None, balanza_name=None):
    cliente, anio, mes = _ensure_basic_inputs(cliente, anio, mes)
    balanza_doc = _find_or_create_balanza(cliente, anio, mes, balanza_name=balanza_name)
    package_doc = _find_or_create_package(cliente, anio, mes, balanza_doc, package_name=package_name)
    return package_doc, balanza_doc


def _bootstrap_response(cliente=None, anio=None, mes=None, package_name=None, balanza_name=None):
    return {
        "cliente": _clean(cliente) or None,
        "anio": cint(anio or 0) or None,
        "mes": _clean(mes) or None,
        "package_name": package_name,
        "balanza_name": balanza_name,
        "clients": _get_clients(),
        "packages": _get_packages(cliente=cliente, anio=anio, mes=mes),
        "balanzas": _get_balanzas(cliente=cliente, anio=anio, mes=mes),
        "meses": list(MESES),
        "status": _build_status(package_name=package_name, balanza_name=balanza_name),
    }


@frappe.whitelist()
def get_wizard_bootstrap(cliente=None, anio=None, mes=None, package_name=None, balanza_name=None):
    return _bootstrap_response(cliente=cliente, anio=anio, mes=mes, package_name=package_name, balanza_name=balanza_name)


@frappe.whitelist()
def prepare_package(cliente, anio, mes, package_name=None, balanza_name=None):
    package_doc, balanza_doc = _prepare_docs(cliente, anio, mes, package_name=package_name, balanza_name=balanza_name)
    return _bootstrap_response(
        cliente=package_doc.get("company") or package_doc.get("cliente"),
        anio=package_doc.anio,
        mes=package_doc.mes,
        package_name=package_doc.name,
        balanza_name=balanza_doc.name,
    )


@frappe.whitelist()
def upload_balanza_csv_from_wizard(balanza_name, csv_content, tasa_cambio=None, moneda=None):
    result = cargar_balanza_csv(balanza_name, csv_content, tasa_cambio=tasa_cambio, moneda=moneda)
    package_name = frappe.db.get_value("Paquete EEFF", {"balanza_comprobacion_eeff": balanza_name}, "name")
    return {
        "upload": result,
        "status": _build_status(package_name=package_name, balanza_name=balanza_name),
    }


@frappe.whitelist()
def run_mapping_from_wizard(package_name):
    result = ejecutar_mapeo(package_name)
    balanza_name = frappe.db.get_value("Paquete EEFF", package_name, "balanza_comprobacion_eeff")
    return {
        "mapping": result,
        "status": _build_status(package_name=package_name, balanza_name=balanza_name),
    }


@frappe.whitelist()
def one_click_upload_and_map(
    cliente,
    anio,
    mes,
    csv_content,
    package_name=None,
    balanza_name=None,
    tasa_cambio=None,
    moneda=None,
):
    package_doc, balanza_doc = _prepare_docs(cliente, anio, mes, package_name=package_name, balanza_name=balanza_name)
    upload = cargar_balanza_csv(balanza_doc.name, csv_content, tasa_cambio=tasa_cambio, moneda=moneda)
    mapping = ejecutar_mapeo(package_doc.name)
    return {
        "upload": upload,
        "mapping": mapping,
        "status": _build_status(package_name=package_doc.name, balanza_name=balanza_doc.name),
    }
