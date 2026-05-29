import frappe


def _table_exists(doctype_name):
    table_name = f"tab{doctype_name}"
    return bool(frappe.db.sql("SHOW TABLES LIKE %s", table_name))


def execute():
    child_table = "Linea Balanza Comprobacion EEFF"
    parent_table = "Balanza Comprobacion EEFF"

    if not _table_exists(child_table) or not _table_exists(parent_table):
        return

    child_columns = ("debe", "haber", "debe_saldo", "haber_saldo", "saldo")
    if not all(frappe.db.has_column(child_table, column) for column in child_columns):
        return

    frappe.db.sql(
        """
        UPDATE `tabLinea Balanza Comprobacion EEFF`
        SET
            debe_saldo = CASE
                WHEN COALESCE(debe_saldo, 0) = 0 AND COALESCE(haber_saldo, 0) = 0
                    THEN COALESCE(debe, 0)
                ELSE COALESCE(debe_saldo, 0)
            END,
            haber_saldo = CASE
                WHEN COALESCE(debe_saldo, 0) = 0 AND COALESCE(haber_saldo, 0) = 0
                    THEN COALESCE(haber, 0)
                ELSE COALESCE(haber_saldo, 0)
            END
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabLinea Balanza Comprobacion EEFF`
        SET saldo = COALESCE(debe_saldo, 0) - COALESCE(haber_saldo, 0)
        """
    )

    parent_columns = ("total_lineas", "total_debe", "total_haber", "cuadra", "estado_balanza")
    if not all(frappe.db.has_column(parent_table, column) for column in parent_columns):
        return

    frappe.db.sql(
        """
        UPDATE `tabBalanza Comprobacion EEFF` AS balanza
        LEFT JOIN (
            SELECT
                parent,
                COUNT(*) AS total_lineas,
                SUM(COALESCE(debe_saldo, 0)) AS total_debe,
                SUM(COALESCE(haber_saldo, 0)) AS total_haber
            FROM `tabLinea Balanza Comprobacion EEFF`
            WHERE parenttype = 'Balanza Comprobacion EEFF'
            GROUP BY parent
        ) AS lineas
            ON lineas.parent = balanza.name
        SET
            balanza.total_lineas = COALESCE(lineas.total_lineas, 0),
            balanza.total_debe = COALESCE(lineas.total_debe, 0),
            balanza.total_haber = COALESCE(lineas.total_haber, 0),
            balanza.cuadra = CASE
                WHEN ABS(COALESCE(lineas.total_debe, 0) - COALESCE(lineas.total_haber, 0)) < 0.0001 THEN 1
                ELSE 0
            END,
            balanza.estado_balanza = CASE
                WHEN COALESCE(lineas.total_lineas, 0) > 0 THEN 'Cargada'
                ELSE balanza.estado_balanza
            END
        """
    )
