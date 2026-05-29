frappe.pages["asistente-notas-eeff"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Asistente Notas EEFF",
        single_column: true,
    });

    frappe.pages["asistente-notas-eeff"].editor = new AsistenteNotasEEFF(page);
    frappe.pages["asistente-notas-eeff"].editor.init();
};

frappe.pages["asistente-notas-eeff"].on_page_show = function () {
    const editor = frappe.pages["asistente-notas-eeff"].editor;
    if (!editor) return;
    editor.apply_route_options();
    const hasRouteOptions = !!Object.keys(editor.state.route_options || {}).length;
    if (hasRouteOptions || !editor.bootstrapped) {
        editor.load_bootstrap({}, true);
    }
};

class AsistenteNotasEEFF {
    constructor(page) {
        this.page = page;
        this.wrapper = page.main;
        this.bootstrapped = false;
        this.loading = false;
        this.last_bootstrap_key = null;
        this.state = {
            cliente: "",
            anio: new Date().getFullYear(),
            mes: "",
            package_name: "",
            selected_note_name: "",
            clients: [],
            meses: [],
            packages: [],
            notes: [],
            summary: null,
            note: null,
            current_section_id: null,
            route_options: {},
            fullscreen_cards: {},
        };
    }

    init() {
        this.setup_styles();
        this.render_shell();
        this.bind_events();
        this.page.set_primary_action(__("Guardar Nota"), () => this.save_current_note(), "save");
        this.page.set_secondary_action(__("Nueva Nota"), () => this.open_create_note_dialog());
        this.page.add_menu_item(__("Abrir Paquete"), () => this.open_package_form());
        this.page.add_menu_item(__("Abrir Nota en Formulario"), () => this.open_current_note_form());
        this.render_all();
    }

    apply_route_options() {
        this.state.route_options = frappe.route_options || {};
        frappe.route_options = null;
    }

    setup_styles() {
        if (document.getElementById("cf-note-editor-style")) return;
        const style = document.createElement("style");
        style.id = "cf-note-editor-style";
        style.textContent = `
            .cfe-shell{display:grid;grid-template-columns:320px minmax(0,1fr);gap:16px;padding:18px;border:1px solid #d8e2ea;border-radius:22px;background:linear-gradient(160deg,#f4f9f8 0%,#eef7ff 52%,#fffaf1 100%)}
            .cfe-sidebar,.cfe-card{background:#fff;border:1px solid #d8e2ea;border-radius:18px;box-shadow:0 12px 28px rgba(15,23,42,.06)}
            .cfe-sidebar{overflow:hidden}.cfe-main{display:flex;flex-direction:column;gap:14px;min-width:0}
            .cfe-card-head,.cfe-sidebar-head{padding:14px 16px;border-bottom:1px solid #eef2f7}
            .cfe-card-head h3,.cfe-sidebar-head h3{margin:0;font-size:15px;font-weight:800;color:#0f172a}
            .cfe-card-head p,.cfe-sidebar-head p{margin:6px 0 0;color:#64748b;font-size:12px}
            .cfe-filters,.cfe-summary{padding:14px 16px}.cfe-grid{display:grid;gap:12px}
            .cfe-grid.filters,.cfe-grid.note-meta,.cfe-grid.section-meta,.cfe-grid.note-content{grid-template-columns:repeat(2,minmax(0,1fr))}
            .cfe-field{display:flex;flex-direction:column;gap:6px}.cfe-field label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:800}
            .cfe-field input,.cfe-field select,.cfe-field textarea{width:100%;border:1px solid #cbd5e1;border-radius:10px;padding:9px 10px;font-size:13px;background:#fff}
            .cfe-field textarea{min-height:110px;resize:vertical}.cfe-field.span-2{grid-column:span 2}
            .cfe-actions,.cfe-toolbar,.cfe-section-tabs{display:flex;gap:8px;flex-wrap:wrap}.cfe-actions{margin-top:12px}
            .cfe-btn{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:700;cursor:pointer}
            .cfe-btn.primary{background:#0f766e;border-color:#0f766e;color:#fff}.cfe-btn.secondary{background:#14532d;border-color:#14532d;color:#fff}.cfe-btn.danger{background:#fff1f2;border-color:#fecdd3;color:#be123c}
            .cfe-note-list{max-height:calc(100vh - 280px);overflow:auto}.cfe-note-item{padding:12px 16px;border-top:1px solid #eef2f7;cursor:pointer}.cfe-note-item:first-child{border-top:0}.cfe-note-item:hover{background:#f8fafc}.cfe-note-item.active{background:#dcfce7}
            .cfe-note-title{display:flex;align-items:center;justify-content:space-between;gap:8px}.cfe-note-title strong{font-size:13px;color:#0f172a}.cfe-note-item span{display:block;margin-top:5px;color:#64748b;font-size:11px}
            .cfe-pill{display:inline-flex;align-items:center;justify-content:center;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800;text-transform:uppercase}.cfe-pill.simple{background:#dbeafe;color:#1d4ed8}.cfe-pill.complex{background:#ecfccb;color:#4d7c0f}.cfe-pill.draft{background:#e2e8f0;color:#334155}.cfe-pill.review{background:#ffedd5;color:#9a3412}.cfe-pill.approved{background:#dcfce7;color:#166534}
            .cfe-empty{padding:44px 24px;text-align:center;color:#64748b;border:1px dashed #cbd5e1;border-radius:16px;background:rgba(255,255,255,.78)}
            .cfe-table-wrap,.cfe-matrix-wrap{overflow:auto;padding:0 16px 16px}.cfe-table,.cfe-matrix-table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}
            .cfe-table th,.cfe-table td,.cfe-matrix-table th,.cfe-matrix-table td{padding:8px;border-bottom:1px solid #eef2f7;vertical-align:top}
            .cfe-table th,.cfe-matrix-table th{background:#f8fafc;color:#475569;font-size:11px;text-transform:uppercase;font-weight:800}
            .cfe-table input,.cfe-table select,.cfe-table textarea{width:100%;border:1px solid #cbd5e1;border-radius:8px;padding:6px 8px;font-size:12px;background:#fff}
            .cfe-table textarea{min-height:60px;resize:vertical}.cfe-link-delete{color:#be123c;cursor:pointer;font-weight:700}
            .cfe-section-tabs{padding:0 16px 16px}.cfe-section-tab{border:1px solid #cbd5e1;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:700;cursor:pointer;background:#fff;color:#334155}.cfe-section-tab.active{background:#0f172a;border-color:#0f172a;color:#fff}
            .cfe-rowhead{min-width:220px;background:#fff}.cfe-code{display:block;color:#64748b;font-size:11px;margin-top:4px}
            .cfe-matrix-cell{display:flex;align-items:stretch;border:1px solid #cbd5e1;border-radius:8px;background:#fff}.cfe-matrix-cell input.cfe-matrix-input{border:none!important;border-radius:0 8px 8px 0!important;flex:1;min-width:0!important;background:transparent!important}
            .cfe-matrix-format-dropdown{display:flex;align-items:stretch}.cfe-matrix-format-btn{border:none;border-right:1px solid #cbd5e1;background:#f8fafc;padding:0;color:#475569;font-size:12px;font-weight:700;width:32px;border-radius:8px 0 0 8px}.cfe-matrix-format-dropdown .dropdown-toggle::after{display:none!important}.cfe-matrix-cell.computed{background:#f8fafc;border-style:dashed}
            .cfe-help{padding:0 16px 16px;color:#475569;font-size:12px}.cfe-title-cell{background:#fafafa}.cfe-fullscreen{position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;z-index:9999!important;margin:0!important;border-radius:0!important;display:flex;flex-direction:column}.cfe-fullscreen .cfe-table-wrap,.cfe-fullscreen .cfe-matrix-wrap{flex:1;max-height:none}
            @media (max-width:1250px){.cfe-shell{grid-template-columns:1fr}.cfe-grid.filters,.cfe-grid.note-meta,.cfe-grid.section-meta,.cfe-grid.note-content{grid-template-columns:1fr}.cfe-field.span-2{grid-column:auto}}
        `;
        document.head.appendChild(style);
    }

    render_shell() {
        this.wrapper.html(`
            <div class="cfe-shell">
                <aside class="cfe-sidebar">
                    <div class="cfe-sidebar-head">
                        <h3>${__("Editor de Notas")}</h3>
                        <p>${__("Trabaja la nota desde esta page sin salir al doctype base.")}</p>
                    </div>
                    <div class="cfe-filters" data-role="filters"></div>
                    <div class="cfe-summary" data-role="summary"></div>
                    <div class="cfe-note-list" data-role="note-list"></div>
                </aside>
                <section class="cfe-main" data-role="editor"></section>
            </div>
        `);
        this.$filters = this.wrapper.find('[data-role="filters"]');
        this.$summary = this.wrapper.find('[data-role="summary"]');
        this.$noteList = this.wrapper.find('[data-role="note-list"]');
        this.$editor = this.wrapper.find('[data-role="editor"]');
    }

    bind_events() {
        this.wrapper.on("change", "[data-filter='cliente']", (event) => this.load_bootstrap({ cliente: event.currentTarget.value || null, package_name: null, note_name: null }));
        this.wrapper.on("change", "[data-filter='anio']", (event) => this.load_bootstrap({ anio: this.asInt(event.currentTarget.value, new Date().getFullYear()), package_name: null, note_name: null }));
        this.wrapper.on("change", "[data-filter='mes']", (event) => this.load_bootstrap({ mes: event.currentTarget.value || null, package_name: null, note_name: null }));
        this.wrapper.on("change", "[data-filter='package']", (event) => this.load_bootstrap({ package_name: event.currentTarget.value || null, note_name: null }));
        this.wrapper.on("click", "[data-action='refresh-bootstrap']", () => this.load_bootstrap({}, true));
        this.wrapper.on("click", "[data-action='open-package']", () => this.open_package_form());
        this.wrapper.on("click", "[data-action='open-note-list']", () => this.open_note_list());
        this.wrapper.on("click", ".cfe-note-item", (event) => {
            const noteName = event.currentTarget.dataset.noteName;
            if (noteName) this.load_bootstrap({ note_name: noteName });
        });
        this.wrapper.on("change", ".cfe-note-field", (event) => this.update_note_field(event));
        this.wrapper.on("click", "[data-action='open-note-form']", () => this.open_current_note_form());
        this.wrapper.on("click", "[data-action='create-note-inline']", () => this.open_create_note_dialog());
        this.wrapper.on("click", "[data-action='add-figure']", () => this.add_figure());
        this.wrapper.on("click", ".cfe-delete-figure", (event) => this.delete_figure(this.asInt(event.currentTarget.dataset.index, -1)));
        this.wrapper.on("change", ".cfe-figure-field", (event) => this.update_figure_field(event));
        this.wrapper.on("click", "[data-action='add-section']", () => this.add_section());
        this.wrapper.on("click", "[data-action='duplicate-section']", () => this.duplicate_current_section());
        this.wrapper.on("click", "[data-action='delete-section']", () => this.delete_current_section());
        this.wrapper.on("click", ".cfe-section-tab", (event) => {
            this.state.current_section_id = event.currentTarget.dataset.sectionId || null;
            this.render_editor();
        });
        this.wrapper.on("change", ".cfe-section-field", (event) => this.update_section_field(event));
        this.wrapper.on("click", "[data-action='add-column']", () => this.add_column());
        this.wrapper.on("click", ".cfe-delete-column", (event) => this.delete_column(this.asInt(event.currentTarget.dataset.index, -1)));
        this.wrapper.on("change", ".cfe-column-field", (event) => this.update_column_field(event));
        this.wrapper.on("click", "[data-action='add-row']", () => this.add_row());
        this.wrapper.on("click", ".cfe-delete-row", (event) => this.delete_row(this.asInt(event.currentTarget.dataset.index, -1)));
        this.wrapper.on("change", ".cfe-row-field", (event) => this.update_row_field(event));
        this.wrapper.on("change", ".cfe-matrix-input", (event) => this.update_matrix_value(event));
        this.wrapper.on("click", ".cfe-format-option", (event) => {
            event.preventDefault();
            this.update_matrix_format(event);
        });
        this.wrapper.on("click", "[data-action='refresh-matrix']", (event) => {
            event.preventDefault();
            event.stopPropagation();
            this.refresh_matrix_card();
        });
        this.wrapper.on("click", "[data-action='download-csv']", () => this.download_current_section_csv());
        this.wrapper.on("click", "[data-action='upload-csv']", () => this.open_csv_picker());
        this.wrapper.on("change", ".cfe-csv-input", (event) => this.handle_csv_upload(event));
        this.wrapper.on("click", ".cfe-toggle-fullscreen", (event) => this.toggle_fullscreen(event));
    }

    load_bootstrap(overrides = {}, force = false) {
        if (this.loading) return;
        const route = this.state.route_options || {};
        const args = {
            cliente: overrides.cliente !== undefined ? overrides.cliente : (route.cliente || this.state.cliente || null),
            anio: overrides.anio !== undefined ? overrides.anio : (route.anio || this.state.anio || null),
            mes: overrides.mes !== undefined ? overrides.mes : (route.mes || this.state.mes || null),
            package_name: overrides.package_name !== undefined ? overrides.package_name : (route.package_name || this.state.package_name || null),
            note_name: overrides.note_name !== undefined ? overrides.note_name : (route.note_name || this.state.selected_note_name || null),
        };
        const bootstrapKey = JSON.stringify(args);
        this.state.route_options = {};
        if (!force && bootstrapKey === this.last_bootstrap_key) return;
        this.loading = true;
        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_notas_eeff.asistente_notas_eeff.get_note_editor_bootstrap",
            args,
            freeze: true,
            freeze_message: __("Cargando editor de notas..."),
            callback: (r) => {
                this.absorb_bootstrap(r.message || {});
                this.last_bootstrap_key = bootstrapKey;
                this.bootstrapped = true;
                this.render_all();
            },
            always: () => {
                this.loading = false;
            },
        });
    }

    absorb_bootstrap(data) {
        this.state.cliente = data.cliente || "";
        this.state.anio = this.asInt(data.anio, this.state.anio || new Date().getFullYear());
        this.state.mes = data.mes || "";
        this.state.package_name = data.package_name || "";
        this.state.clients = data.clients || [];
        this.state.meses = data.meses || [];
        this.state.packages = data.packages || [];
        this.state.notes = data.notes || [];
        this.state.summary = data.summary || null;
        this.state.note = data.note || null;
        this.state.selected_note_name = this.get_doc()?.name || "";
        this.ensure_note_shape();
        this.ensure_current_section();
    }

    render_all() {
        this.render_filters();
        this.render_summary();
        this.render_note_list();
        this.render_editor();
    }

    render_filters() {
        this.$filters.html(`
            <div class="cfe-grid filters">
                <div class="cfe-field"><label>${__("Cliente")}</label><select data-filter="cliente"><option value=""></option>${this.options_html(this.state.clients || [], this.state.cliente)}</select></div>
                <div class="cfe-field"><label>${__("Anio")}</label><input data-filter="anio" type="number" min="1900" max="2200" value="${this.escape(this.state.anio || new Date().getFullYear())}"></div>
                <div class="cfe-field"><label>${__("Mes")}</label><select data-filter="mes"><option value=""></option>${this.options_html((this.state.meses || []).map((row) => ({ value: row, label: row })), this.state.mes)}</select></div>
                <div class="cfe-field"><label>${__("Paquete")}</label><select data-filter="package"><option value=""></option>${this.options_html(this.state.packages || [], this.state.package_name)}</select></div>
            </div>
            <div class="cfe-actions">
                <button class="cfe-btn" data-action="refresh-bootstrap">${__("Refrescar")}</button>
                <button class="cfe-btn" data-action="open-package">${__("Abrir Paquete")}</button>
                <button class="cfe-btn" data-action="open-note-list">${__("Ver Todas las Notas")}</button>
            </div>
        `);
    }

    render_summary() {
        const summary = this.state.summary;
        if (!summary) {
            this.$summary.html(`<div class="cfe-empty">${__("Selecciona un paquete para cargar su contexto y sus notas.")}</div>`);
            return;
        }
        this.$summary.html(`
            <div class="cfe-card-head" style="padding:0 0 12px 0;border:none;">
                <h3>${__("Contexto Activo")}</h3>
                <p>${this.escape(summary.package_name || "-")}</p>
            </div>
        `);
    }

    render_note_list() {
        if (!this.state.package_name) {
            this.$noteList.html(`<div class="cfe-empty">${__("No hay paquete seleccionado.")}</div>`);
            return;
        }
        if (!this.state.notes.length) {
            this.$noteList.html(`<div class="cfe-empty">${__("El paquete no tiene notas registradas.")}</div>`);
            return;
        }
        const currentName = this.get_doc()?.name || this.state.selected_note_name;
        this.$noteList.html(this.state.notes.map((note) => `
            <div class="cfe-note-item ${note.name === currentName ? "active" : ""}" data-note-name="${this.escape(note.name)}">
                <div class="cfe-note-title">
                    <strong>${this.escape(note.identificador_nota || note.numero_nota || note.name)}</strong>
                    <span class="cfe-pill ${note.estructura_nota === "Compleja" ? "complex" : "simple"}">${this.escape(note.estructura_nota || "Simple")}</span>
                </div>
                <span>${this.escape(note.titulo || __("Sin titulo"))}</span>
                <span class="cfe-pill ${this.approval_pill_class(note.estado_aprobacion)}" style="margin-top:8px;">${this.escape(note.estado_aprobacion || "Borrador")}</span>
            </div>
        `).join(""));
    }

    render_editor() {
        const doc = this.get_doc();
        if (!this.state.package_name) {
            this.state.fullscreen_cards = {};
            this.$editor.html(`<div class="cfe-empty">${__("Selecciona un paquete y luego una nota para trabajar desde esta page.")}</div>`);
            this.sync_body_scroll();
            return;
        }
        if (!doc) {
            this.state.fullscreen_cards = {};
            this.$editor.html(`<div class="cfe-empty">${__("Selecciona una nota existente o crea una nueva para abrir el editor.")}<br><button class="cfe-btn primary" style="margin-top:12px;" data-action="create-note-inline">${__("Nueva Nota")}</button></div>`);
            this.sync_body_scroll();
            return;
        }

        this.sort_current_note_data();
        const sections = this.get_sections();
        const currentSection = this.get_current_section();
        const noteIdentifier = doc.identificador_nota || this.build_note_identifier(doc.numero_nota, doc.sub_nota);
        const figuresEditor = this.render_figures_editor();
        this.$editor.html(`
            <div class="cfe-card">
                <div class="cfe-card-head"><h3>${__("Nota")} ${this.escape(noteIdentifier || "-")}</h3><p>${this.escape(doc.titulo || __("Sin titulo"))}</p></div>
                <div class="cfe-grid note-meta" style="padding:16px;">
                    ${this.note_field_html("numero_nota", __("Numero Nota"), doc.numero_nota || "", "number")}
                    ${this.note_field_html("sub_nota", __("Sub-nota"), doc.sub_nota || "", "text", __("Ejemplo: A"))}
                    ${this.note_select_html("estructura_nota", __("Estructura"), doc.estructura_nota || "Simple", ["Simple", "Compleja"])}
                    ${this.note_select_html("estado_aprobacion", __("Estado Aprobacion"), doc.estado_aprobacion || "Borrador", ["Borrador", "Revision", "Aprobado"])}
                    <div class="cfe-field span-2"><label>${__("Titulo")}</label><input class="cfe-note-field" data-fieldname="titulo" type="text" value="${this.escape(doc.titulo || "")}"></div>
                    ${this.note_field_html("tamano_letra_impresion", __("Tamano Letra Tablas"), doc.tamano_letra_impresion || 12, "number")}
                    ${this.note_field_html("ancho_tabla_impresion", __("Ancho Tabla"), doc.ancho_tabla_impresion || "100%", "text")}
                    ${this.note_select_html("alineacion_tabla_impresion", __("Alineacion Tabla"), doc.alineacion_tabla_impresion || "Centro", ["Izquierda", "Centro", "Derecha"])}
                </div>
                <div class="cfe-grid note-content" style="padding:0 16px 16px;">
                    <div class="cfe-field"><label>${__("Contenido Narrativo")}</label><textarea class="cfe-note-field" data-fieldname="contenido_narrativo">${this.escape(doc.contenido_narrativo || "")}</textarea></div>
                    <div class="cfe-field"><label>${__("Observaciones")}</label><textarea class="cfe-note-field" data-fieldname="observaciones">${this.escape(doc.observaciones || "")}</textarea></div>
                </div>
                <div class="cfe-toolbar" style="padding:0 16px 16px;"><button class="cfe-btn" data-action="open-note-form">${__("Abrir Formulario Base")}</button></div>
            </div>
            ${figuresEditor}
            ${doc.estructura_nota === "Compleja" ? this.render_sections_workspace(currentSection) : ""}
        `);
        this.sync_body_scroll();
    }

    render_figures_editor() {
        const figures = this.get_figures();
        const isExpanded = this.is_fullscreen_card("figures_note");
        return `
            <div class="cfe-card ${isExpanded ? "cfe-fullscreen" : ""}" data-fullscreen-key="figures_note">
                <div class="cfe-card-head"><h3>${__("Cifras de la Nota")}</h3><p>${__("Edita conceptos, montos, formulas y reglas de impresion para la nota, aun si tambien tiene secciones complejas.")}</p></div>
                <div class="cfe-toolbar" style="padding:12px 16px 0;">
                    <button class="cfe-btn secondary" data-action="add-figure">${__("Agregar Cifra")}</button>
                    <button class="cfe-btn cfe-toggle-fullscreen" style="margin-left:auto;">${isExpanded ? __("Contraer") : __("Expandir")}</button>
                </div>
                <div class="cfe-table-wrap">
                    <table class="cfe-table">
                        <thead><tr><th>${__("Codigo")}</th><th>${__("Concepto")}</th><th>${__("Nivel")}</th><th>${__("Formato")}</th><th>${__("Actual")}</th><th>${__("Comparativo")}</th><th>${__("Titulo")}</th><th>${__("Linea Blanco")}</th><th>${__("Manual")}</th><th>${__("Auto")}</th><th>${__("Formula")}</th><th>${__("Total")}</th><th>${__("Subtotal")}</th><th>${__("No Imprimir")}</th><th></th></tr></thead>
                        <tbody>
                            ${figures.length ? figures.map((row, index) => `
                                <tr>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="codigo_cifra" value="${this.escape(row.codigo_cifra || "")}"></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="concepto" value="${this.escape(row.concepto || "")}"></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="nivel" type="number" min="1" value="${this.escape(row.nivel || 1)}"></td>
                                    <td><select class="cfe-figure-field" data-index="${index}" data-fieldname="formato_numero">${this.select_options(["Numero", "Moneda", "Porcentaje", "Texto"], this.get_figure_format(row))}</select></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="monto_actual" value="${this.escape(this.get_figure_input_value(row, "monto_actual"))}" ${this.figure_disables_values(row) ? "disabled" : ""}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="monto_comparativo" value="${this.escape(this.get_figure_input_value(row, "monto_comparativo"))}" ${this.figure_disables_values(row) ? "disabled" : ""}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="es_titulo" type="checkbox" ${this.checked(row.es_titulo)}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="es_linea_blanco" type="checkbox" ${this.checked(row.es_linea_blanco)}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="es_manual" type="checkbox" ${this.checked(row.es_manual)}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="calculo_automatico" type="checkbox" ${this.checked(row.calculo_automatico)}></td>
                                    <td><textarea class="cfe-figure-field" data-index="${index}" data-fieldname="formula_cifras" ${this.figure_disables_formula(row) ? "disabled" : ""}>${this.escape(row.formula_cifras || "")}</textarea></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="es_total" type="checkbox" ${this.checked(row.es_total)}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="es_subtotal" type="checkbox" ${this.checked(row.es_subtotal)}></td>
                                    <td><input class="cfe-figure-field" data-index="${index}" data-fieldname="no_imprimir" type="checkbox" ${this.checked(row.no_imprimir)}></td>
                                    <td><span class="cfe-link-delete cfe-delete-figure" data-index="${index}">${__("Eliminar")}</span></td>
                                </tr>
                            `).join("") : `<tr><td colspan="15">${__("La nota todavia no tiene cifras.")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    render_sections_workspace(currentSection) {
        const sections = this.get_sections();
        return `
            <div class="cfe-card">
                <div class="cfe-card-head"><h3>${__("Secciones Complejas")}</h3><p>${__("Organiza narrativa y tablas dentro de la misma nota.")}</p></div>
                <div class="cfe-toolbar" style="padding:12px 16px 0;">
                    <button class="cfe-btn secondary" data-action="add-section">${__("Agregar Seccion")}</button>
                    ${currentSection ? `<button class="cfe-btn" data-action="duplicate-section">${__("Duplicar Actual")}</button>` : ""}
                    ${currentSection ? `<button class="cfe-btn danger" data-action="delete-section">${__("Eliminar Actual")}</button>` : ""}
                </div>
                <div class="cfe-section-tabs">
                    ${sections.map((section) => `<button class="cfe-section-tab ${section._client_id === this.state.current_section_id ? "active" : ""}" data-section-id="${this.escape(section._client_id)}">${this.escape(section.codigo_seccion || __("Seccion"))}</button>`).join("")}
                </div>
            </div>
            ${currentSection ? this.render_section_editor(currentSection) : `<div class="cfe-empty">${__("Agrega al menos una seccion para estructurar la nota compleja.")}</div>`}
        `;
    }

    render_section_editor(section) {
        const useNarrative = this.section_uses_narrative(section);
        return `
            <div class="cfe-card">
                <div class="cfe-card-head"><h3>${__("Seccion")} ${this.escape(section.codigo_seccion || "")}</h3><p>${__("Edita la seccion actual y su estructura interna sin abandonar la nota.")}</p></div>
                <div class="cfe-grid section-meta" style="padding:16px;">
                    <div class="cfe-field"><label>${__("Codigo Seccion")}</label><input class="cfe-section-field" data-fieldname="codigo_seccion" type="text" value="${this.escape(section.codigo_seccion || "")}"></div>
                    <div class="cfe-field"><label>${__("Titulo Seccion")}</label><input class="cfe-section-field" data-fieldname="titulo_seccion" type="text" value="${this.escape(section.titulo_seccion || "")}"></div>
                    <div class="cfe-field"><label>${__("Tipo Seccion")}</label><select class="cfe-section-field" data-fieldname="tipo_seccion">${this.select_options(["Narrativa", "Tabla", "Mixta"], section.tipo_seccion || "Narrativa")}</select></div>
                    <div class="cfe-field"><label>${__("Orden")}</label><input class="cfe-section-field" data-fieldname="orden" type="number" value="${this.escape(section.orden || 1)}"></div>
                    <div class="cfe-field"><label>${__("Mostrar Titulo")}</label><input class="cfe-section-field" data-fieldname="mostrar_titulo" type="checkbox" ${this.checked(section.mostrar_titulo)}></div>
                    <div class="cfe-field span-2"><label>${__("Observaciones")}</label><textarea class="cfe-section-field" data-fieldname="observaciones">${this.escape(section.observaciones || "")}</textarea></div>
                    ${useNarrative ? `<div class="cfe-field span-2"><label>${__("Narrativa de la Seccion")}</label><textarea class="cfe-section-field" data-fieldname="contenido_narrativo">${this.escape(section.contenido_narrativo || "")}</textarea></div>` : ""}
                </div>
            </div>
            ${this.render_columns_editor(section)}${this.render_rows_editor(section)}${this.render_matrix(section)}
        `;
    }

    render_columns_editor(section) {
        const rows = this.get_section_columns(section);
        return `
            <div class="cfe-card">
                <div class="cfe-card-head"><h3>${__("Columnas Tabulares")}</h3><p>${__("Controla etiquetas, tipo de dato, alineacion y formulas por columna.")}</p></div>
                <div class="cfe-toolbar" style="padding:12px 16px 0;">
                    <button class="cfe-btn secondary" data-action="add-column">${__("Agregar Columna")}</button>
                    <button class="cfe-btn" data-action="download-csv">${__("Descargar CSV")}</button>
                    <button class="cfe-btn" data-action="upload-csv">${__("Cargar CSV")}</button>
                    <button class="cfe-btn cfe-toggle-fullscreen" style="margin-left:auto;">${__("Expandir")}</button>
                    <input type="file" class="cfe-csv-input" accept=".csv,text/csv,.txt,.tsv" style="display:none">
                </div>
                <div class="cfe-table-wrap">
                    <table class="cfe-table">
                        <thead><tr><th>${__("Tabla")}</th><th>${__("Codigo")}</th><th>${__("Etiqueta")}</th><th>${__("Grupo")}</th><th>${__("Tipo")}</th><th>${__("Alineacion")}</th><th>${__("Entero")}</th><th>${__("Auto")}</th><th>${__("Formula")}</th><th></th></tr></thead>
                        <tbody>
                            ${rows.length ? rows.map((row, index) => `
                                <tr>
                                    <td><input class="cfe-column-field" data-index="${index}" data-fieldname="codigo_tabla" value="${this.escape(row.codigo_tabla || "")}"></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-fieldname="codigo_columna" data-original-code="${this.escape(row.codigo_columna || "")}" value="${this.escape(row.codigo_columna || "")}"></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-fieldname="etiqueta" value="${this.escape(row.etiqueta || "")}"></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-fieldname="grupo_columna" value="${this.escape(row.grupo_columna || "")}"></td>
                                    <td><select class="cfe-column-field" data-index="${index}" data-fieldname="tipo_dato">${this.select_options(["Numero", "Moneda", "Porcentaje", "Texto"], row.tipo_dato || "Numero")}</select></td>
                                    <td><select class="cfe-column-field" data-index="${index}" data-fieldname="alineacion">${this.select_options(["Left", "Center", "Right"], row.alineacion || "Right")}</select></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-fieldname="redondear_entero" type="checkbox" ${this.checked(row.redondear_entero)}></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-fieldname="calculo_automatico" type="checkbox" ${this.checked(row.calculo_automatico)}></td>
                                    <td><textarea class="cfe-column-field" data-index="${index}" data-fieldname="formula_columnas">${this.escape(row.formula_columnas || "")}</textarea></td>
                                    <td><span class="cfe-link-delete cfe-delete-column" data-index="${index}">${__("Eliminar")}</span></td>
                                </tr>
                            `).join("") : `<tr><td colspan="10">${__("La seccion no tiene columnas.")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    render_rows_editor(section) {
        const rows = this.get_section_rows(section);
        return `
            <div class="cfe-card">
                <div class="cfe-card-head"><h3>${__("Filas Tabulares")}</h3><p>${__("Define descripcion, nivel, tipo y formulas por fila.")}</p></div>
                <div class="cfe-toolbar" style="padding:12px 16px 0;">
                    <button class="cfe-btn secondary" data-action="add-row">${__("Agregar Fila")}</button>
                    <button class="cfe-btn cfe-toggle-fullscreen" style="margin-left:auto;">${__("Expandir")}</button>
                </div>
                <div class="cfe-table-wrap">
                    <table class="cfe-table">
                        <thead><tr><th>${__("Tabla")}</th><th>${__("Codigo")}</th><th>${__("Descripcion")}</th><th>${__("Nivel")}</th><th>${__("Tipo")}</th><th>${__("Auto")}</th><th>${__("Formula")}</th><th>${__("Negrita")}</th><th>${__("Subrayado")}</th><th></th></tr></thead>
                        <tbody>
                            ${rows.length ? rows.map((row, index) => `
                                <tr>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="codigo_tabla" value="${this.escape(row.codigo_tabla || "")}"></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="codigo_fila" data-original-code="${this.escape(row.codigo_fila || "")}" value="${this.escape(row.codigo_fila || "")}"></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="descripcion" value="${this.escape(row.descripcion || "")}"></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="nivel" type="number" min="1" value="${this.escape(row.nivel || 1)}"></td>
                                    <td><select class="cfe-row-field" data-index="${index}" data-fieldname="tipo_fila">${this.select_options(["Detalle", "Subtotal", "Total", "Titulo"], row.tipo_fila || "Detalle")}</select></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="calculo_automatico" type="checkbox" ${this.checked(row.calculo_automatico)}></td>
                                    <td><textarea class="cfe-row-field" data-index="${index}" data-fieldname="formula_filas">${this.escape(row.formula_filas || "")}</textarea></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="negrita" type="checkbox" ${this.checked(row.negrita)}></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-fieldname="subrayado" type="checkbox" ${this.checked(row.subrayado)}></td>
                                    <td><span class="cfe-link-delete cfe-delete-row" data-index="${index}">${__("Eliminar")}</span></td>
                                </tr>
                            `).join("") : `<tr><td colspan="10">${__("La seccion no tiene filas.")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    render_matrix(section) {
        const rows = this.get_section_rows(section);
        const columns = this.get_section_columns(section);
        const groups = this.build_column_groups(columns);
        const hasGroups = groups.length > 0;
        const matrix = this.compute_matrix(section);
        return `
            <div class="cfe-card" data-role="matrix-card">
                <div class="cfe-card-head"><h3>${__("Matriz Visual")}</h3><p>${__("Edita celdas manuales y revisa valores calculados en tiempo real.")}</p></div>
                <div class="cfe-toolbar" style="padding:12px 16px 0;"><button type="button" class="cfe-btn" data-action="refresh-matrix">${__("Refrescar")}</button><button type="button" class="cfe-btn cfe-toggle-fullscreen" style="margin-left:auto;">${__("Expandir")}</button></div>
                <div class="cfe-matrix-wrap" data-role="matrix-wrap">
                    ${rows.length && columns.length ? `
                        <table class="cfe-matrix-table">
                            <thead>
                                ${hasGroups ? `
                                    <tr><th class="cfe-rowhead" rowspan="2">${__("Fila / Columna")}</th>${groups.map((group) => {
                                        if (group.standalone) {
                                            const column = group.columns[0];
                                            return `<th rowspan="2"><div>${this.escape(column.etiqueta || column.codigo_columna)}</div><span class="cfe-code">${this.escape(column.codigo_columna)}</span></th>`;
                                        }
                                        return `<th colspan="${group.span}">${this.escape(group.label)}</th>`;
                                    }).join("")}</tr>
                                    <tr>${groups.map((group) => group.standalone ? "" : group.columns.map((column) => `<th><div>${this.escape(column.etiqueta || column.codigo_columna)}</div><span class="cfe-code">${this.escape(column.codigo_columna)}</span></th>`).join("")).join("")}</tr>
                                ` : `<tr><th class="cfe-rowhead">${__("Fila / Columna")}</th>${columns.map((column) => `<th><div>${this.escape(column.etiqueta || column.codigo_columna)}</div><span class="cfe-code">${this.escape(column.codigo_columna)}</span></th>`).join("")}</tr>`}
                            </thead>
                            <tbody>
                                ${rows.map((row) => `
                                    <tr>
                                        <td class="cfe-rowhead"><strong>${this.escape(row.descripcion || row.codigo_fila)}</strong><span class="cfe-code">${this.escape(row.codigo_fila || "")}</span></td>
                                        ${columns.filter((column) => column.codigo_tabla === row.codigo_tabla).map((column) => {
                                            if ((row.tipo_fila || "Detalle") === "Titulo") return `<td class="cfe-title-cell"></td>`;
                                            const key = `${row.codigo_tabla}::${row.codigo_fila}::${column.codigo_columna}`;
                                            const cell = matrix[key] || { value: "", is_manual: false, is_computed: false, format: column.tipo_dato || "Numero", round: column.redondear_entero || 0 };
                                            const symbol = cell.format === "Moneda" ? "$" : cell.format === "Porcentaje" ? "%" : cell.format === "Texto" ? "T" : "#";
                                            return `<td><div class="cfe-matrix-cell ${cell.is_computed && !cell.is_manual ? "computed" : ""}"><div class="dropdown cfe-matrix-format-dropdown"><button class="cfe-matrix-format-btn dropdown-toggle" type="button" data-toggle="dropdown">${symbol}</button><div class="dropdown-menu"><a class="dropdown-item cfe-format-option" href="#" data-format="Numero" data-table-code="${this.escape(row.codigo_tabla)}" data-row-code="${this.escape(row.codigo_fila)}" data-column-code="${this.escape(column.codigo_columna)}"># ${__("Numero")}</a><a class="dropdown-item cfe-format-option" href="#" data-format="Moneda" data-table-code="${this.escape(row.codigo_tabla)}" data-row-code="${this.escape(row.codigo_fila)}" data-column-code="${this.escape(column.codigo_columna)}">$ ${__("Moneda")}</a><a class="dropdown-item cfe-format-option" href="#" data-format="Porcentaje" data-table-code="${this.escape(row.codigo_tabla)}" data-row-code="${this.escape(row.codigo_fila)}" data-column-code="${this.escape(column.codigo_columna)}">% ${__("Porcentaje")}</a><a class="dropdown-item cfe-format-option" href="#" data-format="Texto" data-table-code="${this.escape(row.codigo_tabla)}" data-row-code="${this.escape(row.codigo_fila)}" data-column-code="${this.escape(column.codigo_columna)}">T ${__("Texto")}</a><div class="dropdown-divider"></div><a class="dropdown-item cfe-format-option" href="#" data-format="ToggleRound" data-table-code="${this.escape(row.codigo_tabla)}" data-row-code="${this.escape(row.codigo_fila)}" data-column-code="${this.escape(column.codigo_columna)}">${cell.round ? "[x]" : "[ ]"} ${__("Redondear entero")}</a></div></div><input class="cfe-matrix-input" data-table-code="${this.escape(row.codigo_tabla)}" data-row-code="${this.escape(row.codigo_fila)}" data-column-code="${this.escape(column.codigo_columna)}" value="${this.escape(cell.value ?? "")}"></div></td>`;
                                        }).join("")}
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    ` : `<div class="cfe-empty">${__("Define al menos una fila y una columna para usar la matriz tabular.")}</div>`}
                </div>
                <div class="cfe-help">${__("Las formulas aceptan codigos separados por coma, punto y coma o salto de linea. Ejemplo: +VENTAS,-DEVOLUCIONES.")}</div>
            </div>
        `;
    }
    open_create_note_dialog() {
        if (!this.state.package_name) {
            frappe.msgprint(__("Selecciona primero un paquete valido."));
            return;
        }
        const summary = this.state.summary || {};
        const dialog = new frappe.ui.Dialog({
            title: __("Nueva Nota EEFF"),
            fields: [
                { fieldname: "numero_nota", fieldtype: "Int", label: __("Numero Nota"), reqd: 1, default: summary.next_numero_nota || 1 },
                { fieldname: "sub_nota", fieldtype: "Data", label: __("Sub-nota") },
                { fieldname: "titulo", fieldtype: "Data", label: __("Titulo"), reqd: 1 },
                { fieldname: "estructura_nota", fieldtype: "Select", label: __("Estructura"), options: "Simple\nCompleja", default: "Simple", reqd: 1 },
                { fieldname: "tamano_letra_impresion", fieldtype: "Float", label: __("Tamano Letra Tablas"), default: 12 },
                { fieldname: "ancho_tabla_impresion", fieldtype: "Data", label: __("Ancho Tabla"), default: "100%" },
                { fieldname: "alineacion_tabla_impresion", fieldtype: "Select", label: __("Alineacion Tabla"), options: "Izquierda\nCentro\nDerecha", default: "Centro" },
                { fieldname: "contenido_narrativo", fieldtype: "Small Text", label: __("Contenido Narrativo Base") },
                { fieldname: "observaciones", fieldtype: "Small Text", label: __("Observaciones") },
            ],
            primary_action_label: __("Crear"),
            primary_action: (values) => {
                frappe.call({
                    method: "mfi_tools.mfi_tools.page.asistente_notas_eeff.asistente_notas_eeff.create_note_for_editor",
                    args: {
                        package_name: this.state.package_name,
                        numero_nota: values.numero_nota,
                        sub_nota: values.sub_nota,
                        titulo: values.titulo,
                        estructura_nota: values.estructura_nota,
                        contenido_narrativo: values.contenido_narrativo,
                        observaciones: values.observaciones,
                        tamano_letra_impresion: values.tamano_letra_impresion,
                        ancho_tabla_impresion: values.ancho_tabla_impresion,
                        alineacion_tabla_impresion: values.alineacion_tabla_impresion,
                    },
                    freeze: true,
                    freeze_message: __("Creando nota..."),
                    callback: (r) => {
                        this.absorb_bootstrap(r.message || {});
                        this.render_all();
                        dialog.hide();
                        frappe.show_alert({ indicator: "green", message: __("Nota creada") });
                    },
                });
            },
        });
        dialog.show();
    }

    save_current_note() {
        if (!this.get_doc()?.name) {
            frappe.msgprint(__("No hay una nota cargada."));
            return;
        }
        this.sort_current_note_data();
        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_notas_eeff.asistente_notas_eeff.save_note_editor",
            args: { note_payload: JSON.stringify(this.state.note) },
            freeze: true,
            freeze_message: __("Guardando nota..."),
            callback: (r) => {
                this.absorb_bootstrap(r.message || {});
                this.render_all();
                frappe.show_alert({ indicator: "green", message: __("Nota guardada") });
            },
        });
    }

    update_note_field(event) {
        const doc = this.get_doc();
        if (!doc) return;
        const fieldname = event.currentTarget.dataset.fieldname;
        const rawValue = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (fieldname === "estructura_nota") {
            if (rawValue === "Simple" && this.get_sections().length) {
                frappe.confirm(
                    __("Cambiar la nota a Simple eliminara sus secciones complejas al guardar. Continuar?"),
                    () => {
                        doc.estructura_nota = "Simple";
                        this.state.note.sections = [];
                        this.state.current_section_id = null;
                        this.render_editor();
                    },
                    () => this.render_editor()
                );
                return;
            }
            doc.estructura_nota = rawValue || "Simple";
            if (doc.estructura_nota === "Compleja" && !this.get_sections().length) {
                this.add_section(false);
            }
            this.render_editor();
            return;
        }
        if (fieldname === "numero_nota") {
            doc.numero_nota = this.asInt(rawValue, doc.numero_nota || 0);
            return;
        }
        if (fieldname === "sub_nota") {
            doc.sub_nota = String(rawValue || "").trim();
            return;
        }
        if (fieldname === "tamano_letra_impresion") {
            doc.tamano_letra_impresion = this.asFloat(rawValue);
            return;
        }
        doc[fieldname] = rawValue;
    }

    update_figure_field(event) {
        const row = this.get_figures()[this.asInt(event.currentTarget.dataset.index, -1)];
        if (!row) return;
        const fieldname = event.currentTarget.dataset.fieldname;
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        const format = this.get_figure_format(row);
        if (fieldname === "es_linea_blanco") {
            row.es_linea_blanco = value ? 1 : 0;
            this.sync_blank_figure(row);
            this.render_editor();
            return;
        }
        if (fieldname === "es_titulo") {
            row.es_titulo = value ? 1 : 0;
            this.sync_title_figure(row);
            this.render_editor();
            return;
        }
        if (fieldname === "formato_numero") {
            row.formato_numero = ["Numero", "Moneda", "Porcentaje", "Texto"].includes(String(value || "")) ? String(value) : "Moneda";
            if (row.formato_numero === "Texto") {
                if (!String(row.valor_texto_actual || "").trim() && row.monto_actual !== null && row.monto_actual !== undefined && row.monto_actual !== "") {
                    row.valor_texto_actual = String(row.monto_actual);
                }
                if (!String(row.valor_texto_comparativo || "").trim() && row.monto_comparativo !== null && row.monto_comparativo !== undefined && row.monto_comparativo !== "") {
                    row.valor_texto_comparativo = String(row.monto_comparativo);
                }
                row.es_manual = 1;
                row.calculo_automatico = 0;
                row.formula_cifras = "";
            }
            this.sync_figure_presentation_fields(row);
            this.render_editor();
            return;
        }
        if (["monto_actual", "monto_comparativo"].includes(fieldname)) {
            const textField = fieldname === "monto_actual" ? "valor_texto_actual" : "valor_texto_comparativo";
            if (format === "Texto") {
                row[textField] = String(value || "");
                row[fieldname] = null;
                return;
            }
            row[fieldname] = value === "" ? null : this.asFloat(value);
            return;
        }
        if (fieldname === "nivel") {
            row.nivel = Math.max(this.asInt(value, 1), 1);
            return;
        }
        row[fieldname] = fieldname === "codigo_cifra" ? String(value || "").trim().toUpperCase() : value;
        this.sync_figure_presentation_fields(row);
    }

    add_figure() {
        const doc = this.get_doc();
        if (!doc) return;
        doc.cifras_nota = doc.cifras_nota || [];
        const next = doc.cifras_nota.length + 1;
        doc.cifras_nota.push({
            codigo_cifra: `CIFRA_${String(next).padStart(2, "0")}`,
            concepto: __("Concepto {0}", [next]),
            nivel: 1,
            es_manual: 1,
            origen_dato: "Manual",
            calculo_automatico: 0,
            formula_cifras: "",
            no_imprimir: 0,
            negrita: 0,
            subrayado: 0,
            es_titulo: 0,
            es_linea_blanco: 0,
            es_total: 0,
            es_subtotal: 0,
            formato_numero: "Moneda",
            valor_texto_actual: "",
            valor_texto_comparativo: "",
            monto_actual: 0,
            monto_comparativo: 0,
        });
        this.render_editor();
    }

    figure_disables_values(row) {
        return this.truthy(row?.es_titulo) || this.truthy(row?.es_linea_blanco);
    }

    figure_disables_formula(row) {
        return this.truthy(row?.es_titulo) || this.truthy(row?.es_linea_blanco) || this.get_figure_format(row) === "Texto";
    }

    clear_figure_amounts(row) {
        row.monto_actual = null;
        row.monto_comparativo = null;
        row.valor_texto_actual = "";
        row.valor_texto_comparativo = "";
    }

    sync_blank_figure(row) {
        if (!this.truthy(row?.es_linea_blanco)) return;
        row.concepto = "";
        row.formato_numero = "Numero";
        row.es_titulo = 0;
        row.es_total = 0;
        row.es_subtotal = 0;
        row.negrita = 0;
        row.subrayado = 0;
        row.calculo_automatico = 0;
        row.es_manual = 0;
        row.formula_cifras = "";
        this.clear_figure_amounts(row);
    }

    sync_title_figure(row) {
        if (!this.truthy(row?.es_titulo)) return;
        row.es_linea_blanco = 0;
        row.es_total = 0;
        row.es_subtotal = 0;
        row.calculo_automatico = 0;
        row.formula_cifras = "";
        this.clear_figure_amounts(row);
    }

    sync_figure_presentation_fields(row) {
        if (!row) return;
        if (this.truthy(row.es_linea_blanco)) {
            this.sync_blank_figure(row);
            return;
        }
        if (this.truthy(row.es_titulo)) {
            this.sync_title_figure(row);
        }
    }

    delete_figure(index) {
        const doc = this.get_doc();
        if (!doc || index < 0) return;
        doc.cifras_nota.splice(index, 1);
        this.render_editor();
    }

    add_section(renderNow = true) {
        if (!this.state.note) return;
        this.state.note.sections = this.state.note.sections || [];
        const next = this.state.note.sections.length + 1;
        const section = {
            _client_id: this.make_local_id("SECTION"),
            codigo_seccion: this.build_unique_section_code(),
            tipo_seccion: "Tabla",
            titulo_seccion: __("Seccion {0}", [next]),
            orden: next,
            mostrar_titulo: 1,
            contenido_narrativo: "",
            observaciones: "",
            columnas_tabulares: [],
            filas_tabulares: [],
            celdas_tabulares: [],
        };
        this.state.note.sections.push(section);
        this.state.current_section_id = section._client_id;
        if (renderNow) this.render_editor();
    }

    duplicate_current_section() {
        const section = this.get_current_section();
        if (!section) return;
        const clone = JSON.parse(JSON.stringify(section));
        clone.name = "";
        clone.nombre_seccion = "";
        clone._client_id = this.make_local_id("SECTION");
        clone.codigo_seccion = this.build_unique_section_code(section.codigo_seccion || "SEC");
        clone.titulo_seccion = section.titulo_seccion ? `${section.titulo_seccion} (${__("Copia")})` : __("Seccion Copia");
        clone.orden = this.get_sections().length + 1;
        this.state.note.sections.push(clone);
        this.state.current_section_id = clone._client_id;
        this.render_editor();
    }

    delete_current_section() {
        const current = this.get_current_section();
        if (!current) return;
        frappe.confirm(__("Se eliminara la seccion actual y toda su estructura. Continuar?"), () => {
            this.state.note.sections = (this.state.note.sections || []).filter((row) => row._client_id !== current._client_id);
            this.ensure_current_section();
            this.render_editor();
        });
    }

    update_section_field(event) {
        const section = this.get_current_section();
        if (!section) return;
        const fieldname = event.currentTarget.dataset.fieldname;
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (fieldname === "orden") {
            section.orden = this.asInt(value, section.orden || 0);
            this.render_editor();
            return;
        }
        if (fieldname === "codigo_seccion") {
            section.codigo_seccion = this.normalize_code(value, "SEC");
            this.render_editor();
            return;
        }
        if (fieldname === "tipo_seccion") {
            section.tipo_seccion = value || "Narrativa";
            this.render_editor();
            return;
        }
        section[fieldname] = value;
    }

    add_column() {
        const section = this.get_current_section();
        if (!section) return;
        section.columnas_tabulares = section.columnas_tabulares || [];
        const next = section.columnas_tabulares.length + 1;
        section.columnas_tabulares.push({
            codigo_tabla: "TABLA_01",
            codigo_columna: `COL_${String(next).padStart(2, "0")}`,
            etiqueta: __("Columna {0}", [next]),
            tipo_dato: "Numero",
            alineacion: "Right",
            grupo_columna: "",
            redondear_entero: 0,
            calculo_automatico: 0,
            formula_columnas: "",
            es_total: 0,
        });
        this.render_editor();
    }

    update_column_field(event) {
        const section = this.get_current_section();
        const row = this.get_section_columns(section)[this.asInt(event.currentTarget.dataset.index, -1)];
        if (!row) return;
        const fieldname = event.currentTarget.dataset.fieldname;
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (fieldname === "codigo_columna") {
            const previous = event.currentTarget.dataset.originalCode || row.codigo_columna;
            row.codigo_columna = this.normalize_code(value, "COL");
            (section.celdas_tabulares || []).forEach((cell) => {
                if (cell.codigo_columna === previous) cell.codigo_columna = row.codigo_columna;
            });
            this.render_editor();
            return;
        }
        row[fieldname] = fieldname === "codigo_tabla" ? this.normalize_code(value, "TABLA") : value;
    }

    delete_column(index) {
        const section = this.get_current_section();
        const row = this.get_section_columns(section)[index];
        if (!section || !row) return;
        section.columnas_tabulares = (section.columnas_tabulares || []).filter((item) => item !== row);
        section.celdas_tabulares = (section.celdas_tabulares || []).filter((cell) => !(cell.codigo_tabla === row.codigo_tabla && cell.codigo_columna === row.codigo_columna));
        this.render_editor();
    }

    add_row() {
        const section = this.get_current_section();
        if (!section) return;
        section.filas_tabulares = section.filas_tabulares || [];
        const next = section.filas_tabulares.length + 1;
        section.filas_tabulares.push({
            codigo_tabla: "TABLA_01",
            codigo_fila: `FILA_${String(next).padStart(2, "0")}`,
            descripcion: __("Fila {0}", [next]),
            nivel: 1,
            tipo_fila: "Detalle",
            calculo_automatico: 0,
            formula_filas: "",
            negrita: 0,
            subrayado: 0,
        });
        this.render_editor();
    }

    update_row_field(event) {
        const section = this.get_current_section();
        const row = this.get_section_rows(section)[this.asInt(event.currentTarget.dataset.index, -1)];
        if (!row) return;
        const fieldname = event.currentTarget.dataset.fieldname;
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (fieldname === "codigo_fila") {
            const previous = event.currentTarget.dataset.originalCode || row.codigo_fila;
            row.codigo_fila = this.normalize_code(value, "FILA");
            (section.celdas_tabulares || []).forEach((cell) => {
                if (cell.codigo_fila === previous) cell.codigo_fila = row.codigo_fila;
            });
            this.render_editor();
            return;
        }
        if (fieldname === "nivel") {
            row[fieldname] = this.asInt(value, 1);
            this.render_editor();
            return;
        }
        row[fieldname] = fieldname === "codigo_tabla" ? this.normalize_code(value, "TABLA") : value;
    }

    delete_row(index) {
        const section = this.get_current_section();
        const row = this.get_section_rows(section)[index];
        if (!section || !row) return;
        section.filas_tabulares = (section.filas_tabulares || []).filter((item) => item !== row);
        section.celdas_tabulares = (section.celdas_tabulares || []).filter((cell) => !(cell.codigo_tabla === row.codigo_tabla && cell.codigo_fila === row.codigo_fila));
        this.render_editor();
    }

    update_matrix_value(event) {
        const section = this.get_current_section();
        if (!section) return;
        const tableCode = event.currentTarget.dataset.tableCode;
        const rowCode = event.currentTarget.dataset.rowCode;
        const columnCode = event.currentTarget.dataset.columnCode;
        const raw = event.currentTarget.value;
        let cell = this.find_section_cell(section, tableCode, rowCode, columnCode);
        const column = this.get_section_columns(section).find((item) => item.codigo_tabla === tableCode && item.codigo_columna === columnCode);
        const defaultFormat = column?.tipo_dato || "Numero";
        if (!cell && raw === "") return;
        if (!cell) {
            cell = { codigo_tabla: tableCode, codigo_fila: rowCode, codigo_columna: columnCode, valor_numero: null, valor_texto: "", formato_numero: defaultFormat, redondear_entero: column?.redondear_entero || 0, es_manual: 0, origen_dato: "Manual", comentario: "" };
            section.celdas_tabulares = section.celdas_tabulares || [];
            section.celdas_tabulares.push(cell);
        }
        if (raw === "") {
            cell.valor_numero = null;
            cell.valor_texto = "";
            cell.es_manual = 0;
        } else if ((cell.formato_numero || defaultFormat) === "Texto") {
            cell.valor_texto = raw;
            cell.valor_numero = null;
            cell.es_manual = 1;
        } else {
            cell.valor_numero = this.asFloat(raw);
            cell.valor_texto = "";
            cell.es_manual = 1;
        }
        if (this.section_cell_is_default(cell, column)) {
            section.celdas_tabulares = (section.celdas_tabulares || []).filter((item) => item !== cell);
        }
        this.render_matrix_only();
    }

    update_matrix_format(event) {
        const section = this.get_current_section();
        if (!section) return;
        const tableCode = event.currentTarget.dataset.tableCode;
        const rowCode = event.currentTarget.dataset.rowCode;
        const columnCode = event.currentTarget.dataset.columnCode;
        const action = event.currentTarget.dataset.format;
        const column = this.get_section_columns(section).find((item) => item.codigo_tabla === tableCode && item.codigo_columna === columnCode);
        let cell = this.find_section_cell(section, tableCode, rowCode, columnCode);
        if (!cell) {
            cell = { codigo_tabla: tableCode, codigo_fila: rowCode, codigo_columna: columnCode, valor_numero: null, valor_texto: "", formato_numero: column?.tipo_dato || "Numero", redondear_entero: column?.redondear_entero || 0, es_manual: 0, origen_dato: "Manual", comentario: "" };
            section.celdas_tabulares = section.celdas_tabulares || [];
            section.celdas_tabulares.push(cell);
        }
        if (action === "ToggleRound") {
            cell.redondear_entero = cell.redondear_entero ? 0 : 1;
        } else {
            cell.formato_numero = action;
            if (action === "Texto" && cell.valor_numero !== null && cell.valor_numero !== undefined && cell.es_manual) {
                cell.valor_texto = String(cell.valor_numero);
                cell.valor_numero = null;
            } else if (action !== "Texto" && cell.valor_texto && cell.es_manual) {
                cell.valor_numero = this.asFloat(cell.valor_texto);
                cell.valor_texto = "";
            }
        }
        if (this.section_cell_is_default(cell, column)) {
            section.celdas_tabulares = (section.celdas_tabulares || []).filter((item) => item !== cell);
        }
        this.render_matrix_only();
    }

    compute_matrix(section) {
        const rows = this.get_section_rows(section);
        const columns = this.get_section_columns(section);
        const cells = this.get_section_cells(section);
        const rowMap = Object.fromEntries(rows.map((row) => [`${row.codigo_tabla}::${row.codigo_fila}`, row]));
        const colMap = Object.fromEntries(columns.map((col) => [`${col.codigo_tabla}::${col.codigo_columna}`, col]));
        const explicit = new Map(cells.map((cell) => [`${cell.codigo_tabla}::${cell.codigo_fila}::${cell.codigo_columna}`, cell]));
        const cache = new Map();

        const resolve = (tableCode, rowCode, columnCode, stack = new Set()) => {
            const key = `${tableCode}::${rowCode}::${columnCode}`;
            if (cache.has(key)) return cache.get(key);
            const row = rowMap[`${tableCode}::${rowCode}`];
            const col = colMap[`${tableCode}::${columnCode}`];
            const cell = explicit.get(key);
            if (stack.has(key)) {
                return { value: "", is_manual: false, is_computed: true, format: cell?.formato_numero || col?.tipo_dato || "Numero", round: cell?.redondear_entero ?? col?.redondear_entero ?? 0 };
            }
            stack.add(key);

            const result = { value: "", is_manual: this.truthy(cell?.es_manual), is_computed: false, format: cell?.formato_numero || col?.tipo_dato || "Numero", round: cell?.redondear_entero ?? col?.redondear_entero ?? 0 };
            const isManual = this.truthy(cell?.es_manual);
            if (!isManual && row && this.truthy(row.calculo_automatico) && row.formula_filas) {
                result.value = this.evaluate_formula(row.formula_filas, (refCode, sign) => sign * this.asFloat(resolve(tableCode, refCode, columnCode, stack).value));
                result.is_computed = true;
            } else if (!isManual && col && this.truthy(col.calculo_automatico) && col.formula_columnas) {
                result.value = this.evaluate_formula(col.formula_columnas, (refCode, sign) => sign * this.asFloat(resolve(tableCode, rowCode, refCode, stack).value));
                result.is_computed = true;
            } else if (cell) {
                result.value = cell.valor_texto ? cell.valor_texto : (cell.valor_numero ?? "");
            }
            stack.delete(key);
            cache.set(key, result);
            return result;
        };

        const output = {};
        rows.forEach((row) => {
            columns.filter((column) => column.codigo_tabla === row.codigo_tabla).forEach((column) => {
                output[`${row.codigo_tabla}::${row.codigo_fila}::${column.codigo_columna}`] = resolve(row.codigo_tabla, row.codigo_fila, column.codigo_columna);
            });
        });
        return output;
    }

    evaluate_formula(formula, resolver) {
        return String(formula || "").split(/[\n,;]+/).map((token) => token.trim()).filter(Boolean).reduce((sum, token) => {
            const sign = token.startsWith("-") ? -1 : 1;
            const code = token.replace(/^[+-]/, "").trim().toUpperCase();
            return code ? sum + resolver(code, sign) : sum;
        }, 0);
    }

    build_column_groups(columns) {
        if (!columns.some((column) => String(column.grupo_columna || "").trim())) return [];
        const groups = [];
        let current = null;
        columns.forEach((column) => {
            const label = String(column.grupo_columna || "").trim();
            if (!label) {
                groups.push({ label: "", span: 1, standalone: true, columns: [column] });
                current = null;
                return;
            }
            if (current && current.label === label) {
                current.columns.push(column);
                current.span += 1;
                return;
            }
            current = { label, span: 1, standalone: false, columns: [column] };
            groups.push(current);
        });
        return groups;
    }

    open_csv_picker() {
        const input = this.wrapper.find(".cfe-csv-input").get(0);
        if (!input) return;
        input.value = "";
        input.click();
    }

    handle_csv_upload(event) {
        const file = event.currentTarget.files && event.currentTarget.files[0];
        const section = this.get_current_section();
        if (!file || !section) return;
        const reader = new FileReader();
        reader.onload = () => {
            try {
                const parsed = this.parse_csv_table(String(reader.result || ""));
                this.apply_csv_to_section(section, parsed);
                this.render_editor();
                frappe.show_alert({ indicator: "green", message: __("CSV cargado en la seccion actual") });
            } catch (error) {
                frappe.msgprint({ title: __("CSV invalido"), indicator: "red", message: __(error.message || "No se pudo interpretar el archivo CSV.") });
            }
        };
        reader.readAsText(file, "utf-8");
    }

    parse_csv_table(content) {
        const lines = String(content || "").replace(/^\uFEFF/, "").split(/\r?\n/).filter((line) => line.trim());
        if (lines.length < 2) throw new Error(__("El archivo debe incluir encabezados y al menos una fila de datos."));
        const delimiter = this.detect_csv_delimiter(lines[0]);
        const rows = lines.map((line) => this.parse_csv_line(line, delimiter));
        const headers = rows[0].map((value) => String(value || "").trim());
        if (headers.length < 2) throw new Error(__("El archivo debe tener al menos una columna de descripcion y una columna de valores."));
        return { headers, rows: rows.slice(1) };
    }

    detect_csv_delimiter(line) {
        const candidates = [",", ";", "\t"];
        let best = ",";
        let bestCount = -1;
        candidates.forEach((candidate) => {
            const count = line.split(candidate).length;
            if (count > bestCount) {
                best = candidate;
                bestCount = count;
            }
        });
        return best;
    }

    parse_csv_line(line, delimiter) {
        const output = [];
        let current = "";
        let inQuotes = false;
        for (let idx = 0; idx < line.length; idx += 1) {
            const char = line[idx];
            const next = line[idx + 1];
            if (char === "\"") {
                if (inQuotes && next === "\"") {
                    current += "\"";
                    idx += 1;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (char === delimiter && !inQuotes) {
                output.push(current.trim());
                current = "";
            } else {
                current += char;
            }
        }
        output.push(current.trim());
        return output;
    }

    apply_csv_to_section(section, parsed) {
        const headers = parsed.headers || [];
        const dataRows = parsed.rows || [];
        const valueHeaders = headers.slice(1);
        section.tipo_seccion = section.tipo_seccion === "Mixta" ? "Mixta" : "Tabla";
        section.columnas_tabulares = [];
        section.filas_tabulares = [];
        section.celdas_tabulares = [];
        valueHeaders.forEach((header, index) => {
            section.columnas_tabulares.push({ codigo_tabla: "TABLA_01", codigo_columna: this.build_csv_column_code(header, index + 1), etiqueta: header || __("Columna {0}", [index + 1]), tipo_dato: "Moneda", alineacion: "Right", grupo_columna: "", redondear_entero: 0, calculo_automatico: 0, formula_columnas: "", es_total: 0 });
        });
        dataRows.forEach((dataRow, rowIndex) => {
            const description = String(dataRow[0] || "").trim();
            if (!description) return;
            const rowType = description.toLowerCase().startsWith("total") ? "Total" : description.toLowerCase().startsWith("subtotal") ? "Subtotal" : "Detalle";
            const rowCode = this.build_csv_row_code(description, rowIndex + 1);
            section.filas_tabulares.push({ codigo_tabla: "TABLA_01", codigo_fila: rowCode, descripcion: description, nivel: 1, tipo_fila: rowType, calculo_automatico: 0, formula_filas: "", negrita: rowType !== "Detalle" ? 1 : 0, subrayado: rowType === "Total" ? 1 : 0 });
            valueHeaders.forEach((header, colIndex) => {
                const rawValue = dataRow[colIndex + 1];
                if (rawValue === undefined || rawValue === null || String(rawValue).trim() === "") return;
                const numericValue = this.parse_csv_numeric_value(rawValue);
                section.celdas_tabulares.push({ codigo_tabla: "TABLA_01", codigo_fila: rowCode, codigo_columna: this.build_csv_column_code(header, colIndex + 1), valor_numero: numericValue, valor_texto: numericValue === null ? String(rawValue).trim() : "", formato_numero: numericValue === null ? "Texto" : "Moneda", redondear_entero: 0, es_manual: 1, origen_dato: "Manual", ultima_regla_mapeo: "", comentario: "" });
            });
        });
    }

    build_csv_column_code(header, index) { return this.normalize_code(header || `COL_${index}`, "COL"); }
    build_csv_row_code(description, index) { return this.normalize_code(description || `FILA_${index}`, "FILA"); }

    parse_csv_numeric_value(value) {
        const cleaned = String(value || "").trim().replace(/C\$/gi, "").replace(/US\$/gi, "").replace(/\s+/g, "").replace(/\(([^)]+)\)/, "-$1").replace(/,/g, "");
        if (!cleaned) return null;
        const parsed = Number(cleaned);
        return Number.isFinite(parsed) ? parsed : null;
    }

    download_current_section_csv() {
        const section = this.get_current_section();
        if (!section) return;
        const rows = this.get_section_rows(section);
        const columns = this.get_section_columns(section);
        if (!rows.length || !columns.length) {
            frappe.msgprint(__("La seccion actual no tiene datos suficientes para exportar CSV."));
            return;
        }
        const matrix = this.compute_matrix(section);
        const csvRows = [["Concepto"].concat(columns.map((column) => column.etiqueta || column.codigo_columna || ""))];
        rows.forEach((row) => {
            const values = columns.filter((column) => column.codigo_tabla === row.codigo_tabla).map((column) => {
                const cell = matrix[`${row.codigo_tabla}::${row.codigo_fila}::${column.codigo_columna}`] || { value: "" };
                return String(cell.value ?? "");
            });
            csvRows.push([row.descripcion || row.codigo_fila || ""].concat(values));
        });
        const csvContent = csvRows.map((row) => row.map((value) => {
            const text = String(value ?? "");
            return /[",\n;]/.test(text) ? `"${text.replace(/"/g, "\"\"")}"` : text;
        }).join(",")).join("\n");
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${section.codigo_seccion || "seccion"}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    toggle_fullscreen(event) {
        const $card = $(event.currentTarget).closest(".cfe-card");
        const key = String($card.data("fullscreenKey") || "").trim();
        $card.toggleClass("cfe-fullscreen");
        const isFull = $card.hasClass("cfe-fullscreen");
        if (key) {
            this.state.fullscreen_cards = this.state.fullscreen_cards || {};
            if (isFull) this.state.fullscreen_cards[key] = 1;
            else delete this.state.fullscreen_cards[key];
        }
        $(event.currentTarget).text(isFull ? __("Contraer") : __("Expandir"));
        this.sync_body_scroll();
    }

    is_fullscreen_card(key) {
        return !!(this.state.fullscreen_cards || {})[key];
    }

    sync_body_scroll() {
        const hasStateFullscreen = Object.keys(this.state.fullscreen_cards || {}).length > 0;
        const hasDomFullscreen = $(".cfe-fullscreen").length > 0;
        $("body").css("overflow", hasStateFullscreen || hasDomFullscreen ? "hidden" : "");
    }

    open_package_form() {
        if (!this.state.package_name) {
            frappe.msgprint(__("No hay paquete seleccionado."));
            return;
        }
        frappe.set_route("Form", "Paquete EEFF", this.state.package_name);
    }

    open_note_list() {
        if (!this.state.package_name) {
            frappe.set_route("List", "Nota EEFF");
            return;
        }
        frappe.set_route("List", "Nota EEFF", { paquete_eeff: this.state.package_name });
    }

    open_current_note_form() {
        const noteName = this.get_doc()?.name;
        if (!noteName) {
            frappe.msgprint(__("No hay nota seleccionada."));
            return;
        }
        frappe.set_route("Form", "Nota EEFF", noteName);
    }

    render_matrix_only() {
        const section = this.get_current_section();
        if (!section) return;
        const html = $(this.render_matrix(section)).find("[data-role='matrix-wrap']").html();
        this.wrapper.find("[data-role='matrix-wrap']").html(html);
    }

    refresh_matrix_card() {
        const section = this.get_current_section();
        if (!section) return;
        const matrixCardHtml = this.render_matrix(section);
        const $currentCard = this.wrapper.find("[data-role='matrix-card']").first();
        if ($currentCard.length) {
            $currentCard.replaceWith(matrixCardHtml);
            return;
        }
        this.render_matrix_only();
    }

    ensure_note_shape() {
        if (!this.state.note) return;
        this.state.note.sections = this.state.note.sections || [];
        this.state.note.sections.forEach((section) => {
            section._client_id = section._client_id || section.name || this.make_local_id("SECTION");
            section.columnas_tabulares = section.columnas_tabulares || [];
            section.filas_tabulares = section.filas_tabulares || [];
            section.celdas_tabulares = section.celdas_tabulares || [];
        });
        const doc = this.get_doc();
        doc.cifras_nota = doc.cifras_nota || [];
        doc.cifras_nota.forEach((row) => {
            row.nivel = Math.max(this.asInt(row.nivel, 1), 1);
            row.formato_numero = this.get_figure_format(row);
            row.valor_texto_actual = row.valor_texto_actual || "";
            row.valor_texto_comparativo = row.valor_texto_comparativo || "";
        });
    }

    ensure_current_section() {
        const sections = this.get_sections();
        if (!sections.length) {
            this.state.current_section_id = null;
            return;
        }
        if (!sections.find((row) => row._client_id === this.state.current_section_id)) {
            this.state.current_section_id = sections[0]._client_id;
        }
    }

    sort_current_note_data() {
        if (!this.state.note) return;
        const doc = this.get_doc();
        doc.cifras_nota = doc.cifras_nota || [];
        this.state.note.sections = this.sort_rows(this.state.note.sections || [], (row) => [this.asInt(row.orden, 0), String(row.codigo_seccion || "")]);
        this.state.note.sections.forEach((section) => {
            section.celdas_tabulares = this.sort_rows(section.celdas_tabulares || [], (row) => [String(row.codigo_tabla || ""), String(row.codigo_fila || ""), String(row.codigo_columna || "")]);
        });
    }
    get_doc() { return this.state.note && this.state.note.doc ? this.state.note.doc : null; }
    get_sections() { return this.state.note?.sections || []; }
    get_current_section() { return this.get_sections().find((row) => row._client_id === this.state.current_section_id) || null; }
    get_figures() { return this.get_doc()?.cifras_nota || []; }
    get_figure_format(row) {
        const format = String(row?.formato_numero || "").trim();
        return ["Numero", "Moneda", "Porcentaje", "Texto"].includes(format) ? format : "Moneda";
    }
    get_figure_input_value(row, fieldname) {
        const textField = fieldname === "monto_actual" ? "valor_texto_actual" : "valor_texto_comparativo";
        if (this.get_figure_format(row) === "Texto") return row?.[textField] ?? "";
        return row?.[fieldname] ?? "";
    }
    get_section_columns(section) { return section?.columnas_tabulares || []; }
    get_section_rows(section) { return section?.filas_tabulares || []; }
    get_section_cells(section) { return section?.celdas_tabulares || []; }
    find_section_cell(section, tableCode, rowCode, columnCode) {
        return this.get_section_cells(section).find((cell) => cell.codigo_tabla === tableCode && cell.codigo_fila === rowCode && cell.codigo_columna === columnCode) || null;
    }

    section_cell_is_default(cell, column) {
        const defaultFormat = column?.tipo_dato || "Numero";
        const defaultRound = column?.redondear_entero || 0;
        return !this.truthy(cell.es_manual)
            && !String(cell.valor_texto || "").trim()
            && (cell.valor_numero === null || cell.valor_numero === undefined || cell.valor_numero === "")
            && String(cell.formato_numero || defaultFormat) === String(defaultFormat)
            && this.asInt(cell.redondear_entero, defaultRound) === this.asInt(defaultRound, 0)
            && !String(cell.comentario || "").trim();
    }
    section_uses_narrative(section) { return ["Narrativa", "Mixta"].includes(section?.tipo_seccion || "Narrativa"); }
    section_uses_table(section) { return ["Tabla", "Mixta"].includes(section?.tipo_seccion || "Narrativa"); }
    build_unique_section_code(preferred = "SEC") {
        const existing = new Set((this.state.note?.sections || []).map((row) => String(row.codigo_seccion || "").trim().toUpperCase()).filter(Boolean));
        const base = this.normalize_code(preferred, "SEC");
        if (!existing.has(base)) return base;
        let index = (this.state.note?.sections || []).length + 1;
        let candidate = `${base}_${String(index).padStart(2, "0")}`;
        while (existing.has(candidate)) {
            index += 1;
            candidate = `${base}_${String(index).padStart(2, "0")}`;
        }
        return candidate;
    }
    build_note_identifier(numero, subNota) { const clean = String(subNota || "").trim(); return numero ? (clean ? `${numero} (${clean})` : String(numero)) : ""; }
    make_local_id(prefix) { return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`.toUpperCase(); }
    sort_rows(rows, mapper) { return (rows || []).sort((a, b) => { const left = mapper(a); const right = mapper(b); const maxLen = Math.max(left.length, right.length); for (let i = 0; i < maxLen; i += 1) { const l = left[i] ?? ""; const r = right[i] ?? ""; if (l < r) return -1; if (l > r) return 1; } return 0; }); }
    normalize_code(value, fallback) { const normalized = String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase(); return normalized || fallback; }
    note_field_html(fieldname, label, value, type = "text", placeholder = "") { return `<div class="cfe-field"><label>${label}</label><input class="cfe-note-field" data-fieldname="${fieldname}" type="${type}" value="${this.escape(value ?? "")}" placeholder="${this.escape(placeholder)}"></div>`; }
    note_select_html(fieldname, label, value, options) { return `<div class="cfe-field"><label>${label}</label><select class="cfe-note-field" data-fieldname="${fieldname}">${this.select_options(options, value)}</select></div>`; }
    options_html(rows, selected) { return (rows || []).map((row) => `<option value="${this.escape(row.value || "")}" ${String(selected || "") === String(row.value || "") ? "selected" : ""}>${this.escape(row.label || row.value || "")}</option>`).join(""); }
    select_options(options, selected) { return (options || []).map((option) => `<option value="${this.escape(option)}" ${String(selected || "") === String(option || "") ? "selected" : ""}>${this.escape(option)}</option>`).join(""); }
    approval_pill_class(value) { if (value === "Aprobado") return "approved"; if (value === "Revision") return "review"; return "draft"; }
    checked(value) { return this.truthy(value) ? "checked" : ""; }
    truthy(value) { return this.asInt(value, 0) === 1; }
    asInt(value, fallback = 0) { const parsed = parseInt(value, 10); return Number.isNaN(parsed) ? fallback : parsed; }
    asFloat(value) { if (value === null || value === undefined || value === "") return 0; const parsed = parseFloat(String(value).replace(/,/g, "").trim()); return Number.isNaN(parsed) ? 0 : parsed; }
    escape(value) { return frappe.utils.escape_html(String(value ?? "")); }
}
