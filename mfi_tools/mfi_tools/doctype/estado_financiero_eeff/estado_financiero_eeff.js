function openEstadoPrint(frm) {
    const url = frappe.urllib.get_full_url(
        `/printview?doctype=${encodeURIComponent(frm.doctype)}&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent("Estado Financiero EEFF - Base")}&trigger_print=1`
    );
    window.open(url, "_blank");
}

function runPackageMappingFromEstado(frm) {
    const targetPackage = (frm.doc.paquete_eeff || "").trim();
    if (!targetPackage) {
        frappe.msgprint(__("Este estado no tiene paquete EEFF asociado."));
        return;
    }

    frappe.call({
        method: "mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.ejecutar_mapeo",
        args: { paquete_name: targetPackage },
        freeze: true,
        freeze_message: __("Ejecutando mapeo del paquete actual..."),
        callback: (r) => {
            const result = r.message || {};
            if (result.error) {
                frappe.msgprint({title: __("Mapeo pendiente"), indicator: "orange", message: frappe.utils.escape_html(result.error)});
                frm.reload_doc();
                return;
            }
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

function enableLineasBulkEdit(frm) {
    const gridNames = ["lineas", "columnas_tabulares", "filas_tabulares", "celdas_tabulares"];
    for (const gridName of gridNames) {
        const grid = frm.get_field(gridName)?.grid;
        if (!grid) continue;

        grid.df.allow_bulk_edit = 1;
        if (typeof grid.setup_allow_bulk_edit === "function") {
            grid.setup_allow_bulk_edit();
        }
    }
}

function clearTitleAmounts(cdt, cdn) {
    const row = locals[cdt]?.[cdn];
    if (!row || !row.es_titulo) return;

    frappe.model.set_value(cdt, cdn, "monto_actual", null);
    frappe.model.set_value(cdt, cdn, "monto_comparativo", null);
    frappe.model.set_value(cdt, cdn, "monto_base_actual", null);
    frappe.model.set_value(cdt, cdn, "monto_base_comparativo", null);
}

function syncBlankLine(cdt, cdn) {
    const row = locals[cdt]?.[cdn];
    if (!row || !row.es_linea_blanco) return;

    frappe.model.set_value(cdt, cdn, "descripcion", "");
    frappe.model.set_value(cdt, cdn, "monto_actual", null);
    frappe.model.set_value(cdt, cdn, "monto_comparativo", null);
    frappe.model.set_value(cdt, cdn, "monto_base_actual", null);
    frappe.model.set_value(cdt, cdn, "monto_base_comparativo", null);
    frappe.model.set_value(cdt, cdn, "valor_texto", "");
    frappe.model.set_value(cdt, cdn, "es_titulo", 0);
    frappe.model.set_value(cdt, cdn, "es_total", 0);
    frappe.model.set_value(cdt, cdn, "es_subtotal", 0);
    frappe.model.set_value(cdt, cdn, "negrita", 0);
    frappe.model.set_value(cdt, cdn, "subrayado", 0);
    
    frappe.model.set_value(cdt, cdn, "modo_formula", "Vertical");
    frappe.model.set_value(cdt, cdn, "formula_lineas", "");
}

function syncPresentationFields(frm, cdt, cdn) {
    const row = locals[cdt]?.[cdn];
    if (!row) return;

    if (row.es_linea_blanco) {
        syncBlankLine(cdt, cdn);
        return;
    }

    if (row.es_titulo) {
        clearTitleAmounts(cdt, cdn);
    }
}

frappe.ui.form.on("Estado Financiero EEFF", {
    tipo_estado(frm) {
        if (!frm.is_new()) return;
        const months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
        const selected = frm.doc.tipo_estado === "Estado de Cambios en el Patrimonio" ? ["junio", "diciembre"]
            : frm.doc.tipo_estado === "Estado de Flujos de Efectivo" ? ["diciembre"] : [];
        const values = { emitir_todos_meses: selected.length ? 0 : 1, periodicidad_configurada: 1 };
        months.forEach((month) => values[`emitir_${month}`] = selected.includes(month) ? 1 : 0);
        frm.set_value(values);
    },
    emitir_todos_meses(frm) { frm.doc.periodicidad_configurada = 1; },
    refresh(frm) {
        enableLineasBulkEdit(frm);
        if (frm.is_new()) return;

        frm.add_custom_button(__("Ejecutar Mapeo"), () => {
            runPackageMappingFromEstado(frm);
        });

        frm.add_custom_button(__("Imprimir Estado"), () => {
            openEstadoPrint(frm);
        }, __("Impresion"));
    },
});

frappe.ui.form.on("Linea Estado Financiero EEFF", {
    es_linea_blanco(frm, cdt, cdn) {
        syncPresentationFields(frm, cdt, cdn);
        frm.refresh_field("lineas");
    },
    es_titulo(frm, cdt, cdn) {
        syncPresentationFields(frm, cdt, cdn);
        frm.refresh_field("lineas");
    },
    formato_presentacion(frm, cdt, cdn) {
        syncPresentationFields(frm, cdt, cdn);
        frm.refresh_field("lineas");
    },
});

// A user's explicit month selections take precedence over the type defaults.
const emissionMonthHandlers = {};
["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"].forEach((month) => {
    emissionMonthHandlers[`emitir_${month}`] = (frm) => { frm.doc.periodicidad_configurada = 1; };
});
frappe.ui.form.on("Estado Financiero EEFF", emissionMonthHandlers);
