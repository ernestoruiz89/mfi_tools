import frappe
from frappe.utils import cstr


def get_customer_display(customer):
    customer = cstr(customer or "").strip()
    if not customer:
        return ""
    customer_name = frappe.db.get_value("Customer", customer, "customer_name")
    return cstr(customer_name or customer).strip()


def get_customer_display_map(customers):
    names = sorted({cstr(customer or "").strip() for customer in (customers or []) if cstr(customer or "").strip()})
    if not names:
        return {}

    rows = frappe.get_all(
        "Customer",
        filters={"name": ["in", names]},
        fields=["name", "customer_name"],
        limit_page_length=max(len(names), 1),
    )
    mapping = {cstr(row.name).strip(): cstr(row.customer_name or row.name).strip() for row in rows}
    for name in names:
        mapping.setdefault(name, name)
    return mapping
