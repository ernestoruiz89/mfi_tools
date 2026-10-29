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

        frm.add_custom_button(__("Generar ISC (TXT)"), () => {
            open_isc_dialog(frm);
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

function open_isc_dialog(frm) {
    if (!(frm.doc.lineas || []).length) {
        frappe.msgprint(__("La balanza no tiene lineas cargadas para generar el archivo ISC."));
        return;
    }

    const defaultRate = (frm.doc.moneda !== "NIO" && frm.doc.moneda !== "COR")
        ? (frm.doc.tasas_cambio?.[0]?.tasa_cambio || 1)
        : 1;

    const dialog = new frappe.ui.Dialog({
        title: __("Generar Archivo ISC - CONAMI (.txt)"),
        fields: [
            {
                fieldname: "id_moneda",
                fieldtype: "Select",
                label: __("Moneda del Envío (id_moneda)"),
                options: [
                    "Auto-detectar por 9no dígito de cuenta (1, 2, 3 y consolidar en 0)",
                    "0 - Moneda integradora (Consolidado)",
                    "1 - Nacional con Mantenimiento de Valor",
                    "2 - Nacional sin Mantenimiento de Valor",
                    "3 - Extranjera",
                ].join("\n"),
                default: "Auto-detectar por 9no dígito de cuenta (1, 2, 3 y consolidar en 0)",
                description: __("Según manual CONAMI: 0=Integradora, 1=Nac c/MV, 2=Nac s/MV, 3=Extranjera."),
            },
            {
                fieldname: "longitud_cuenta",
                fieldtype: "Select",
                label: __("Longitud Cuenta Contable"),
                options: [
                    "Hasta 8 dígitos (Sub-subcuenta MUC CONAMI)",
                    "Código completo (sin puntos/guiones)",
                ].join("\n"),
                default: "Hasta 8 dígitos (Sub-subcuenta MUC CONAMI)",
                description: __("El manual especifica Varchar(8) sin puntos ni guiones."),
            },
            {
                fieldname: "incluir_moneda_0",
                fieldtype: "Check",
                label: __("Garantizar registros de Moneda Integradora (0)"),
                default: 1,
                description: __("Requerido por validación CONAMI 02.001.007."),
            },
            {
                fieldname: "omitir_ceros",
                fieldtype: "Check",
                label: __("Omitir cuentas con saldos y movimientos en cero"),
                default: 1,
            },
            {
                fieldname: "tasa_cambio",
                fieldtype: "Float",
                label: __("Tasa de cambio a Córdobas"),
                default: defaultRate,
                description: __("Todos los saldos deben expresarse en Córdobas. Usar 1 si la balanza ya está en Córdobas."),
            },
            {
                fieldname: "separador",
                fieldtype: "Select",
                label: __("Separador de Campos"),
                options: "|\n,\n\\t",
                default: "|",
                description: __("El estándar oficial de CONAMI es pleca (|)."),
            },
            {
                fieldname: "preview_section",
                fieldtype: "Section Break",
                label: __("Validación y Vista Previa"),
            },
            {
                fieldname: "preview_html",
                fieldtype: "HTML",
            },
        ],
        primary_action_label: __("Descargar ISC_Saldos.txt"),
        primary_action(values) {
            download_isc_file(frm, values);
            dialog.hide();
        },
        secondary_action_label: __("Validar y Previsualizar"),
        secondary_action() {
            refresh_isc_preview(dialog, frm);
        },
    });

    dialog.show();
    refresh_isc_preview(dialog, frm);
}

function refresh_isc_preview(dialog, frm) {
    const values = dialog.get_values() || {};
    const $wrapper = dialog.get_field("preview_html").$wrapper;
    $wrapper.html(`<div class="text-muted text-center p-3">${__("Validando saldos...")}</div>`);

    frappe.call({
        method: "mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.validar_datos_isc",
        args: {
            balanza_name: frm.doc.name,
            id_moneda: values.id_moneda || "auto",
            longitud_cuenta: (values.longitud_cuenta || "").includes("completo") ? "completo" : "8",
            incluir_moneda_0: values.incluir_moneda_0 ? 1 : 0,
            omitir_ceros: values.omitir_ceros ? 1 : 0,
            separador: values.separador || "|",
            tasa_cambio: values.tasa_cambio || 1,
        },
        callback: (r) => {
            const data = r.message || {};
            const badgeClass = data.cuadra ? "indicator-pill green" : "indicator-pill red";
            const cuadraText = data.cuadra ? __("Cuadra perfectamente (Σ Deudoras = Σ Acreedoras)") : __("DESCUADRE DETECTADO");

            let html = `
                <div style="margin-bottom: 12px; padding: 10px; border-radius: 6px; background-color: var(--bg-light-gray, #f8f9fa); border: 1px solid var(--border-color, #d1d8dd);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="${badgeClass}" style="font-weight: 600; font-size: 13px;">${cuadraText}</span>
                        <span class="text-muted" style="font-size: 12px;"><b>${data.total_registros || 0}</b> registros a generar</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; font-size: 12px;">
                        <div><b>Σ Deudoras:</b> ${format_currency(data.suma_deudoras || 0, "NIO")}</div>
                        <div><b>Σ Acreedoras:</b> ${format_currency(data.suma_acreedoras || 0, "NIO")}</div>
                        <div><b>Diferencia:</b> <span style="color: ${data.cuadra ? 'inherit' : 'red'}">${format_currency(data.diferencia || 0, "NIO")}</span></div>
                    </div>
                </div>
            `;

            if (data.advertencias && data.advertencias.length) {
                html += `
                    <div class="alert alert-warning p-2" style="font-size: 12px; margin-bottom: 10px;">
                        ${data.advertencias.join("<br>")}
                    </div>
                `;
            }

            if (data.preview) {
                html += `
                    <div style="font-size: 11px; font-weight: bold; margin-bottom: 4px;" class="text-muted">
                        ${__("Primeras líneas de isc_saldos.txt (cta_contable|Id_moneda|Saldo_inicial|creditos_mes|debitos_mes|Saldo):")}
                    </div>
                    <pre style="background: var(--code-block-bg, #282c34); color: #abb2bf; padding: 10px; border-radius: 5px; max-height: 160px; overflow-y: auto; font-family: monospace; font-size: 11px; line-height: 1.4;">${frappe.utils.escape_html(data.preview)}</pre>
                `;
            }

            $wrapper.html(html);
        },
    });
}

function download_isc_file(frm, values) {
    const balanzaName = frm.doc.name || "";
    const idMoneda = encodeURIComponent(values.id_moneda || "auto");
    const longCta = encodeURIComponent((values.longitud_cuenta || "").includes("completo") ? "completo" : "8");
    const inc0 = values.incluir_moneda_0 ? 1 : 0;
    const omit0 = values.omitir_ceros ? 1 : 0;
    const sep = encodeURIComponent(values.separador || "|");
    const tc = values.tasa_cambio || 1;

    const url = frappe.urllib.get_full_url(
        `/api/method/mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.descargar_archivo_isc?balanza_name=${encodeURIComponent(balanzaName)}&id_moneda=${idMoneda}&longitud_cuenta=${longCta}&incluir_moneda_0=${inc0}&omitir_ceros=${omit0}&separador=${sep}&tasa_cambio=${tc}`
    );
    window.open(url, "_blank");
}
