
__version__ = "0.2.2"


def check_app_permission():
    """Show the app to Desk users who can read its financial packages."""
    import frappe

    return (
        frappe.session.user != "Guest"
        and frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"
        and bool(frappe.has_permission("Paquete EEFF", ptype="read"))
    )
