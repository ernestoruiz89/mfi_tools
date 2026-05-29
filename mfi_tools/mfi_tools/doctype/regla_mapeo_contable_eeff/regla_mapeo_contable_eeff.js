function extractCodeToken(value) {
    const text = String(value || "").trim().toUpperCase();
    if (!text) return "";
    if (text.includes(" - ")) {
        return text.split(" - ", 1)[0].trim();
    }
    return text;
}

function normalizeDestinationCode(frm, fieldname) {
    const currentValue = String(frm.doc[fieldname] || "").trim();
    if (!currentValue) return;

    const normalizedCurrent = extractCodeToken(currentValue);
    if (normalizedCurrent !== currentValue) {
        frm.set_value(fieldname, normalizedCurrent);
    }
}

frappe.ui.form.on("Regla Mapeo Contable EEFF", {
    destino_codigo_linea(frm) {
        normalizeDestinationCode(frm, "destino_codigo_linea");
    },
    destino_codigo_seccion(frm) {
        normalizeDestinationCode(frm, "destino_codigo_seccion");
    },
    destino_codigo_tabla(frm) {
        normalizeDestinationCode(frm, "destino_codigo_tabla");
    },
    destino_codigo_fila(frm) {
        normalizeDestinationCode(frm, "destino_codigo_fila");
    },
    destino_codigo_columna(frm) {
        normalizeDestinationCode(frm, "destino_codigo_columna");
    },
    before_save(frm) {
        normalizeDestinationCode(frm, "destino_codigo_linea");
        normalizeDestinationCode(frm, "destino_codigo_seccion");
        normalizeDestinationCode(frm, "destino_codigo_tabla");
        normalizeDestinationCode(frm, "destino_codigo_fila");
        normalizeDestinationCode(frm, "destino_codigo_columna");
    },
});

