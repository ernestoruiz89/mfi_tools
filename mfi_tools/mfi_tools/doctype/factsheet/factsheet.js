function runPackageMappingFromFactsheet(frm) {
    const targetPackage = (frm.doc.paquete_eeff || "").trim();
    if (!targetPackage) {
        frappe.msgprint(__("Este factsheet no tiene paquete EEFF asociado."));
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

function openFactsheetPrint(frm) {
    const url = frappe.urllib.get_full_url(
        `/printview?doctype=${encodeURIComponent(frm.doctype)}&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent("Factsheet - Individual")}&trigger_print=1`
    );
    window.open(url, "_blank");
}

frappe.ui.form.on("Factsheet", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Ejecutar Mapeo"), () => {
            runPackageMappingFromFactsheet(frm);
        }, __("Revision"));

        frm.add_custom_button(__("Imprimir Factsheet"), () => {
            openFactsheetPrint(frm);
        }, __("Impresion"));
    },
});
