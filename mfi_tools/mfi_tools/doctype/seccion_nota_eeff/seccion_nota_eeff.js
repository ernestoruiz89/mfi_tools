function runPackageMappingFromSeccion(frm) {
    const targetPackage = (frm.doc.paquete_eeff || "").trim();
    if (!targetPackage) {
        frappe.msgprint(__("Esta seccion no tiene paquete EEFF asociado."));
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

frappe.ui.form.on("Seccion Nota EEFF", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Ejecutar Mapeo"), () => {
            runPackageMappingFromSeccion(frm);
        }, __("Revision"));
    },
    nota_eeff(frm) {
        if (!frm.doc.nota_eeff) return;
        frappe.db.get_value("Nota EEFF", frm.doc.nota_eeff, ["paquete_eeff", "mes", "anio"], (r) => {
            if (!r) return;
            if (r.paquete_eeff && frm.doc.paquete_eeff !== r.paquete_eeff) {
                frm.set_value("paquete_eeff", r.paquete_eeff);
            }
            if (r.mes) {
                frm.set_value("mes", r.mes);
            }
            if (r.anio) {
                frm.set_value("anio", r.anio);
            }
        });
    },
});
