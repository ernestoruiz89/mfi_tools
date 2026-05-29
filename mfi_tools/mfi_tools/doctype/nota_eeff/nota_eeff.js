const NOTA_EEFF_SHORTCUT_NAMESPACE = ".mfiToolsNotaEEFFShortcuts";

function openNotaPrint(frm) {
    const url = frappe.urllib.get_full_url(
        `/printview?doctype=${encodeURIComponent(frm.doctype)}&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent("Nota EEFF - Individual")}&trigger_print=1`
    );
    window.open(url, "_blank");
}

function runPackageMappingFromNota(frm) {
    const targetPackage = (frm.doc.paquete_eeff || "").trim();
    if (!targetPackage) {
        frappe.msgprint(__("Esta nota no tiene paquete EEFF asociado."));
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

function bindNotaShortcuts(frm) {
    $(document).off(`keydown${NOTA_EEFF_SHORTCUT_NAMESPACE}`);

    if (frm.is_new()) return;

    $(document).on(`keydown${NOTA_EEFF_SHORTCUT_NAMESPACE}`, (event) => {
        const activeForm = cur_frm;
        const key = String(event.key || "").toLowerCase();
        const code = String(event.code || "");
        const isMappingShortcut = event.ctrlKey && event.altKey && !event.shiftKey && (key === "m" || code === "KeyM");

        if (!isMappingShortcut) return;
        if (!activeForm || activeForm.doctype !== "Nota EEFF" || activeForm.doc?.name !== frm.doc.name) return;
        if ($(".modal:visible").length) return;

        event.preventDefault();
        event.stopPropagation();
        runPackageMappingFromNota(activeForm);
    });
}

frappe.ui.form.on("Nota EEFF", {
    refresh(frm) {
        bindNotaShortcuts(frm);

        if (frm.is_new()) return;

        frm.add_custom_button(__("Ejecutar Mapeo"), () => {
            runPackageMappingFromNota(frm);
        }, __("Revision"));

        frm.add_custom_button(__("Helper de Mapeo"), () => {
            frappe.route_options = {
                package_name: frm.doc.paquete_eeff,
                note_name: frm.doc.name,
            };
            frappe.set_route("helper-mapeo-notas-eeff");
        }, __("Revision"));

        frm.add_custom_button(__("Imprimir Nota"), () => {
            openNotaPrint(frm);
        }, __("Impresion"));

        if (frm.doc.estructura_nota === "Compleja") {
            frm.add_custom_button(__("Nueva Seccion Compleja"), () => {
                frappe.route_options = {
                    nota_eeff: frm.doc.name,
                    paquete_eeff: frm.doc.paquete_eeff,
                };
                frappe.new_doc("Seccion Nota EEFF");
            }, __("Estructura"));

            frm.add_custom_button(__("Ver Secciones Complejas"), () => {
                frappe.set_route("List", "Seccion Nota EEFF", { nota_eeff: frm.doc.name });
            }, __("Estructura"));
        }
    },
});
