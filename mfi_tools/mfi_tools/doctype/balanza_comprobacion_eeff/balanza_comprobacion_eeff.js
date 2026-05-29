frappe.ui.form.on("Balanza Comprobacion EEFF", {
    refresh(frm) {
        set_lineas_read_only(frm);

        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Importar CSV"), () => {
            open_csv_import_dialog(frm);
        });
        frm.add_custom_button(__("Descargar Plantilla"), () => {
            download_balance_template();
        });
        frm.add_custom_button(__("Duplicar a otra Moneda"), () => {
            open_duplicate_dialog(frm, "mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.duplicar_a_moneda");
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

function set_lineas_read_only(frm) {
    frm.set_df_property("lineas", "read_only", 1);
    if (frm.fields_dict.lineas && frm.fields_dict.lineas.grid) {
        frm.fields_dict.lineas.grid.cannot_add_rows = true;
        frm.fields_dict.lineas.grid.only_sortable();
        frm.refresh_field("lineas");
    }
}

function open_csv_import_dialog(frm) {
    const defaultRate = get_default_rate_entry(frm);
    const dialog = new frappe.ui.Dialog({
        title: __("Importar Balanza CSV"),
        fields: [
            {
                fieldname: "adjunto_csv",
                fieldtype: "Attach",
                label: __("Archivo CSV"),
                reqd: 1,
                description: __("Sube un archivo CSV para reemplazar las lineas actuales de la balanza."),
            },
            {
                fieldname: "moneda",
                fieldtype: "Link",
                label: __("Moneda"),
                options: "Currency",
                default: defaultRate.moneda || "USD",
                reqd: 1,
            },
            {
                fieldname: "tasa_cambio",
                fieldtype: "Float",
                label: __("Tasa de Cambio"),
                default: defaultRate.tasa_cambio || 1,
                reqd: 1,
            },
        ],
        primary_action_label: __("Importar"),
        primary_action(values) {
            const file_url = values.adjunto_csv;
            if (!file_url) {
                frappe.msgprint(__("Debes adjuntar un archivo CSV."));
                return;
            }
            fetch_file_and_import(frm, file_url, values.moneda, values.tasa_cambio, dialog);
        },
    });

    dialog.show();
}

function get_default_rate_entry(frm) {
    return {
        moneda: frm.doc.moneda || "USD",
        tasa_cambio: 1,
    };
}

async function fetch_file_and_import(frm, file_url, moneda, tasaCambio, dialog) {
    try {
        const response = await fetch(file_url, { credentials: "same-origin" });
        if (!response.ok) {
            throw new Error(__("No se pudo descargar el archivo CSV adjunto."));
        }

        const content = await response.text();
        if (!content) {
            frappe.msgprint(__("No se pudo leer el archivo CSV adjunto."));
            return;
        }

        frappe.call({
            method: "mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.cargar_balanza_csv",
            args: {
                balanza_name: frm.doc.name,
                csv_content: content,
                moneda,
                tasa_cambio: tasaCambio,
            },
            freeze: true,
            freeze_message: __("Importando balanza..."),
            callback: (callResponse) => {
                dialog.hide();
                frm.reload_doc();
                const data = callResponse.message || {};
                frappe.show_alert({
                    message: __("Balanza importada: {0} lineas | TC {1} {2}", [
                        data.total_lineas || 0,
                        data.moneda_tasa_cambio || moneda || "USD",
                        data.tasa_cambio || tasaCambio || 1,
                    ]),
                    indicator: "green",
                });
            },
        });
    } catch (error) {
        frappe.msgprint(error.message || __("No se pudo importar el archivo CSV."));
    }
}

function download_balance_template() {
    const filename = "plantilla_balanza_comprobacion.csv";
    const csv = `\ufeff${build_balance_csv_template()}`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
    frappe.show_alert({ message: __("Plantilla descargada."), indicator: "green" });
}

function build_balance_csv_template() {
    const rows = [
        [
            "codigo_cuenta",
            "descripcion_cuenta",
            "centro_costo",
            "debe_saldo_anterior",
            "haber_saldo_anterior",
            "debe_mes",
            "haber_mes",
            "debe_saldo",
            "haber_saldo",
        ],
        ["1101", "Caja General", "ADM", "1500.00", "0.00", "250.00", "100.00", "1650.00", "0.00"],
        ["1201", "Cuentas por Cobrar", "COM", "2000.00", "0.00", "500.00", "200.00", "2300.00", "0.00"],
        ["6101", "Gasto Administrativo", "ADM", "0.00", "0.00", "300.00", "0.00", "300.00", "0.00"],
        ["2101", "Proveedores", "BOD", "0.00", "1800.00", "400.00", "900.00", "0.00", "2300.00"],
        ["3101", "Capital Social", "", "0.00", "1650.00", "0.00", "0.00", "0.00", "1650.00"],
        ["4101", "Ingresos Operativos", "", "0.00", "0.00", "0.00", "500.00", "0.00", "500.00"],
    ];
    return rows.map((row) => to_csv_row(row)).join("\n");
}

function to_csv_row(row) {
    return (row || [])
        .map((value) => `"${String(value ?? "").replace(/"/g, "\"\"")}"`)
        .join(",");
}
