import frappe


def execute():
    """Remove the child-table list link and refresh navigation on both v16 shells."""
    from frappe.modules.import_file import import_file_by_path

    frappe.reload_doc("mfi_tools", "workspace", "panel_mfi_tools", force=True)
    if frappe.db.exists("DocType", "Sidebar"):
        frappe.reload_doc("mfi_tools", "sidebar", "mfi_tools", force=True)
    else:
        import_file_by_path(
            frappe.get_app_path("mfi_tools", "workspace_sidebar", "panel_mfi_tools.json"),
            force=True,
        )

    if frappe.db.get_value("Desktop Icon", "MFI Tools", "standard"):
        frappe.db.set_value("Desktop Icon", "MFI Tools", "link", "/desk/panel-mfi-tools")
    frappe.clear_cache()
