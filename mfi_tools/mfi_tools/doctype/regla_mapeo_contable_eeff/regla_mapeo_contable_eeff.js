function extractCodeToken(value) {
    const text = String(value || "").trim().toUpperCase();
    if (!text) return "";
    if (text.includes(" - ")) {
        return text.split(" - ", 1)[0].trim();
    }
    return text;
}

function getFieldInput(frm, fieldname) {
    const field = frm.get_field(fieldname);
    if (!field || !field.$input || !field.$input.length) {
        return null;
    }
    return field.$input.get(0);
}

function buildLabel(code, description) {
    const cleanCode = String(code || "").trim().toUpperCase();
    const cleanDescription = String(description || "").trim();
    if (!cleanCode) return "";
    if (!cleanDescription) return cleanCode;
    return `${cleanCode} - ${cleanDescription}`;
}

function applyAutocomplete(frm, fieldname, rawOptions) {
    const input = getFieldInput(frm, fieldname);
    if (!input) return;

    const options = Array.isArray(rawOptions) ? rawOptions : [];
    frm.__cf_destination_maps = frm.__cf_destination_maps || {};

    const codeMap = {};
    const codeSet = new Set();
    const labels = [];
    const seenLabels = new Set();

    for (const option of options) {
        const code = extractCodeToken(option.code);
        if (!code) continue;

        const label = String(option.label || code).trim();
        codeSet.add(code);
        codeMap[code] = code;
        codeMap[label.toUpperCase()] = code;

        if (!seenLabels.has(label)) {
            labels.push(label);
            seenLabels.add(label);
        }
    }

    frm.__cf_destination_maps[fieldname] = { codeMap, codeSet };

    const datalistId = `cf-${frappe.scrub(frm.doctype)}-${fieldname}-options`;
    let datalist = document.getElementById(datalistId);
    if (!datalist) {
        datalist = document.createElement("datalist");
        datalist.id = datalistId;
        frm.$wrapper.get(0).appendChild(datalist);
    }

    datalist.innerHTML = "";
    for (const label of labels) {
        const optionNode = document.createElement("option");
        optionNode.value = label;
        datalist.appendChild(optionNode);
    }
    input.setAttribute("list", datalistId);
}

function normalizeDestinationCode(frm, fieldname) {
    const currentValue = String(frm.doc[fieldname] || "").trim();
    if (!currentValue) return;

    const normalizedCurrent = extractCodeToken(currentValue);
    const fieldMap = frm.__cf_destination_maps && frm.__cf_destination_maps[fieldname];

    if (!fieldMap) {
        if (normalizedCurrent !== currentValue) {
            frm.set_value(fieldname, normalizedCurrent);
        }
        return;
    }

    const mappedCode = fieldMap.codeMap[currentValue.toUpperCase()] || fieldMap.codeMap[normalizedCurrent] || "";
    const finalCode = mappedCode || normalizedCurrent;

    if (!finalCode) return;
    if (fieldMap.codeSet.size && !fieldMap.codeSet.has(finalCode)) {
        return;
    }
    if (finalCode !== currentValue) {
        frm.set_value(fieldname, finalCode);
    }
}

async function refreshEstadoLineaOptions(frm) {
    const estadoName = String(frm.doc.estado_financiero_eeff || "").trim();
    if (!estadoName) {
        applyAutocomplete(frm, "destino_codigo_linea", []);
        return;
    }

    try {
        const estadoDoc = await frappe.db.get_doc("Estado Financiero EEFF", estadoName);
        const lineOptions = (estadoDoc.lineas || [])
            .filter((linea) => !Number(linea.es_titulo || 0) && !Number(linea.calculo_automatico || 0))
            .map((linea) => ({
                code: linea.codigo_linea,
                label: buildLabel(linea.codigo_linea, linea.descripcion),
            }))
            .filter((row) => row.code);
        applyAutocomplete(frm, "destino_codigo_linea", lineOptions);
        normalizeDestinationCode(frm, "destino_codigo_linea");
    } catch (error) {
        applyAutocomplete(frm, "destino_codigo_linea", []);
        console.error("No se pudieron cargar lineas del estado financiero.", error);
    }
}

function collectUniqueTableCodes(sectionDoc) {
    const result = new Set();
    const groups = [
        sectionDoc.filas_tabulares || [],
        sectionDoc.columnas_tabulares || [],
        sectionDoc.celdas_tabulares || [],
    ];
    for (const rows of groups) {
        for (const row of rows) {
            const tableCode = extractCodeToken(row.codigo_tabla);
            if (tableCode) result.add(tableCode);
        }
    }
    return Array.from(result).sort();
}

async function refreshSeccionOptions(frm) {
    const seccionName = String(frm.doc.seccion_nota_eeff || "").trim();
    if (!seccionName) {
        applyAutocomplete(frm, "destino_codigo_seccion", []);
        applyAutocomplete(frm, "destino_codigo_tabla", []);
        applyAutocomplete(frm, "destino_codigo_fila", []);
        applyAutocomplete(frm, "destino_codigo_columna", []);
        return;
    }

    try {
        const sectionDoc = await frappe.db.get_doc("Seccion Nota EEFF", seccionName);
        const sectionOptions = [
            {
                code: sectionDoc.codigo_seccion,
                label: buildLabel(sectionDoc.codigo_seccion, sectionDoc.titulo_seccion),
            },
        ].filter((row) => row.code);

        const rowOptions = (sectionDoc.filas_tabulares || [])
            .map((row) => ({
                code: row.codigo_fila,
                label: buildLabel(row.codigo_fila, row.descripcion),
            }))
            .filter((row) => row.code);

        const columnOptions = (sectionDoc.columnas_tabulares || [])
            .map((row) => ({
                code: row.codigo_columna,
                label: buildLabel(row.codigo_columna, row.etiqueta),
            }))
            .filter((row) => row.code);

        const tableOptions = collectUniqueTableCodes(sectionDoc).map((code) => ({
            code,
            label: code,
        }));

        applyAutocomplete(frm, "destino_codigo_seccion", sectionOptions);
        applyAutocomplete(frm, "destino_codigo_tabla", tableOptions);
        applyAutocomplete(frm, "destino_codigo_fila", rowOptions);
        applyAutocomplete(frm, "destino_codigo_columna", columnOptions);

        normalizeDestinationCode(frm, "destino_codigo_seccion");
        normalizeDestinationCode(frm, "destino_codigo_tabla");
        normalizeDestinationCode(frm, "destino_codigo_fila");
        normalizeDestinationCode(frm, "destino_codigo_columna");
    } catch (error) {
        applyAutocomplete(frm, "destino_codigo_seccion", []);
        applyAutocomplete(frm, "destino_codigo_tabla", []);
        applyAutocomplete(frm, "destino_codigo_fila", []);
        applyAutocomplete(frm, "destino_codigo_columna", []);
        console.error("No se pudieron cargar opciones de la seccion de nota.", error);
    }
}

async function refreshDestinationOptions(frm) {
    await Promise.all([refreshEstadoLineaOptions(frm), refreshSeccionOptions(frm)]);
}

frappe.ui.form.on("Regla Mapeo Contable EEFF", {
    setup(frm) {
        frm.set_query("estado_financiero_eeff", () => {
            const filters = {};
            if (frm.doc.paquete_eeff) filters.paquete_eeff = frm.doc.paquete_eeff;
            return { filters };
        });

        frm.set_query("nota_eeff", () => {
            const filters = {};
            if (frm.doc.paquete_eeff) filters.paquete_eeff = frm.doc.paquete_eeff;
            return { filters };
        });

        frm.set_query("seccion_nota_eeff", () => {
            const filters = {};
            if (frm.doc.nota_eeff) filters.nota_eeff = frm.doc.nota_eeff;
            if (!frm.doc.nota_eeff && frm.doc.paquete_eeff) filters.paquete_eeff = frm.doc.paquete_eeff;
            return { filters };
        });
    },

    async refresh(frm) {
        await refreshDestinationOptions(frm);
    },

    async estado_financiero_eeff(frm) {
        await refreshEstadoLineaOptions(frm);
    },

    async seccion_nota_eeff(frm) {
        await refreshSeccionOptions(frm);
    },

    nota_eeff(frm) {
        frm.set_value("seccion_nota_eeff", "");
        applyAutocomplete(frm, "destino_codigo_seccion", []);
        applyAutocomplete(frm, "destino_codigo_tabla", []);
        applyAutocomplete(frm, "destino_codigo_fila", []);
        applyAutocomplete(frm, "destino_codigo_columna", []);
    },

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
