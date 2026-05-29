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


def _ensure_basic_inputs(cliente, anio, mes):
    cliente = _clean(cliente)
    if not cliente:
        frappe.throw(_("Debes indicar un cliente."), title=_("Cliente Requerido"))
    return cliente, _year_or_throw(anio), _month_or_throw(mes)


def _get_clients():
    values = set()
    for doctype in ("Paquete EEFF", "Balanza Comprobacion EEFF"):
        rows = frappe.get_all(
            doctype,
            fields=["cliente"],
            filters={"cliente": ["is", "set"]},
            distinct=True,
            limit_page_length=2000,
        )
        for row in rows:
            cliente = _clean(row.cliente)
            if cliente:
                values.add(cliente)
    output = sorted(values)
    display_map = get_customer_display_map(output)
    return [{"value": row, "label": display_map.get(row, row)} for row in output]


def _build_filters(cliente=None, anio=None, mes=None):
    filters = {}
    if _clean(cliente):
        filters["cliente"] = _clean(cliente)
    if cint(anio or 0):
        filters["anio"] = cint(anio)
    if _clean(mes):
        filters["mes"] = _clean(mes)
    return filters


def _get_packages(cliente=None, anio=None, mes=None):
    rows = frappe.get_all(
        "Paquete EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes),
        fields=[
            "name",
            "cliente",
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
    customer_labels = get_customer_display_map([row.cliente for row in rows])
    return [
        {
            "value": row.name,
            "label": f"{row.name} | {customer_labels.get(row.cliente, row.cliente) or '-'} | {row.mes or '-'} {row.anio or '-'} | {row.estado_preparacion or 'Borrador'}",
            "cliente": row.cliente,
            "cliente_label": customer_labels.get(row.cliente, row.cliente),
            "anio": row.anio,
            "mes": row.mes,
            "periodo_nombre": row.periodo_nombre,
            "balanza": row.balanza_comprobacion_eeff,
            "balanza_comparativa": row.balanza_comparativa_eeff,
        }
        for row in rows
    ]


def _get_balanzas(cliente=None, anio=None, mes=None):
    rows = frappe.get_all(
        "Balanza Comprobacion EEFF",
        filters=_build_filters(cliente=cliente, anio=anio, mes=mes),
        fields=[
            "name",
            "cliente",
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
    customer_labels = get_customer_display_map([row.cliente for row in rows])
    return [
        {
            "value": row.name,
            "label": f"{row.name} | {customer_labels.get(row.cliente, row.cliente) or '-'} | {row.mes or '-'} {row.anio or '-'} | Lineas: {cint(row.total_lineas or 0)}",
            "cliente": row.cliente,
            "cliente_label": customer_labels.get(row.cliente, row.cliente),
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
        status["cliente"] = package.cliente
        status["cliente_label"] = get_customer_display(package.cliente)
        status["estado_preparacion"] = package.estado_preparacion
        status["total_estados"] = cint(package.total_estados or 0)
        status["total_notas"] = cint(package.total_notas or 0)
        status["reglas_activas"] = frappe.db.count("Regla Mapeo Contable EEFF", {"company": package.company, "activo": 1})
        if package.balanza_comprobacion_eeff:
            status["balanza_name"] = package.balanza_comprobacion_eeff

    if status["balanza_name"] and frappe.db.exists("Balanza Comprobacion EEFF", status["balanza_name"]):
        balanza = frappe.get_doc("Balanza Comprobacion EEFF", status["balanza_name"])
        status["balanza_name"] = balanza.name
        status["periodo_nombre"] = status["periodo_nombre"] or balanza.periodo_nombre
        status["cliente"] = status["cliente"] or balanza.cliente
        status["cliente_label"] = status.get("cliente_label") or get_customer_display(balanza.cliente)
        status["total_lineas"] = cint(balanza.total_lineas or 0)
        status["total_debe"] = balanza.total_debe or 0
        status["total_haber"] = balanza.total_haber or 0
        status["cuadra"] = cint(balanza.cuadra or 0)
        status["tasas_cambio"] = []
        status["total_tasas_cambio"] = 0
        status["moneda_tasa_cambio"] = cstr(balanza.moneda or "").strip().upper() or "USD"
        status["tasa_cambio"] = 1.0

    return status


def _find_or_create_balanza(cliente, anio, mes, balanza_name=None):
    if _clean(balanza_name) and frappe.db.exists("Balanza Comprobacion EEFF", balanza_name):
        return frappe.get_doc("Balanza Comprobacion EEFF", balanza_name)

    existing = frappe.get_all(
        "Balanza Comprobacion EEFF",
        filters={"cliente": cliente, "anio": anio, "mes": mes},
        pluck="name",
        order_by="modified desc",
        limit_page_length=1,
    )
    if existing:
        return frappe.get_doc("Balanza Comprobacion EEFF", existing[0])

    doc = frappe.get_doc(
        {
            "doctype": "Balanza Comprobacion EEFF",
            "cliente": cliente,
            "anio": anio,
            "mes": mes,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _find_or_create_package(cliente, anio, mes, balanza_doc, package_name=None):
    if _clean(package_name) and frappe.db.exists("Paquete EEFF", package_name):
        doc = frappe.get_doc("Paquete EEFF", package_name)
    else:
        existing = frappe.get_all(
            "Paquete EEFF",
            filters={"cliente": cliente, "anio": anio, "mes": mes},
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
                    "cliente": cliente,
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
        cliente=package_doc.cliente,
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
