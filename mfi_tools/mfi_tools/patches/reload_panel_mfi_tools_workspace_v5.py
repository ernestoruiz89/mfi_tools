import frappe


def execute():
    """Refresh the v16 home panel for sites that already installed MFI Tools."""
    frappe.reload_doc("mfi_tools", "workspace", "panel_mfi_tools", force=True)
    frappe.clear_cache()
