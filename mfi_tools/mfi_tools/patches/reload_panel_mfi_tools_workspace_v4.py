import frappe


def execute():
    frappe.reload_doc("mfi_tools", "workspace", "panel_mfi_tools", force=True)
    frappe.clear_cache()
