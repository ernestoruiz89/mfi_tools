frappe.ui.form.on("Balanza Comprobacion EEFF", {
    refresh(frm) {
        set_lineas_read_only(frm);

        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Importar Excel / CSV"), () => {
            open_import_dialog(frm);
        });

        frm.add_custom_button(__("Plantilla Excel"), () => {
            download_balance_excel_template(frm);
        }, __("Plantillas"));

        frm.add_custom_button(__("Plantilla CSV"), () => {
            download_balance_template();
        }, __("Plantillas"));

        frm.add_custom_button(__("Descargar Excel"), () => {
            download_balance_excel(frm);
        });

        frm.add_custom_button(__("Duplicar a otra Moneda"), () => {
            open_duplicate_dialog(frm, "mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.duplicar_a_moneda");
        });
    },
    tasas_cambio_add(frm, cdt, cdn) {
        set_default_moneda_tasa_cambio(cdt, cdn);
    },
});

frappe.ui.form.on("Tasa Cambio Balanza EEFF", {
    tasas_cambio_add(frm, cdt, cdn) {
        set_default_moneda_tasa_cambio(cdt, cdn);
    },
});

function set_default_moneda_tasa_cambio(cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    if (row && !row.moneda) {
        frappe.model.set_value(cdt, cdn, "moneda", "USD");
    }
}

function open_duplicate_dialog(frm, method) {
    const dialog = new frappe.ui.Dialog({
        title: __("Duplicar a otra Moneda"),
        fields: [
            {
                fieldname: "moneda_destino",
                fieldtype: "Link",
                label: __("Moneda Destino"),
                options: "Currency",
                reqd: 1,
            },
            {
                fieldname: "tasa_cambio",
                fieldtype: "Float",
                label: __("Tasa de Cambio"),
                default: 1,
                reqd: 1,
            },
            {
                fieldname: "operacion",
                fieldtype: "Select",
                label: __("Operacion"),
                options: "Dividir\nMultiplicar",
                default: "Dividir",
                reqd: 1,
                description: __("Si conviertes de moneda local a extranjera, normalmente Divides."),
            },
        ],
        primary_action_label: __("Duplicar"),
        primary_action(values) {
            frappe.call({
                method: method,
                args: {
                    docname: frm.doc.name,
                    moneda_destino: values.moneda_destino,
                    tasa_cambio: values.tasa_cambio,
                    operacion: values.operacion,
                },
                freeze: true,
                freeze_message: __("Duplicando..."),
                callback: (r) => {
                    dialog.hide();
                    if (r.message) {
                        frappe.set_route("Form", frm.doc.doctype, r.message);
                        frappe.show_alert({ message: __("Documento duplicado con exito."), indicator: "green" });
                    }
                },
            });
        },
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

function open_import_dialog(frm) {
    const defaultRate = get_default_rate_entry(frm);
    const dialog = new frappe.ui.Dialog({
        title: __("Importar Balanza (Excel o CSV)"),
        fields: [
            {
                fieldname: "adjunto",
                fieldtype: "Attach",
                label: __("Archivo Excel o CSV"),
                reqd: 1,
                description: __("Sube un archivo de Excel (.xlsx, .xls) o CSV para reemplazar las lineas de la balanza."),
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
            const file_url = values.adjunto;
            if (!file_url) {
                frappe.msgprint(__("Debes adjuntar un archivo Excel o CSV."));
                return;
            }
            import_balance_file(frm, file_url, values.moneda, values.tasa_cambio, dialog);
        },
    });

    dialog.show();
}

// Backward compatibility alias
function open_csv_import_dialog(frm) {
    open_import_dialog(frm);
}

function get_default_rate_entry(frm) {
    const rates = frm.doc.tasas_cambio || [];
    if (!rates.length) {
        return { moneda: "USD", tasa_cambio: 1 };
    }
    const first = rates[0] || {};
    return {
        moneda: first.moneda || "USD",
        tasa_cambio: first.tasa_cambio || 1,
    };
}

function import_balance_file(frm, file_url, moneda, tasaCambio, dialog) {
    frappe.call({
        method: "mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.cargar_balanza_archivo",
        args: {
            balanza_name: frm.doc.name,
            file_url: file_url,
            moneda: moneda,
            tasa_cambio: tasaCambio,
        },
        freeze: true,
        freeze_message: __("Importando balanza..."),
        callback: (callResponse) => {
            if (dialog) {
                dialog.hide();
            }
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
}

// Backward compatibility alias
async function fetch_file_and_import(frm, file_url, moneda, tasaCambio, dialog) {
    import_balance_file(frm, file_url, moneda, tasaCambio, dialog);
}

function download_balance_excel(frm) {
    const balanzaName = (frm && frm.doc && frm.doc.name) ? frm.doc.name : "";
    const url = frappe.urllib.get_full_url(
        `/api/method/mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.descargar_balanza_excel?balanza_name=${encodeURIComponent(balanzaName)}`
    );
    window.open(url, "_blank");
}

function download_balance_excel_template(frm) {
    const balanzaName = (frm && frm.doc && frm.doc.name) ? frm.doc.name : "";
    const url = frappe.urllib.get_full_url(
        `/api/method/mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.descargar_plantilla_excel?balanza_name=${encodeURIComponent(balanzaName)}`
    );
    window.open(url, "_blank");
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
