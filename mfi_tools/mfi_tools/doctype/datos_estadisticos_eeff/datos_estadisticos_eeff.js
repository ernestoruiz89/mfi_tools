frappe.ui.form.on("Datos Estadisticos EEFF", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Duplicar a otra Moneda"), () => {
            open_duplicate_dialog(frm, "mfi_tools.mfi_tools.doctype.datos_estadisticos_eeff.datos_estadisticos_eeff.duplicar_a_moneda");
        });
    },
});

function open_duplicate_dialog(frm, method) {
    const dialog = new frappe.ui.Dialog({
        title: __("Duplicar a otra Moneda"),
        fields: [
            {
                fieldname: "moneda_destino",
                fieldtype: "Link",
                label: __("Moneda Destino"),
                options: "Currency",
                reqd: 1
            },
            {
                fieldname: "tasa_cambio",
                fieldtype: "Float",
                label: __("Tasa de Cambio"),
                default: 1,
                reqd: 1
            },
            {
                fieldname: "operacion",
                fieldtype: "Select",
                label: __("Operacion"),
                options: "Dividir\nMultiplicar",
                default: "Dividir",
                reqd: 1,
                description: __("Si conviertes de moneda local a extranjera, normalmente Divides.")
            }
        ],
        primary_action_label: __("Duplicar"),
        primary_action(values) {
            frappe.call({
                method: method,
                args: {
                    docname: frm.doc.name,
                    moneda_destino: values.moneda_destino,
                    tasa_cambio: values.tasa_cambio,
                    operacion: values.operacion
                },
                freeze: true,
                freeze_message: __("Duplicando..."),
                callback: (r) => {
                    dialog.hide();
                    if (r.message) {
                        frappe.set_route("Form", frm.doc.doctype, r.message);
                        frappe.show_alert({ message: __("Documento duplicado con exito."), indicator: "green" });
                    }
                }
            });
        }
    });
    dialog.show();
}
