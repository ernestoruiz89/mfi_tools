import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
    frappe.reload_doc("mfi_tools", "page", "tablero_financiero_eeff", force=True)
    frappe.reload_doc("mfi_tools", "workspace", "panel_mfi_tools", force=True)
    if frappe.db.exists("DocType", "Sidebar"):
        frappe.reload_doc("mfi_tools", "sidebar", "mfi_tools", force=True)
    else:
        import_file_by_path(frappe.get_app_path("mfi_tools", "workspace_sidebar", "panel_mfi_tools.json"), force=True)
