import frappe


def _table_exists(doctype_name):
    table_name = f"tab{doctype_name}"
    return bool(frappe.db.sql("SHOW TABLES LIKE %s", table_name))


def execute():
    child_table = "Linea Balanza Comprobacion EEFF"

    if not _table_exists(child_table):
        return

    required_columns = (
        "debe_saldo_anterior",
        "haber_saldo_anterior",
        "saldo_anterior",
        "debe_mes",
        "haber_mes",
        "movimiento_del_mes",
    )
    if not all(frappe.db.has_column(child_table, column) for column in required_columns):
        return

    frappe.db.sql(
        """
        UPDATE `tabLinea Balanza Comprobacion EEFF`
        SET
            saldo_anterior = COALESCE(debe_saldo_anterior, 0) - COALESCE(haber_saldo_anterior, 0),
            movimiento_del_mes = COALESCE(debe_mes, 0) - COALESCE(haber_mes, 0)
        """
    )
