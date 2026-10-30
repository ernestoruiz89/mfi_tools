import frappe


OBSOLETE_PAGES = (
    "asistente-eeff",
    "helper-mapeo-notas-eeff",
)


def execute():
    """Remove obsolete pages and refresh Workspace and Sidebar navigation."""
    from frappe.modules.import_file import import_file_by_path

    for page_name in OBSOLETE_PAGES:
        if frappe.db.exists("Page", page_name):
            frappe.delete_doc("Page", page_name, force=True, ignore_missing=True)

    frappe.reload_doc("mfi_tools", "workspace", "panel_mfi_tools", force=True)
    if frappe.db.exists("DocType", "Sidebar"):
        frappe.reload_doc("mfi_tools", "sidebar", "mfi_tools", force=True)
    else:
        import_file_by_path(
            frappe.get_app_path("mfi_tools", "workspace_sidebar", "panel_mfi_tools.json"),
            force=True,
        )

    frappe.clear_cache()
