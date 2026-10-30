import json
import frappe


DOCTYPES = (
    ("estado_financiero_eeff", "Estado Financiero EEFF"),
    ("nota_eeff", "Nota EEFF"),
    ("seccion_nota_eeff", "Seccion Nota EEFF"),
    ("factsheet", "Factsheet"),
)


def _table_exists(doctype_name):
    table_name = f"tab{doctype_name}"
    return bool(frappe.db.sql("SHOW TABLES LIKE %s", table_name))


def _sync_list_view_settings(doctype_name):
    if _table_exists("Property Setter"):
        frappe.db.sql(
            """
            DELETE FROM `tabProperty Setter`
            WHERE doc_type = %s
              AND (
                  (field_name IN ('mes', 'anio') AND property = 'in_list_view')
                  OR property IN ('field_order', 'title_field')
              )
            """,
            (doctype_name,),
        )

    if not _table_exists("List View Settings") or not frappe.db.exists("List View Settings", doctype_name):
        return

    raw_fields = frappe.db.get_value("List View Settings", doctype_name, "fields")
    total_fields = frappe.db.get_value("List View Settings", doctype_name, "total_fields") or 4
    if not raw_fields:
        return

    try:
        fields = json.loads(raw_fields)
    except Exception:
        return

    if not isinstance(fields, list):
        return

    existing_fieldnames = {item.get("fieldname") for item in fields if isinstance(item, dict)}
    to_insert = []
    if "mes" not in existing_fieldnames:
        to_insert.append({"fieldname": "mes", "label": "Mes"})
    if "anio" not in existing_fieldnames:
        to_insert.append({"fieldname": "anio", "label": "Anio"})

    if to_insert:
        insert_idx = 1 if fields else 0
        for idx, item in enumerate(fields):
            if isinstance(item, dict) and item.get("fieldname") == "paquete_eeff":
                insert_idx = idx + 1
                break
        fields[insert_idx:insert_idx] = to_insert
        new_total = min(max(int(total_fields), insert_idx + len(to_insert), 6), 10)
        frappe.db.set_value(
            "List View Settings",
            doctype_name,
            {
                "fields": json.dumps(fields),
                "total_fields": new_total,
            },
            update_modified=False,
        )


def execute():
    for module_doc, doctype_name in DOCTYPES:
        try:
            frappe.reload_doc("mfi_tools", "doctype", module_doc, force=True)
        except Exception:
            pass

    if not _table_exists("Paquete EEFF"):
        return

    if not all(frappe.db.has_column("Paquete EEFF", col) for col in ("mes", "anio")):
        return

    if _table_exists("Seccion Nota EEFF") and _table_exists("Nota EEFF"):
        if frappe.db.has_column("Seccion Nota EEFF", "paquete_eeff") and frappe.db.has_column("Seccion Nota EEFF", "nota_eeff"):
            frappe.db.sql(
                """
                UPDATE `tabSeccion Nota EEFF` AS sec
                INNER JOIN `tabNota EEFF` AS nota
                    ON nota.name = sec.nota_eeff
                SET sec.paquete_eeff = nota.paquete_eeff
                WHERE COALESCE(sec.paquete_eeff, '') = ''
                  AND COALESCE(nota.paquete_eeff, '') != ''
                """
            )

    for _module_doc, doctype_name in DOCTYPES:
        if not _table_exists(doctype_name):
            continue
        if not all(frappe.db.has_column(doctype_name, col) for col in ("paquete_eeff", "mes", "anio")):
            continue

        frappe.db.sql(
            f"""
            UPDATE `tab{doctype_name}` AS target
            INNER JOIN `tabPaquete EEFF` AS pkg
                ON pkg.name = target.paquete_eeff
            SET
                target.mes = pkg.mes,
                target.anio = pkg.anio
            """
        )
        _sync_list_view_settings(doctype_name)

    frappe.clear_cache()
