function openPrint(frm, formatName) {
    const url = frappe.urllib.get_full_url(
        `/printview?doctype=${encodeURIComponent(frm.doctype)}&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent(formatName)}&trigger_print=1`
    );
    window.open(url, "_blank");
}

function callWordExport(frm) {
    const url = frappe.urllib.get_full_url(
        `/api/method/mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.descargar_paquete_word?paquete_name=${encodeURIComponent(frm.doc.name)}`
    );
    frappe.show_alert({ message: __("Generando y descargando documento Word EEFF..."), indicator: "blue" });
    window.open(url, "_blank");
}

function runPackageMapping(frm, paqueteName) {
    const targetPackage = (paqueteName || "").trim();
    if (!targetPackage) {
        frappe.msgprint(__("No se encontro un paquete EEFF para ejecutar mapeo."));
        return;
    }

    frappe.call({
        method: "mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.ejecutar_mapeo",
        args: { paquete_name: targetPackage },
        freeze: true,
        freeze_message: __("Ejecutando mapeo del paquete actual..."),
        callback: (r) => {
            const result = r.message || {};
            const alertas = Array.isArray(result.alertas) ? result.alertas : [];

            frappe.show_alert({
                message: __("Mapeo aplicado al paquete {0}", [targetPackage]),
                indicator: alertas.length ? "orange" : "green",
            });

            if (alertas.length) {
                frappe.msgprint({
                    title: __("Mapeo con Alertas"),
                    indicator: "orange",
                    message: alertas.slice(0, 10).join("<br>"),
                });
            }

            frm.reload_doc();
        },
    });
}

function openCopyNotesDialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Copiar Notas desde otro Paquete"),
        fields: [
            {
                fieldtype: "Link",
                fieldname: "paquete_fuente",
                label: __("Paquete Fuente"),
                options: "Paquete EEFF",
                reqd: 1,
            },
            {
                fieldtype: "Check",
                fieldname: "limpiar_notas",
                label: __("Reemplazar Notas Actuales"),
                default: 0,
            },
        ],
        primary_action_label: __("Copiar"),
        primary_action(values) {
            if (!values.paquete_fuente) {
                frappe.msgprint(__("Selecciona un paquete fuente."));
                return;
            }

            frappe.call({
                method: "mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.copiar_notas_desde_paquete",
                args: {
                    paquete_name: frm.doc.name,
                    paquete_fuente: values.paquete_fuente,
                    limpiar_notas: values.limpiar_notas ? 1 : 0,
                },
                freeze: true,
                freeze_message: __("Copiando notas desde paquete fuente..."),
                callback: (r) => {
                    const message = r.message || {};
                    frappe.show_alert({
                        message: __("Notas copiadas: {0}", [message.notas_copiadas || 0]),
                        indicator: "green",
                    });
                    dialog.hide();
                    frm.reload_doc();
                },
            });
        },
    });

    dialog.fields_dict.paquete_fuente.get_query = () => ({
        filters: (() => {
            const filters = { name: ["!=", frm.doc.name] };
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            return filters;
        })(),
    });

    dialog.show();
}

frappe.ui.form.on("Paquete EEFF", {
    setup(frm) {
        const get_balance_filters = () => {
            const filters = {};
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            return { filters };
        };

        frm.set_query("balanza_comprobacion_eeff", get_balance_filters);
        frm.set_query("balanza_comparativa_eeff", () => {
            const filters = {};
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            if (frm.doc.balanza_comprobacion_eeff) filters.name = ["!=", frm.doc.balanza_comprobacion_eeff];
            return { filters };
        });
        frm.set_query("balanza_base_actual_eeff", () => {
            const filters = {};
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            const excluded = [
                frm.doc.balanza_comprobacion_eeff,
                frm.doc.balanza_comparativa_eeff,
                frm.doc.balanza_base_comparativa_eeff,
            ].filter(Boolean);
            if (excluded.length) filters.name = ["not in", excluded];
            return { filters };
        });
        frm.set_query("balanza_base_comparativa_eeff", () => {
            const filters = {};
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            const excluded = [
                frm.doc.balanza_comprobacion_eeff,
                frm.doc.balanza_comparativa_eeff,
                frm.doc.balanza_base_actual_eeff,
            ].filter(Boolean);
            if (excluded.length) filters.name = ["not in", excluded];
            return { filters };
        });
        frm.set_query("datos_estadisticos_actual_eeff", () => {
            const filters = {};
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            return { filters };
        });
        frm.set_query("datos_estadisticos_comparativo_eeff", () => {
            const filters = {};
            if (frm.doc.cliente) filters.cliente = frm.doc.cliente;
            if (frm.doc.datos_estadisticos_actual_eeff) filters.name = ["!=", frm.doc.datos_estadisticos_actual_eeff];
            return { filters };
        });
    },
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Ejecutar Mapeo"), () => {
            runPackageMapping(frm, frm.doc.name);
        }, __("Revision"));

        frm.add_custom_button(__("Indicadores de Emision"), () => {
            frappe.route_options = {
                paquete_name: frm.doc.name,
                cliente: frm.doc.cliente,
                anio: frm.doc.anio,
                mes: frm.doc.mes,
            };
            frappe.set_route("indicadores-emision-eeff");
        }, __("Revision"));

        frm.add_custom_button(__("Copiar Notas desde Paquete"), () => {
            openCopyNotesDialog(frm);
        }, __("Configuracion"));

        frm.add_custom_button(__("Asistente de Notas"), () => {
            frappe.route_options = {
                package_name: frm.doc.name,
                cliente: frm.doc.cliente,
                anio: frm.doc.anio,
                mes: frm.doc.mes,
            };
            frappe.set_route("asistente-notas-eeff");
        }, __("Notas"));

        frm.add_custom_button(__("Imprimir Paquete Completo"), () => {
            openPrint(frm, "Paquete EEFF - Completo");
        }, __("Impresion"));

        frm.add_custom_button(__("Imprimir Factsheets"), () => {
            openPrint(frm, "Paquete EEFF - Factsheet Completo");
        }, __("Impresion"));

        frm.add_custom_button(__("Exportar Word EEFF"), () => {
            callWordExport(frm);
        }, __("Impresion"));
    },
});
