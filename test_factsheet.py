import frappe

def test():
    frappe.init(site="frappe.local")
    frappe.connect()

    fs = frappe.get_doc("Factsheet", "VAL - Paquete-MIDESA-Febrero-2026")
    print("Before validate:")
    for row in fs.lineas:
        if row.codigo_linea == "VALIDACION_BG":
            print("monto_actual:", row.monto_actual)

    fs.validate()

    print("After validate:")
    for row in fs.lineas:
        if row.codigo_linea == "VALIDACION_BG":
            print("monto_actual:", row.monto_actual)
