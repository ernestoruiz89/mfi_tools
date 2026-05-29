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

        const label = buildLabel(option.code, option.label);
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

async function loadAutocompleteOptions(frm) {
    if (!frm.doc.company) return;
    
    return frappe.call({
        method: "mfi_tools.mfi_tools.doctype.regla_mapeo_contable_eeff.regla_mapeo_contable_eeff.get_autocomplete_options",
        args: { company: frm.doc.company },
        callback: function(r) {
            if (r.message) {
                frm.__cf_full_options = r.message;
                refreshActiveDatalists(frm);
            }
        }
    });
}

function refreshActiveDatalists(frm) {
    const opts = frm.__cf_full_options;
    if (!opts) return;

    const destino = frm.doc.destino_tipo;

    if (destino === "Linea Estado") {
        applyAutocomplete(frm, "destino_codigo_estado", opts.estados);
        let lineas = opts.lineas_estado;
        if (frm.doc.destino_codigo_estado) {
            let estado = extractCodeToken(frm.doc.destino_codigo_estado);
            lineas = lineas.filter(l => l.estado === estado);
        }
        applyAutocomplete(frm, "destino_codigo_linea", lineas);
    } 
    else if (destino === "Cifra Nota" || destino === "Celda Seccion Nota") {
        applyAutocomplete(frm, "destino_numero_nota", opts.notas);
        
        let nota = extractCodeToken(frm.doc.destino_numero_nota);
        if (destino === "Cifra Nota") {
            let cifras = opts.cifras_nota;
            if (nota) cifras = cifras.filter(c => c.nota === nota);
            applyAutocomplete(frm, "destino_codigo_cifra", cifras);
        }
        else if (destino === "Celda Seccion Nota") {
            let secciones = opts.secciones;
            if (nota) secciones = secciones.filter(s => s.nota === nota);
            applyAutocomplete(frm, "destino_codigo_seccion", secciones);
            
            let seccion = extractCodeToken(frm.doc.destino_codigo_seccion);
            let tablas = opts.tablas;
            let filas = opts.filas;
            let columnas = opts.columnas;
            if (seccion) {
                tablas = tablas.filter(t => t.seccion === seccion);
                filas = filas.filter(f => f.seccion === seccion);
                columnas = columnas.filter(c => c.seccion === seccion);
            }
            applyAutocomplete(frm, "destino_codigo_tabla", tablas);
            applyAutocomplete(frm, "destino_codigo_fila", filas);
            applyAutocomplete(frm, "destino_codigo_columna", columnas);
        }
    }
    else if (destino === "Linea Factsheet") {
        applyAutocomplete(frm, "destino_codigo_factsheet", opts.factsheets);
        let lineas = opts.lineas_factsheet;
        if (frm.doc.destino_codigo_factsheet) {
            let fs = extractCodeToken(frm.doc.destino_codigo_factsheet);
            lineas = lineas.filter(l => l.factsheet === fs);
        }
        applyAutocomplete(frm, "destino_codigo_linea", lineas);
    }
}

frappe.ui.form.on("Regla Mapeo Contable EEFF", {
    async refresh(frm) {
        await loadAutocompleteOptions(frm);
    },
    
    async company(frm) {
        await loadAutocompleteOptions(frm);
    },

    destino_tipo(frm) {
        refreshActiveDatalists(frm);
    },

    destino_codigo_estado(frm) {
        normalizeDestinationCode(frm, "destino_codigo_estado");
        refreshActiveDatalists(frm);
    },
    
    destino_numero_nota(frm) {
        normalizeDestinationCode(frm, "destino_numero_nota");
        refreshActiveDatalists(frm);
    },

    destino_codigo_seccion(frm) {
        normalizeDestinationCode(frm, "destino_codigo_seccion");
        refreshActiveDatalists(frm);
    },
    
    destino_codigo_factsheet(frm) {
        normalizeDestinationCode(frm, "destino_codigo_factsheet");
        refreshActiveDatalists(frm);
    },

    destino_codigo_linea(frm) {
        normalizeDestinationCode(frm, "destino_codigo_linea");
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
    destino_codigo_cifra(frm) {
        normalizeDestinationCode(frm, "destino_codigo_cifra");
    },

    before_save(frm) {
        normalizeDestinationCode(frm, "destino_codigo_estado");
        normalizeDestinationCode(frm, "destino_codigo_linea");
        normalizeDestinationCode(frm, "destino_numero_nota");
        normalizeDestinationCode(frm, "destino_codigo_cifra");
        normalizeDestinationCode(frm, "destino_codigo_seccion");
        normalizeDestinationCode(frm, "destino_codigo_tabla");
        normalizeDestinationCode(frm, "destino_codigo_fila");
        normalizeDestinationCode(frm, "destino_codigo_columna");
        normalizeDestinationCode(frm, "destino_codigo_factsheet");
    },
});

