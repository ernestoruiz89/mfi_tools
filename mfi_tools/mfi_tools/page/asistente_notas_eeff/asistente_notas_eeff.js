const ASISTENTE_NOTAS_SHORTCUT_NS = ".mfiToolsAsistenteNotasShortcuts";

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
    editor.bind_keyboard_shortcuts();
    editor.apply_route_options();
    const hasRouteOptions = !!Object.keys(editor.state.route_options || {}).length;
    if (hasRouteOptions || !editor.bootstrapped) {
        editor.load_bootstrap({}, true);
    }
};

frappe.pages["asistente-notas-eeff"].on_page_hide = function () {
    $(document).off(`keydown${ASISTENTE_NOTAS_SHORTCUT_NS}`);
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
            note_search: "",
            is_dirty: false,
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
        this.bind_keyboard_shortcuts();
        this.page.set_primary_action(__("Guardar Nota"), () => this.save_current_note(), "save");
        this.page.set_secondary_action(__("Nueva Nota"), () => this.open_create_note_dialog());
        this.page.add_inner_button(__("Ejecutar Mapeo"), () => this.run_package_mapping());
        this.page.add_inner_button(__("Imprimir Nota"), () => this.print_current_note());
        this.page.add_menu_item(__("Abrir Paquete"), () => this.open_package_form());
        this.page.add_menu_item(__("Abrir Nota en Formulario"), () => this.open_current_note_form());
        this.page.add_menu_item(__("Eliminar Nota Actual"), () => this.delete_current_note());
        this.render_all();
    }

    bind_keyboard_shortcuts() {
        $(document).off(`keydown${ASISTENTE_NOTAS_SHORTCUT_NS}`);
        $(document).on(`keydown${ASISTENTE_NOTAS_SHORTCUT_NS}`, (event) => {
            const route = frappe.get_route ? frappe.get_route() : [];
            if (!route || route[0] !== "asistente-notas-eeff") return;
            if ($(".modal:visible").length) return;

            const key = String(event.key || "").toLowerCase();
            const code = String(event.code || "");

            if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && (key === "s" || code === "KeyS")) {
                event.preventDefault();
                event.stopPropagation();
                this.save_current_note();
                return;
            }

            if (event.ctrlKey && event.altKey && !event.shiftKey && (key === "m" || code === "KeyM")) {
                event.preventDefault();
                event.stopPropagation();
                this.run_package_mapping();
            }
        });
    }

    apply_route_options() {
        this.state.route_options = frappe.route_options || {};
        frappe.route_options = null;
    }

    mark_dirty(dirty = true) {
        this.state.is_dirty = !!dirty;
        const $badge = this.wrapper.find('[data-role="dirty-indicator"]');
        if ($badge.length) {
            if (this.state.is_dirty) {
                $badge.text(__("Cambios sin guardar")).removeClass("saved").addClass("dirty").show();
            } else {
                $badge.text(__("Guardado")).removeClass("dirty").addClass("saved").show();
            }
        }
    }

    setup_styles() {
        if (document.getElementById("cf-note-editor-style")) return;
        const style = document.createElement("style");
        style.id = "cf-note-editor-style";
        style.textContent = `
            .cfe-shell{display:grid;grid-template-columns:340px minmax(0,1fr);gap:16px;padding:18px;border:1px solid #d8e2ea;border-radius:22px;background:linear-gradient(160deg,#f4f9f8 0%,#eef7ff 52%,#fffaf1 100%)}
            .cfe-sidebar,.cfe-card{background:#fff;border:1px solid #d8e2ea;border-radius:18px;box-shadow:0 12px 28px rgba(15,23,42,.06)}
            .cfe-sidebar{overflow:hidden;display:flex;flex-direction:column}.cfe-main{display:flex;flex-direction:column;gap:14px;min-width:0}
            .cfe-card-head,.cfe-sidebar-head{padding:14px 16px;border-bottom:1px solid #eef2f7}
            .cfe-card-head h3,.cfe-sidebar-head h3{margin:0;font-size:15px;font-weight:800;color:#0f172a}
            .cfe-card-head p,.cfe-sidebar-head p{margin:6px 0 0;color:#64748b;font-size:12px}
            .cfe-filters,.cfe-summary{padding:14px 16px;border-bottom:1px solid #eef2f7}.cfe-grid{display:grid;gap:12px}
            .cfe-grid.filters,.cfe-grid.note-meta,.cfe-grid.section-meta,.cfe-grid.note-content{grid-template-columns:repeat(2,minmax(0,1fr))}
            .cfe-field{display:flex;flex-direction:column;gap:6px}.cfe-field label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:800}
            .cfe-field input,.cfe-field select,.cfe-field textarea{width:100%;border:1px solid #cbd5e1;border-radius:10px;padding:8px 10px;font-size:13px;background:#fff}
            .cfe-field textarea{min-height:110px;resize:vertical}.cfe-field.span-2{grid-column:span 2}
            .cfe-actions,.cfe-toolbar,.cfe-section-tabs{display:flex;gap:8px;flex-wrap:wrap}.cfe-actions{margin-top:12px}
            .cfe-btn{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:999px;padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer;transition:all .15s ease}
            .cfe-btn:hover{background:#f1f5f9}
            .cfe-btn.primary{background:#0f766e;border-color:#0f766e;color:#fff}.cfe-btn.primary:hover{background:#115e59}
            .cfe-btn.secondary{background:#14532d;border-color:#14532d;color:#fff}.cfe-btn.secondary:hover{background:#166534}
            .cfe-btn.danger{background:#fff1f2;border-color:#fecdd3;color:#be123c}.cfe-btn.danger:hover{background:#ffe4e6}
            .cfe-btn.xs{padding:3px 7px;font-size:11px;border-radius:6px}
            .cfe-search-box{padding:10px 16px;border-bottom:1px solid #eef2f7;background:#f8fafc}
            .cfe-search-box input{width:100%;border:1px solid #cbd5e1;border-radius:999px;padding:7px 12px;font-size:12px;background:#fff}
            .cfe-note-list{max-height:calc(100vh - 340px);overflow:auto}.cfe-note-item{padding:12px 16px;border-top:1px solid #eef2f7;cursor:pointer;transition:background .12s ease}.cfe-note-item:first-child{border-top:0}.cfe-note-item:hover{background:#f8fafc}.cfe-note-item.active{background:#dcfce7;border-left:4px solid #15803d}
            .cfe-note-title{display:flex;align-items:center;justify-content:space-between;gap:8px}.cfe-note-title strong{font-size:13px;color:#0f172a}.cfe-note-item span.cfe-note-sub{display:block;margin-top:5px;color:#475569;font-size:12px;font-weight:500}
            .cfe-note-badges{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:7px}
            .cfe-pill{display:inline-flex;align-items:center;justify-content:center;padding:3px 8px;border-radius:999px;font-size:10px;font-weight:800;text-transform:uppercase}.cfe-pill.simple{background:#dbeafe;color:#1d4ed8}.cfe-pill.complex{background:#ecfccb;color:#4d7c0f}.cfe-pill.draft{background:#e2e8f0;color:#334155}.cfe-pill.review{background:#ffedd5;color:#9a3412}.cfe-pill.approved{background:#dcfce7;color:#166534}.cfe-pill.dirty{background:#fef3c7;color:#b45309}.cfe-pill.saved{background:#dcfce7;color:#15803d}.cfe-pill.match{background:#dcfce7;color:#166534}.cfe-pill.diff{background:#ffedd5;color:#c2410c}.cfe-pill.origin-map{background:#e0e7ff;color:#3730a3}.cfe-pill.origin-fx{background:#fae8ff;color:#86198f}
            .cfe-summary-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:10px}
            .cfe-stat-box{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:6px 8px;text-align:center}
            .cfe-stat-box strong{display:block;font-size:14px;color:#0f172a;font-weight:800}
            .cfe-stat-box span{font-size:10px;color:#64748b;text-transform:uppercase;font-weight:700}
            .cfe-empty{padding:36px 20px;text-align:center;color:#64748b;border:1px dashed #cbd5e1;border-radius:16px;background:rgba(255,255,255,.78)}
            .cfe-table-wrap,.cfe-matrix-wrap{overflow:auto;padding:0 16px 16px}.cfe-table,.cfe-matrix-table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}
            .cfe-table th,.cfe-table td,.cfe-matrix-table th,.cfe-matrix-table td{padding:7px 6px;border-bottom:1px solid #eef2f7;vertical-align:middle}
            .cfe-table th,.cfe-matrix-table th{background:#f8fafc;color:#475569;font-size:10.5px;text-transform:uppercase;font-weight:800;white-space:nowrap}
            .cfe-table input[type="text"],.cfe-table input[type="number"],.cfe-table select,.cfe-table textarea{width:100%;border:1px solid #cbd5e1;border-radius:8px;padding:5px 7px;font-size:12px;background:#fff}
            .cfe-table input[type="checkbox"]{width:16px;height:16px;cursor:pointer}
            .cfe-table td.chk-cell,.cfe-table th.chk-col{text-align:center;width:42px}
            .cfe-table textarea{min-height:60px;resize:vertical}.cfe-link-delete{color:#be123c;cursor:pointer;font-weight:700}
            .cfe-row-actions{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
            .cfe-section-tabs{padding:0 16px 16px}.cfe-section-tab{border:1px solid #cbd5e1;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:700;cursor:pointer;background:#fff;color:#334155}.cfe-section-tab.active{background:#0f172a;border-color:#0f172a;color:#fff}
            .cfe-rowhead{min-width:220px;background:#fff}.cfe-code{display:block;color:#64748b;font-size:11px;margin-top:4px}
            .cfe-matrix-cell{display:flex;align-items:stretch;border:1px solid #cbd5e1;border-radius:8px;background:#fff;min-width:140px}.cfe-matrix-cell input.cfe-matrix-input{border:none!important;border-radius:0!important;flex:1;min-width:0!important;background:transparent!important;padding:5px 7px;font-size:12px;text-align:right}
            .cfe-matrix-format-dropdown{display:flex;align-items:stretch}.cfe-matrix-format-btn{border:none;border-right:1px solid #cbd5e1;background:#f8fafc;padding:0;color:#475569;font-size:11px;font-weight:700;width:28px;border-radius:8px 0 0 8px;cursor:pointer}.cfe-matrix-format-dropdown .dropdown-toggle::after{display:none!important}
            .cfe-matrix-fx-btn{border:none;border-left:1px solid #e2e8f0;background:#f8fafc;color:#64748b;font-size:10px;font-weight:800;padding:0 6px;border-radius:0 8px 8px 0;cursor:pointer}
            .cfe-matrix-fx-btn.active-fx{background:#fae8ff;color:#86198f}
            .cfe-matrix-fx-btn.active-map{background:#e0e7ff;color:#3730a3}
            .cfe-matrix-cell.computed{background:#f8fafc;border-style:dashed}
            .cfe-matrix-cell.cell-fx{border-color:#d8b4fe;background:#fdf4ff}
            .cfe-matrix-cell.cell-map{border-color:#a5b4fc;background:#eef2ff}
            .cfe-help{padding:0 16px 14px;color:#475569;font-size:12px}.cfe-title-cell{background:#fafafa}.cfe-fullscreen{position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;z-index:9999!important;margin:0!important;border-radius:0!important;display:flex;flex-direction:column}.cfe-fullscreen .cfe-table-wrap,.cfe-fullscreen .cfe-matrix-wrap{flex:1;max-height:none}
            .cfe-reconcile-banner{background:#f8fafc;border:1px solid #cbd5e1;border-radius:14px;padding:12px 16px;margin:0 16px 16px}
            .cfe-fig-computed{background:#f8fafc!important;font-weight:700;color:#0f172a}
            @media (max-width:1250px){.cfe-shell{grid-template-columns:1fr}.cfe-grid.filters,.cfe-grid.note-meta,.cfe-grid.section-meta,.cfe-grid.note-content{grid-template-columns:1fr}.cfe-field.span-2{grid-column:auto}}
        `;
        document.head.appendChild(style);
    }

    render_shell() {
        this.wrapper.html(`
            <div class="cfe-shell">
                <aside class="cfe-sidebar">
                    <div class="cfe-sidebar-head">
                        <h3>${__("Asistente de Notas EEFF")}</h3>
                        <p>${__("Gestiona narrativa, cifras, tablas complejas y cuadre con EEFF desde un solo lugar.")}</p>
                    </div>
                    <div class="cfe-filters" data-role="filters"></div>
                    <div class="cfe-summary" data-role="summary"></div>
                    <div class="cfe-search-box">
                        <input type="text" data-role="note-search" placeholder="${__("Buscar nota por número, título o tipo...")}" value="${this.escape(this.state.note_search || "")}">
                    </div>
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
        this.wrapper.on("input", "[data-role='note-search']", (event) => {
            this.state.note_search = event.currentTarget.value || "";
            this.render_note_list();
        });
        this.wrapper.on("click", "[data-action='refresh-bootstrap']", () => this.load_bootstrap({}, true));
        this.wrapper.on("click", "[data-action='open-package']", () => this.open_package_form());
        this.wrapper.on("click", "[data-action='open-note-list']", () => this.open_note_list());
        this.wrapper.on("click", "[data-action='run-mapping']", () => this.run_package_mapping());
        this.wrapper.on("click", "[data-action='print-note']", () => this.print_current_note());
        this.wrapper.on("click", "[data-action='delete-note']", () => this.delete_current_note());
        this.wrapper.on("click", "[data-action='save-note']", () => this.save_current_note());
        this.wrapper.on("click", "[data-action='open-estado']", (event) => {
            const estadoName = event.currentTarget.dataset.estadoName;
            if (estadoName) frappe.set_route("Form", "Estado Financiero EEFF", estadoName);
        });
        this.wrapper.on("click", ".cfe-note-item", (event) => {
            const noteName = event.currentTarget.dataset.noteName;
            if (!noteName || noteName === this.state.selected_note_name) return;
            if (this.state.is_dirty) {
                frappe.confirm(
                    __("Tienes cambios sin guardar en la nota actual. ¿Deseas cambiar de nota y descartarlos?"),
                    () => this.load_bootstrap({ note_name: noteName }, true)
                );
                return;
            }
            this.load_bootstrap({ note_name: noteName });
        });
        this.wrapper.on("change", ".cfe-note-field", (event) => this.update_note_field(event));
        this.wrapper.on("click", "[data-action='open-note-form']", () => this.open_current_note_form());
        this.wrapper.on("click", "[data-action='create-note-inline']", () => this.open_create_note_dialog());
        this.wrapper.on("click", "[data-action='add-figure']", () => this.add_figure());
        this.wrapper.on("click", ".cfe-delete-figure", (event) => this.delete_figure(this.asInt(event.currentTarget.dataset.index, -1)));
        this.wrapper.on("click", ".cfe-move-figure", (event) => {
            const idx = this.asInt(event.currentTarget.dataset.index, -1);
            const dir = this.asInt(event.currentTarget.dataset.dir, 0);
            this.move_figure(idx, dir);
        });
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
        this.wrapper.on("click", ".cfe-move-column", (event) => {
            const idx = this.asInt(event.currentTarget.dataset.index, -1);
            const dir = this.asInt(event.currentTarget.dataset.dir, 0);
            this.move_column(idx, dir);
        });
        this.wrapper.on("change", ".cfe-column-field", (event) => this.update_column_field(event));
        this.wrapper.on("click", "[data-action='add-row']", () => this.add_row());
        this.wrapper.on("click", ".cfe-delete-row", (event) => this.delete_row(this.asInt(event.currentTarget.dataset.index, -1)));
        this.wrapper.on("click", ".cfe-move-row", (event) => {
            const idx = this.asInt(event.currentTarget.dataset.index, -1);
            const dir = this.asInt(event.currentTarget.dataset.dir, 0);
            this.move_row(idx, dir);
        });
        this.wrapper.on("change", ".cfe-row-field", (event) => this.update_row_field(event));
        this.wrapper.on("change", ".cfe-matrix-input", (event) => this.update_matrix_value(event));
        this.wrapper.on("click", ".cfe-matrix-fx-btn", (event) => {
            event.preventDefault();
            this.open_cell_formula_dialog(event);
        });
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
            freeze_message: __("Cargando asistente de notas..."),
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
        this.state.is_dirty = false;
        this.ensure_note_shape();
        this.compute_figures_formulas();
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
                <div class="cfe-field"><label>${__("Entidad / Cliente")}</label><select data-filter="cliente"><option value=""></option>${this.options_html(this.state.clients || [], this.state.cliente)}</select></div>
                <div class="cfe-field"><label>${__("Anio")}</label><input data-filter="anio" type="number" min="1900" max="2200" value="${this.escape(this.state.anio || new Date().getFullYear())}"></div>
                <div class="cfe-field"><label>${__("Mes")}</label><select data-filter="mes"><option value=""></option>${this.options_html((this.state.meses || []).map((row) => ({ value: row, label: row })), this.state.mes)}</select></div>
                <div class="cfe-field"><label>${__("Paquete EEFF")}</label><select data-filter="package"><option value=""></option>${this.options_html(this.state.packages || [], this.state.package_name)}</select></div>
            </div>
            <div class="cfe-actions">
                <button class="cfe-btn" data-action="refresh-bootstrap">${__("Refrescar")}</button>
                <button class="cfe-btn" data-action="open-package">${__("Paquete")}</button>
                <button class="cfe-btn" data-action="open-note-list">${__("Lista Notas")}</button>
                <button class="cfe-btn secondary" data-action="run-mapping" title="Ctrl+Alt+M">${__("Mapeo")}</button>
            </div>
        `);
    }

    render_summary() {
        const summary = this.state.summary;
        if (!summary) {
            this.$summary.html(`<div class="cfe-empty" style="padding:18px 12px;">${__("Selecciona un paquete para cargar su contexto y sus notas.")}</div>`);
            return;
        }
        this.$summary.html(`
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                <div>
                    <strong style="font-size:13px;color:#0f172a;display:block;">${this.escape(summary.cliente_label || summary.cliente || "-")}</strong>
                    <span style="font-size:11px;color:#64748b;">${this.escape(summary.periodo_nombre || `${summary.mes || ""} ${summary.anio || ""}`)} &bull; ${this.escape(summary.package_name || "-")}</span>
                </div>
                <span class="cfe-pill ${this.approval_pill_class(summary.estado_preparacion)}">${this.escape(summary.estado_preparacion || "Borrador")}</span>
            </div>
            <div class="cfe-summary-stats">
                <div class="cfe-stat-box"><strong>${this.asInt(summary.total_notas, 0)}</strong><span>${__("Total")}</span></div>
                <div class="cfe-stat-box"><strong>${this.asInt(summary.total_notas_principales, 0)}</strong><span>${__("Princ.")}</span></div>
                <div class="cfe-stat-box"><strong>${this.asInt(summary.total_subnotas, 0)}</strong><span>${__("Subnotas")}</span></div>
                <div class="cfe-stat-box"><strong>${this.asInt(summary.total_notas_complejas, 0)}</strong><span>${__("Complejas")}</span></div>
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
        const query = String(this.state.note_search || "").trim().toLowerCase();
        const filteredNotes = (this.state.notes || []).filter((note) => {
            if (!query) return true;
            const haystack = [
                note.identificador_nota,
                note.numero_nota,
                note.sub_nota,
                note.titulo,
                note.estructura_nota,
                note.estado_aprobacion,
                note.name,
            ]
                .map((v) => String(v || "").toLowerCase())
                .join(" ");
            return haystack.includes(query);
        });

        if (!filteredNotes.length) {
            this.$noteList.html(`<div class="cfe-empty" style="padding:24px 12px;">${__("No hay notas que coincidan con la búsqueda.")}</div>`);
            return;
        }

        const currentName = this.get_doc()?.name || this.state.selected_note_name;
        this.$noteList.html(
            filteredNotes
                .map(
                    (note) => `
            <div class="cfe-note-item ${note.name === currentName ? "active" : ""}" data-note-name="${this.escape(note.name)}">
                <div class="cfe-note-title">
                    <strong>Nota ${this.escape(note.identificador_nota || note.numero_nota || note.name)}</strong>
                    <span class="cfe-pill ${note.estructura_nota === "Compleja" ? "complex" : "simple"}">${this.escape(note.estructura_nota || "Simple")}</span>
                </div>
                <span class="cfe-note-sub">${this.escape(note.titulo || __("Sin titulo"))}</span>
                <div class="cfe-note-badges">
                    <span class="cfe-pill ${this.approval_pill_class(note.estado_aprobacion)}">${this.escape(note.estado_aprobacion || "Borrador")}</span>
                    ${this.asInt(note.total_cifras, 0) > 0 ? `<span class="cfe-pill draft">${this.asInt(note.total_cifras, 0)} ${__("cifras")}</span>` : ""}
                    ${note.estructura_nota === "Compleja" ? `<span class="cfe-pill draft">${this.asInt(note.total_secciones_complejas, 0)} ${__("secc.")}</span>` : ""}
                </div>
            </div>
        `
                )
                .join("")
        );
    }

    render_editor() {
        const doc = this.get_doc();
        if (!this.state.package_name) {
            this.state.fullscreen_cards = {};
            this.$editor.html(`<div class="cfe-empty">${__("Selecciona un paquete y luego una nota para trabajar desde esta página.")}</div>`);
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
        this.compute_figures_formulas();
        const sections = this.get_sections();
        const currentSection = this.get_current_section();
        const noteIdentifier = doc.identificador_nota || this.build_note_identifier(doc.numero_nota, doc.sub_nota);
        const figuresEditor = this.render_figures_editor();
        const reconciliationHtml = this.render_eeff_reconciliation_card(doc);

        this.$editor.html(`
            <div class="cfe-card">
                <div class="cfe-card-head" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                    <div>
                        <div style="display:flex;align-items:center;gap:8px;">
                            <h3>${__("Nota")} ${this.escape(noteIdentifier || "-")}</h3>
                            <span data-role="dirty-indicator" class="cfe-pill ${this.state.is_dirty ? "dirty" : "saved"}">${this.state.is_dirty ? __("Cambios sin guardar") : __("Guardado")}</span>
                        </div>
                        <p>${this.escape(doc.titulo || __("Sin titulo"))} &bull; <small>${this.escape(doc.name || "")}</small></p>
                    </div>
                    <div class="cfe-toolbar">
                        <button class="cfe-btn primary" data-action="save-note" title="Ctrl+S">${__("Guardar Nota")}</button>
                        <button class="cfe-btn secondary" data-action="run-mapping" title="Ctrl+Alt+M">${__("Ejecutar Mapeo")}</button>
                        <button class="cfe-btn" data-action="print-note">${__("Imprimir Nota")}</button>
                        <button class="cfe-btn" data-action="open-note-form">${__("Abrir en Formulario")}</button>
                        <button class="cfe-btn" data-action="create-note-inline">${__("Nueva Nota")}</button>
                        <button class="cfe-btn danger" data-action="delete-note">${__("Eliminar")}</button>
                    </div>
                </div>
                ${reconciliationHtml}
                <div class="cfe-grid note-meta" style="padding:16px;">
                    ${this.note_field_html("numero_nota", __("Numero Nota"), doc.numero_nota || "", "number")}
                    ${this.note_field_html("sub_nota", __("Sub Nota"), doc.sub_nota || "", "text", __("Opcional: a, b, c..."))}
                    ${this.note_field_html("titulo", __("Titulo"), doc.titulo || "", "text", "", "span-2")}
                    ${this.note_select_html("estructura_nota", __("Estructura"), doc.estructura_nota || "Simple", ["Simple", "Compleja"])}
                    ${this.note_select_html("estado_aprobacion", __("Estado Aprobacion"), doc.estado_aprobacion || "Borrador", ["Borrador", "En Revision", "Aprobado"])}
                    ${this.note_select_html("orientacion", __("Orientacion de Pagina"), doc.orientacion || "Vertical", ["Vertical", "Horizontal"])}
                    ${this.note_field_html("tamano_letra_impresion", __("Tamano Letra Tabla (pt)"), doc.tamano_letra_impresion || 12, "number")}
                    ${this.note_field_html("ancho_tabla_impresion", __("Ancho de Tablas"), doc.ancho_tabla_impresion || "100%", "text", __("Ej: 100%, 85%, 720px"))}
                    ${this.note_select_html("alineacion_tabla_impresion", __("Ubicacion de Tablas"), doc.alineacion_tabla_impresion || "Centro", ["Izquierda", "Centro", "Derecha"])}
                    ${this.note_checkbox_html("centrar_valores_verticalmente", __("Centrar Valores Verticalmente"), doc.centrar_valores_verticalmente)}
                </div>
                <div class="cfe-grid note-content" style="padding:0 16px 16px;">
                    ${this.note_textarea_html("contenido_narrativo", __("Contenido Narrativo (soporta Jinja)"), doc.contenido_narrativo || "")}
                    ${this.note_textarea_html("observaciones", __("Observaciones Internas"), doc.observaciones || "")}
                </div>
            </div>
            ${figuresEditor}
            ${doc.estructura_nota === "Compleja" ? this.render_complex_editor(sections, currentSection) : ""}
        `);
        this.sync_body_scroll();
    }

    compute_note_totals(doc) {
        const rows = (doc && doc.cifras_nota) || [];
        const visibleRows = rows.filter((r) => !this.asBool(r.no_imprimir) && !this.asBool(r.es_linea_blanco) && !this.asBool(r.es_titulo) && String(r.formato_numero || "Moneda") !== "Texto");
        const totalRows = visibleRows.filter((r) => this.asBool(r.es_total));
        if (totalRows.length > 0) {
            const lastTotal = totalRows[totalRows.length - 1];
            return {
                source: `Cifra Total (${lastTotal.codigo_cifra || lastTotal.concepto || "TOTAL"})`,
                actual: this.asFloat(lastTotal.monto_actual, 0),
                comparativo: this.asFloat(lastTotal.monto_comparativo, 0),
                has_data: true,
            };
        }
        const detailRows = visibleRows.filter((r) => !this.asBool(r.es_subtotal) && !this.asBool(r.es_total));
        if (detailRows.length > 0) {
            return {
                source: __("Suma de cifras detalle ({0})", [detailRows.length]),
                actual: detailRows.reduce((acc, r) => acc + this.asFloat(r.monto_actual, 0), 0),
                comparativo: detailRows.reduce((acc, r) => acc + this.asFloat(r.monto_comparativo, 0), 0),
                has_data: true,
            };
        }
        return { source: "", actual: 0, comparativo: 0, has_data: false };
    }

    render_eeff_reconciliation_card(doc) {
        const refs = Array.isArray(doc.referenced_in_estados) ? doc.referenced_in_estados : [];
        if (!refs.length) {
            return `
                <div class="cfe-reconcile-banner" style="margin-top:12px;">
                    <span style="font-size:12px;color:#64748b;">
                        <strong>${__("Vínculo con EEFF:")}</strong> ${__("Ninguna línea de Estado Financiero EEFF en este paquete declara referencia a esta nota todavía.")}
                    </span>
                </div>
            `;
        }

        const noteTotals = this.compute_note_totals(doc);
        const rowsHtml = refs
            .map((ref) => {
                const actEEFF = this.asFloat(ref.monto_actual, 0);
                const compEEFF = this.asFloat(ref.monto_comparativo, 0);
                const diffAct = noteTotals.has_data ? actEEFF - noteTotals.actual : null;
                const diffComp = noteTotals.has_data ? compEEFF - noteTotals.comparativo : null;
                const matchAct = diffAct !== null && Math.abs(diffAct) < 0.01;
                const matchComp = diffComp !== null && Math.abs(diffComp) < 0.01;

                return `
                    <tr>
                        <td>
                            <button class="cfe-btn xs" data-action="open-estado" data-estado-name="${this.escape(ref.estado_name)}">${this.escape(ref.estado_titulo || ref.estado_name)}</button>
                        </td>
                        <td><strong>${this.escape(ref.codigo_linea || "-")}</strong> &mdash; ${this.escape(ref.descripcion || "-")}</td>
                        <td><span class="cfe-pill simple">${this.escape(ref.nota_declarada || "-")}</span></td>
                        <td style="text-align:right;font-weight:700;">${this.format_number(actEEFF, 2)}</td>
                        <td style="text-align:right;">
                            ${
                                diffAct === null
                                    ? `<span class="cfe-pill draft">${__("Sin cifras")}</span>`
                                    : matchAct
                                    ? `<span class="cfe-pill match">&#10003; ${__("Cuadra")}</span>`
                                    : `<span class="cfe-pill diff">${__("Dif:")} ${this.format_number(diffAct, 2)}</span>`
                            }
                        </td>
                        <td style="text-align:right;font-weight:700;">${this.format_number(compEEFF, 2)}</td>
                        <td style="text-align:right;">
                            ${
                                diffComp === null
                                    ? `<span class="cfe-pill draft">${__("Sin cifras")}</span>`
                                    : matchComp
                                    ? `<span class="cfe-pill match">&#10003; ${__("Cuadra")}</span>`
                                    : `<span class="cfe-pill diff">${__("Dif:")} ${this.format_number(diffComp, 2)}</span>`
                            }
                        </td>
                    </tr>
                `;
            })
            .join("");

        return `
            <div class="cfe-reconcile-banner" style="margin-top:12px;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
                    <strong style="font-size:12px;color:#0f172a;text-transform:uppercase;">${__("Líneas de EEFF que referencian esta Nota")} (${refs.length})</strong>
                    ${
                        noteTotals.has_data
                            ? `<span style="font-size:12px;color:#334155;"><strong>${this.escape(noteTotals.source)}:</strong> Actual = <strong>${this.format_number(noteTotals.actual, 2)}</strong> | Comparativo = <strong>${this.format_number(noteTotals.comparativo, 2)}</strong></span>`
                            : `<span style="font-size:11px;color:#64748b;">${__("Agrega cifras en la nota para comparar automáticamente contra el saldo declarado en EEFF.")}</span>`
                    }
                </div>
                <div style="overflow:auto;">
                    <table class="cfe-table" style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;">
                        <thead>
                            <tr>
                                <th>${__("Estado Financiero")}</th>
                                <th>${__("Línea EEFF")}</th>
                                <th>${__("Nota Declarada")}</th>
                                <th style="text-align:right;">${__("Actual EEFF")}</th>
                                <th style="text-align:right;">${__("Cuadre Actual")}</th>
                                <th style="text-align:right;">${__("Comparativo EEFF")}</th>
                                <th style="text-align:right;">${__("Cuadre Comp.")}</th>
                            </tr>
                        </thead>
                        <tbody>${rowsHtml}</tbody>
                    </table>
                </div>
            </div>
        `;
    }

    compute_figures_formulas() {
        const doc = this.get_doc();
        if (!doc || !Array.isArray(doc.cifras_nota)) return;
        const rows = doc.cifras_nota;
        const rowMap = new Map();
        rows.forEach((r) => {
            const code = this.clean_code(r.codigo_cifra);
            if (code) rowMap.set(code, r);
        });

        const hasBackendFunc = (expr) => /\b(BAL|BAL_ACT|BAL_COMP|BAL_BASE_ACT|BAL_BASE_COMP|EST|EST_ACT|EST_COMP|YTD|YTD_ANT|ANUAL_ANT|CIERRE_ANT|MES_ANIO_ANT|VAL_ACT|VAL_COMP|SI|ABS|MAX|MIN|REDONDEAR|VAR)\b/i.test(String(expr || ""));

        const cache = new Map();
        const evalField = (code, fieldname, stack = new Set()) => {
            const key = `${code}::${fieldname}`;
            if (cache.has(key)) return cache.get(key);
            const row = rowMap.get(code);
            if (!row) return 0;
            if (this.asBool(row.es_linea_blanco) || this.asBool(row.es_titulo) || String(row.formato_numero || "Moneda") === "Texto") {
                return 0;
            }
            if (stack.has(key)) return this.asFloat(row[fieldname], 0);

            const origin = String(row.origen_dato || "Manual").trim();
            const expr = String(row.formula_cifras || "").trim();
            if (origin === "Formula" && expr && !hasBackendFunc(expr)) {
                const nextStack = new Set(stack);
                nextStack.add(key);
                let total = 0;
                this.parse_formula(expr).forEach((item) => {
                    total += item.sign * evalField(item.code, fieldname, nextStack);
                });
                row[fieldname] = total;
                cache.set(key, total);
                return total;
            }

            const val = this.asFloat(row[fieldname], 0);
            cache.set(key, val);
            return val;
        };

        rows.forEach((row) => {
            const code = this.clean_code(row.codigo_cifra);
            if (!code) return;
            const origin = String(row.origen_dato || "Manual").trim();
            const expr = String(row.formula_cifras || "").trim();
            if (origin === "Formula" && expr && !hasBackendFunc(expr)) {
                evalField(code, "monto_actual");
                evalField(code, "monto_comparativo");
            }
        });
    }

    render_figures_editor() {
        const doc = this.get_doc();
        const rows = doc?.cifras_nota || [];
        const isFullscreen = !!this.state.fullscreen_cards["figures"];
        const totals = this.compute_note_totals(doc);

        return `
            <div class="cfe-card ${isFullscreen ? "cfe-fullscreen" : ""}" data-card-id="figures">
                <div class="cfe-card-head" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                    <div>
                        <h3>${__("Cifras de la Nota")} (${rows.length})</h3>
                        <p>${__("Edita importes actuales y comparativos, formato, origen (Manual / Mapeo / Fórmula) y presentación.")}</p>
                    </div>
                    <div class="cfe-toolbar">
                        <button class="cfe-btn primary" data-action="add-figure">${__("+ Agregar Cifra")}</button>
                        <button class="cfe-btn cfe-toggle-fullscreen" data-target="figures">${isFullscreen ? __("Salir de Pantalla Completa") : __("Pantalla Completa")}</button>
                    </div>
                </div>
                <div class="cfe-table-wrap">
                    <table class="cfe-table">
                        <thead>
                            <tr>
                                <th style="min-width:110px;">${__("Codigo")}</th>
                                <th style="min-width:210px;">${__("Concepto")}</th>
                                <th style="width:65px;">${__("Nivel")}</th>
                                <th style="min-width:110px;">${__("Formato")}</th>
                                <th class="chk-col" title="${__("Redondear a Entero")}">${__("Ent.")}</th>
                                <th style="min-width:130px;">${__("Actual")}</th>
                                <th style="min-width:130px;">${__("Comparativo")}</th>
                                <th style="min-width:105px;">${__("Origen")}</th>
                                <th style="min-width:150px;">${__("Formula")}</th>
                                <th class="chk-col" title="${__("Concepto en Negrita")}">${__("Neg.")}</th>
                                <th class="chk-col" title="${__("Subrayado")}">${__("Subr.")}</th>
                                <th class="chk-col" title="${__("Es Título")}">${__("Tit.")}</th>
                                <th class="chk-col" title="${__("Es Línea en Blanco")}">${__("Blanco")}</th>
                                <th class="chk-col" title="${__("Es Total")}">${__("Total")}</th>
                                <th class="chk-col" title="${__("Es Subtotal")}">${__("Subt.")}</th>
                                <th class="chk-col" title="${__("No Imprimir")}">${__("No Imp.")}</th>
                                <th style="width:86px;text-align:center;">${__("Acciones")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${
                                rows.length
                                    ? rows
                                          .map((row, index) => {
                                              const isTitle = this.asBool(row.es_titulo);
                                              const isBlank = this.asBool(row.es_linea_blanco);
                                              const fmt = row.formato_numero || "Moneda";
                                              const isText = !isTitle && !isBlank && fmt === "Texto";
                                              const origin = row.origen_dato || "Manual";
                                              const isComputed = origin === "Formula" || origin === "Mapeo";

                                              let actualInputHtml = "";
                                              let compInputHtml = "";
                                              if (isTitle || isBlank) {
                                                  actualInputHtml = `<input type="text" value="" disabled placeholder="-">`;
                                                  compInputHtml = `<input type="text" value="" disabled placeholder="-">`;
                                              } else if (isText) {
                                                  actualInputHtml = `<input class="cfe-figure-field" data-index="${index}" data-field="valor_texto_actual" type="text" placeholder="${__("Texto actual")}" value="${this.escape(row.valor_texto_actual ?? "")}">`;
                                                  compInputHtml = `<input class="cfe-figure-field" data-index="${index}" data-field="valor_texto_comparativo" type="text" placeholder="${__("Texto comparativo")}" value="${this.escape(row.valor_texto_comparativo ?? "")}">`;
                                              } else {
                                                  actualInputHtml = `<input class="cfe-figure-field ${isComputed ? "cfe-fig-computed" : ""}" style="text-align:right;" data-index="${index}" data-field="monto_actual" type="number" step="0.01" value="${this.escape(row.monto_actual ?? "")}" ${origin === "Formula" ? 'title="Calculado por fórmula"' : ""}>`;
                                                  compInputHtml = `<input class="cfe-figure-field ${isComputed ? "cfe-fig-computed" : ""}" style="text-align:right;" data-index="${index}" data-field="monto_comparativo" type="number" step="0.01" value="${this.escape(row.monto_comparativo ?? "")}" ${origin === "Formula" ? 'title="Calculado por fórmula"' : ""}>`;
                                              }

                                              return `
                                    <tr style="${this.asBool(row.es_total) ? "background:#f0fdf4;font-weight:700;" : this.asBool(row.es_subtotal) ? "background:#f8fafc;" : ""}">
                                        <td><input class="cfe-figure-field" data-index="${index}" data-field="codigo_cifra" type="text" value="${this.escape(row.codigo_cifra || "")}"></td>
                                        <td><input class="cfe-figure-field" data-index="${index}" data-field="concepto" type="text" value="${this.escape(row.concepto || "")}" ${isBlank ? "disabled" : ""}></td>
                                        <td><input class="cfe-figure-field" data-index="${index}" data-field="nivel" type="number" min="1" value="${this.escape(row.nivel || 1)}" ${isBlank ? "disabled" : ""}></td>
                                        <td><select class="cfe-figure-field" data-index="${index}" data-field="formato_numero" ${isTitle || isBlank ? "disabled" : ""}>${this.options_html(["Moneda", "Numero", "Porcentaje", "Texto"].map((v) => ({ value: v, label: v })), fmt)}</select></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="redondear_entero" type="checkbox" ${this.asBool(row.redondear_entero) ? "checked" : ""} ${isTitle || isBlank || isText ? "disabled" : ""}></td>
                                        <td>${actualInputHtml}</td>
                                        <td>${compInputHtml}</td>
                                        <td>
                                            <select class="cfe-figure-field" data-index="${index}" data-field="origen_dato" ${isTitle || isBlank || isText ? "disabled" : ""}>
                                                ${this.options_html(["Manual", "Mapeo", "Formula"].map((v) => ({ value: v, label: v })), origin)}
                                            </select>
                                        </td>
                                        <td><input class="cfe-figure-field" data-index="${index}" data-field="formula_cifras" type="text" placeholder="COD_1, -COD_2 o BAL(...)" value="${this.escape(row.formula_cifras || "")}" ${isTitle || isBlank || isText ? "disabled" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="negrita" type="checkbox" ${this.asBool(row.negrita) ? "checked" : ""} ${isBlank ? "disabled" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="subrayado" type="checkbox" ${this.asBool(row.subrayado) ? "checked" : ""} ${isBlank ? "disabled" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="es_titulo" type="checkbox" ${isTitle ? "checked" : ""} ${isBlank ? "disabled" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="es_linea_blanco" type="checkbox" ${isBlank ? "checked" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="es_total" type="checkbox" ${this.asBool(row.es_total) ? "checked" : ""} ${isTitle || isBlank ? "disabled" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="es_subtotal" type="checkbox" ${this.asBool(row.es_subtotal) ? "checked" : ""} ${isTitle || isBlank ? "disabled" : ""}></td>
                                        <td class="chk-cell"><input class="cfe-figure-field" data-index="${index}" data-field="no_imprimir" type="checkbox" ${this.asBool(row.no_imprimir) ? "checked" : ""}></td>
                                        <td style="text-align:center;">
                                            <div class="cfe-row-actions">
                                                <button class="cfe-btn xs cfe-move-figure" data-index="${index}" data-dir="-1" title="${__("Subir")}" ${index === 0 ? "disabled" : ""}>&uarr;</button>
                                                <button class="cfe-btn xs cfe-move-figure" data-index="${index}" data-dir="1" title="${__("Bajar")}" ${index === rows.length - 1 ? "disabled" : ""}>&darr;</button>
                                                <button class="cfe-btn xs danger cfe-delete-figure" data-index="${index}" title="${__("Eliminar")}">&times;</button>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                                          })
                                          .join("")
                                    : `<tr><td colspan="17"><div class="cfe-empty" style="padding:18px;">${__("No hay cifras registradas en esta nota.")}</div></td></tr>`
                            }
                        </tbody>
                        ${
                            totals.has_data
                                ? `
                        <tfoot>
                            <tr style="background:#f8fafc;font-weight:800;border-top:2px solid #cbd5e1;">
                                <td colspan="5" style="text-align:right;">${this.escape(totals.source)}:</td>
                                <td style="text-align:right;color:#0f172a;">${this.format_number(totals.actual, 2)}</td>
                                <td style="text-align:right;color:#0f172a;">${this.format_number(totals.comparativo, 2)}</td>
                                <td colspan="10"></td>
                            </tr>
                        </tfoot>`
                                : ""
                        }
                    </table>
                </div>
            </div>
        `;
    }

    render_complex_editor(sections, currentSection) {
        return `
            <div class="cfe-card">
                <div class="cfe-card-head" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                    <div><h3>${__("Secciones Complejas")} (${sections.length})</h3><p>${__("Administra narrativa, tablas multimoneda/multinivel y fórmulas por fila, columna o celda.")}</p></div>
                    <div class="cfe-toolbar">
                        <button class="cfe-btn primary" data-action="add-section">${__("+ Nueva Seccion")}</button>
                        <button class="cfe-btn" data-action="duplicate-section" ${currentSection ? "" : "disabled"}>${__("Duplicar Seccion")}</button>
                        <button class="cfe-btn danger" data-action="delete-section" ${currentSection ? "" : "disabled"}>${__("Eliminar Seccion")}</button>
                    </div>
                </div>
                <div class="cfe-section-tabs">
                    ${
                        sections.length
                            ? sections
                                  .map(
                                      (section) => `
                        <button class="cfe-section-tab ${section._client_id === currentSection?._client_id ? "active" : ""}" data-section-id="${this.escape(section._client_id)}">
                            ${this.escape(section.codigo_seccion || "SEC")} &bull; ${this.escape(section.titulo_seccion || section.tipo_seccion || __("Seccion"))}
                        </button>
                    `
                                  )
                                  .join("")
                            : `<div class="cfe-empty" style="width:100%;">${__("La nota compleja aún no tiene secciones.")}</div>`
                    }
                </div>
                ${currentSection ? this.render_section_editor(currentSection) : ""}
            </div>
        `;
    }

    render_section_editor(section) {
        const showNarrative = ["Narrativa", "Mixta"].includes(section.tipo_seccion || "Tabla");
        const showTable = ["Tabla", "Mixta"].includes(section.tipo_seccion || "Tabla");
        return `
            <div class="cfe-grid section-meta" style="padding:0 16px 16px;">
                ${this.section_field_html("codigo_seccion", __("Codigo Seccion"), section.codigo_seccion || "", "text")}
                ${this.section_select_html("tipo_seccion", __("Tipo Seccion"), section.tipo_seccion || "Tabla", ["Narrativa", "Tabla", "Mixta"])}
                ${this.section_field_html("titulo_seccion", __("Titulo Seccion"), section.titulo_seccion || "", "text")}
                ${this.section_field_html("orden", __("Orden"), section.orden || 1, "number")}
                ${this.section_checkbox_html("mostrar_titulo", __("Mostrar Titulo al Imprimir"), section.mostrar_titulo)}
                ${this.section_textarea_html("observaciones", __("Observaciones de Seccion"), section.observaciones || "", "span-2")}
                ${showNarrative ? this.section_textarea_html("contenido_narrativo", __("Narrativa de Seccion"), section.contenido_narrativo || "", "span-2") : ""}
            </div>
            ${showTable ? `${this.render_columns_editor(section)}${this.render_rows_editor(section)}${this.render_matrix_editor(section)}` : ""}
        `;
    }

    render_columns_editor(section) {
        const rows = section.columnas_tabulares || [];
        const cardId = `cols_${section._client_id}`;
        const isFullscreen = !!this.state.fullscreen_cards[cardId];
        return `
            <div class="cfe-card ${isFullscreen ? "cfe-fullscreen" : ""}" data-card-id="${this.escape(cardId)}" style="margin:0 16px 16px;">
                <div class="cfe-card-head" style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                    <div><h3>${__("Columnas Tabulares")} (${rows.length})</h3><p>${__("Define códigos, grupos de encabezado, tipo de dato y fórmulas entre columnas.")}</p></div>
                    <div class="cfe-toolbar">
                        <button class="cfe-btn primary" data-action="add-column">${__("+ Agregar Columna")}</button>
                        <button class="cfe-btn cfe-toggle-fullscreen" data-target="${this.escape(cardId)}">${isFullscreen ? __("Salir de Pantalla Completa") : __("Pantalla Completa")}</button>
                    </div>
                </div>
                <div class="cfe-table-wrap">
                    <table class="cfe-table">
                        <thead>
                            <tr>
                                <th style="min-width:95px;">${__("Tabla")}</th>
                                <th style="min-width:105px;">${__("Codigo")}</th>
                                <th style="min-width:180px;">${__("Etiqueta")}</th>
                                <th style="min-width:140px;">${__("Grupo")}</th>
                                <th style="min-width:110px;">${__("Tipo")}</th>
                                <th style="min-width:100px;">${__("Alineacion")}</th>
                                <th class="chk-col" title="${__("Redondear a Entero")}">${__("Entero")}</th>
                                <th class="chk-col" title="${__("Es Columna de Total")}">${__("Es Total")}</th>
                                <th style="min-width:160px;">${__("Formula Columnas")}</th>
                                <th style="width:86px;text-align:center;">${__("Acciones")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${
                                rows.length
                                    ? rows
                                          .map(
                                              (row, index) => `
                                <tr>
                                    <td><input class="cfe-column-field" data-index="${index}" data-field="codigo_tabla" type="text" value="${this.escape(row.codigo_tabla || "TABLA_1")}"></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-field="codigo_columna" type="text" value="${this.escape(row.codigo_columna || "")}"></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-field="etiqueta" type="text" value="${this.escape(row.etiqueta || "")}"></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-field="grupo_columna" type="text" value="${this.escape(row.grupo_columna || "")}"></td>
                                    <td><select class="cfe-column-field" data-index="${index}" data-field="tipo_dato">${this.options_html(["Numero", "Moneda", "Porcentaje", "Texto"].map((v) => ({ value: v, label: v })), row.tipo_dato || "Numero")}</select></td>
                                    <td><select class="cfe-column-field" data-index="${index}" data-field="alineacion">${this.options_html(["Left", "Center", "Right"].map((v) => ({ value: v, label: v })), row.alineacion || "Right")}</select></td>
                                    <td class="chk-cell"><input class="cfe-column-field" data-index="${index}" data-field="redondear_entero" type="checkbox" ${this.asBool(row.redondear_entero) ? "checked" : ""}></td>
                                    <td class="chk-cell"><input class="cfe-column-field" data-index="${index}" data-field="es_total" type="checkbox" ${this.asBool(row.es_total) ? "checked" : ""}></td>
                                    <td><input class="cfe-column-field" data-index="${index}" data-field="formula_columnas" type="text" placeholder="COL_1, -COL_2" value="${this.escape(row.formula_columnas || "")}"></td>
                                    <td style="text-align:center;">
                                        <div class="cfe-row-actions">
                                            <button class="cfe-btn xs cfe-move-column" data-index="${index}" data-dir="-1" title="${__("Subir")}" ${index === 0 ? "disabled" : ""}>&uarr;</button>
                                            <button class="cfe-btn xs cfe-move-column" data-index="${index}" data-dir="1" title="${__("Bajar")}" ${index === rows.length - 1 ? "disabled" : ""}>&darr;</button>
                                            <button class="cfe-btn xs danger cfe-delete-column" data-index="${index}" title="${__("Eliminar")}">&times;</button>
                                        </div>
                                    </td>
                                </tr>
                            `
                                          )
                                          .join("")
                                    : `<tr><td colspan="10"><div class="cfe-empty" style="padding:18px;">${__("No hay columnas definidas.")}</div></td></tr>`
                            }
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    render_rows_editor(section) {
        const rows = section.filas_tabulares || [];
        const cardId = `rows_${section._client_id}`;
        const isFullscreen = !!this.state.fullscreen_cards[cardId];
        return `
            <div class="cfe-card ${isFullscreen ? "cfe-fullscreen" : ""}" data-card-id="${this.escape(cardId)}" style="margin:0 16px 16px;">
                <div class="cfe-card-head" style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                    <div><h3>${__("Filas Tabulares")} (${rows.length})</h3><p>${__("Define las filas por tabla, su jerarquía, tipo (Detalle, Subtotal, Total, Título) y fórmula.")}</p></div>
                    <div class="cfe-toolbar">
                        <button class="cfe-btn primary" data-action="add-row">${__("+ Agregar Fila")}</button>
                        <button class="cfe-btn cfe-toggle-fullscreen" data-target="${this.escape(cardId)}">${isFullscreen ? __("Salir de Pantalla Completa") : __("Pantalla Completa")}</button>
                    </div>
                </div>
                <div class="cfe-table-wrap">
                    <table class="cfe-table">
                        <thead>
                            <tr>
                                <th style="min-width:95px;">${__("Tabla")}</th>
                                <th style="min-width:105px;">${__("Codigo")}</th>
                                <th style="min-width:220px;">${__("Descripcion")}</th>
                                <th style="width:68px;">${__("Nivel")}</th>
                                <th style="min-width:115px;">${__("Tipo")}</th>
                                <th style="min-width:170px;">${__("Formula Filas")}</th>
                                <th class="chk-col">${__("Negrita")}</th>
                                <th class="chk-col">${__("Subrayado")}</th>
                                <th style="width:86px;text-align:center;">${__("Acciones")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${
                                rows.length
                                    ? rows
                                          .map(
                                              (row, index) => `
                                <tr>
                                    <td><input class="cfe-row-field" data-index="${index}" data-field="codigo_tabla" type="text" value="${this.escape(row.codigo_tabla || "TABLA_1")}"></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-field="codigo_fila" type="text" value="${this.escape(row.codigo_fila || "")}"></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-field="descripcion" type="text" value="${this.escape(row.descripcion || "")}"></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-field="nivel" type="number" min="1" value="${this.escape(row.nivel || 1)}"></td>
                                    <td><select class="cfe-row-field" data-index="${index}" data-field="tipo_fila">${this.options_html(["Detalle", "Subtotal", "Total", "Titulo"].map((v) => ({ value: v, label: v })), row.tipo_fila || "Detalle")}</select></td>
                                    <td><input class="cfe-row-field" data-index="${index}" data-field="formula_filas" type="text" placeholder="FILA_1, -FILA_2" value="${this.escape(row.formula_filas || "")}"></td>
                                    <td class="chk-cell"><input class="cfe-row-field" data-index="${index}" data-field="negrita" type="checkbox" ${this.asBool(row.negrita) ? "checked" : ""}></td>
                                    <td class="chk-cell"><input class="cfe-row-field" data-index="${index}" data-field="subrayado" type="checkbox" ${this.asBool(row.subrayado) ? "checked" : ""}></td>
                                    <td style="text-align:center;">
                                        <div class="cfe-row-actions">
                                            <button class="cfe-btn xs cfe-move-row" data-index="${index}" data-dir="-1" title="${__("Subir")}" ${index === 0 ? "disabled" : ""}>&uarr;</button>
                                            <button class="cfe-btn xs cfe-move-row" data-index="${index}" data-dir="1" title="${__("Bajar")}" ${index === rows.length - 1 ? "disabled" : ""}>&darr;</button>
                                            <button class="cfe-btn xs danger cfe-delete-row" data-index="${index}" title="${__("Eliminar")}">&times;</button>
                                        </div>
                                    </td>
                                </tr>
                            `
                                          )
                                          .join("")
                                    : `<tr><td colspan="9"><div class="cfe-empty" style="padding:18px;">${__("No hay filas definidas.")}</div></td></tr>`
                            }
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    render_matrix_editor(section) {
        const matrices = this.compute_matrix(section);
        const cardId = `matrix_${section._client_id}`;
        const isFullscreen = !!this.state.fullscreen_cards[cardId];
        return `
            <div class="cfe-card ${isFullscreen ? "cfe-fullscreen" : ""}" data-card-id="${this.escape(cardId)}" data-role="matrix-card" style="margin:0 16px 16px;">
                <div class="cfe-card-head" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                    <div><h3>${__("Matriz Visual de Celdas")}</h3><p>${__("Edita valores directamente, elige formato ($, #, %, T) o pulsa fx para configurar fórmula o mapeo de celda.")}</p></div>
                    <div class="cfe-toolbar">
                        <button class="cfe-btn" data-action="refresh-matrix">${__("Recalcular Matriz")}</button>
                        <button class="cfe-btn" data-action="download-csv">${__("Descargar CSV")}</button>
                        <button class="cfe-btn secondary" data-action="upload-csv">${__("Cargar CSV")}</button>
                        <button class="cfe-btn cfe-toggle-fullscreen" data-target="${this.escape(cardId)}">${isFullscreen ? __("Salir de Pantalla Completa") : __("Pantalla Completa")}</button>
                        <input class="cfe-csv-input" type="file" accept=".csv,text/csv" style="display:none;">
                    </div>
                </div>
                <div class="cfe-help">${__("Tip: Puedes escribir directamente =BAL(\"101*\") en una celda o hacer clic en fx para definir una Fórmula de Celda.")}</div>
                ${
                    matrices.length
                        ? matrices
                              .map(
                                  (matrix) => `
                    <div class="cfe-card-head" style="border-top:1px solid #eef2f7;"><h3>${this.escape(matrix.codigo_tabla)}</h3><p>${matrix.filas.length} ${__("filas")} &bull; ${matrix.columnas.length} ${__("columnas")}</p></div>
                    <div class="cfe-matrix-wrap">
                        <table class="cfe-matrix-table">
                            <thead>
                                ${
                                    matrix.tiene_grupos
                                        ? `
                                    <tr>
                                        <th class="cfe-rowhead" rowspan="2">${__("Concepto / Fila")}</th>
                                        ${matrix.grupos_encabezado
                                            .map((group) =>
                                                group.es_grupo
                                                    ? `<th colspan="${group.colspan}" style="text-align:center;">${this.escape(group.grupo)}</th>`
                                                    : `<th rowspan="2">${this.escape(group.columna.etiqueta || group.columna.codigo_columna)}<span class="cfe-code">${this.escape(group.columna.codigo_columna)}</span></th>`
                                            )
                                            .join("")}
                                    </tr>
                                    <tr>
                                        ${matrix.grupos_encabezado
                                            .filter((group) => group.es_grupo)
                                            .flatMap((group) => group.columnas)
                                            .map((col) => `<th>${this.escape(col.etiqueta || col.codigo_columna)}<span class="cfe-code">${this.escape(col.codigo_columna)}</span></th>`)
                                            .join("")}
                                    </tr>
                                `
                                        : `
                                    <tr>
                                        <th class="cfe-rowhead">${__("Concepto / Fila")}</th>
                                        ${matrix.columnas.map((col) => `<th>${this.escape(col.etiqueta || col.codigo_columna)}<span class="cfe-code">${this.escape(col.codigo_columna)}</span></th>`).join("")}
                                    </tr>
                                `
                                }
                            </thead>
                            <tbody>
                                ${matrix.filas
                                    .map(
                                        (row) => `
                                    <tr style="${row.tipo_fila === "Total" ? "background:#f0fdf4;" : row.tipo_fila === "Subtotal" ? "background:#f8fafc;" : ""}">
                                        <td class="cfe-rowhead">
                                            <div style="padding-left:${Math.max((this.asInt(row.nivel, 1) - 1) * 14, 0)}px;${row.negrita || row.tipo_fila === "Total" ? "font-weight:700;" : ""}${row.subrayado ? "text-decoration:underline;" : ""}">
                                                ${this.escape(row.descripcion || row.codigo_fila)}
                                                <span class="cfe-code">${this.escape(row.codigo_fila)} &bull; ${this.escape(row.tipo_fila)}</span>
                                            </div>
                                        </td>
                                        ${row.celdas
                                            .map((cell) => {
                                                if (cell.is_title) {
                                                    return `<td class="cfe-title-cell"></td>`;
                                                }
                                                const cellClass = cell.read_only
                                                    ? "computed"
                                                    : cell.origen_dato === "Formula"
                                                    ? "cell-fx"
                                                    : cell.origen_dato === "Mapeo"
                                                    ? "cell-map"
                                                    : "";
                                                const fxBtnClass =
                                                    cell.origen_dato === "Formula"
                                                        ? "active-fx"
                                                        : cell.origen_dato === "Mapeo"
                                                        ? "active-map"
                                                        : "";
                                                const fxLabel =
                                                    cell.origen_dato === "Formula"
                                                        ? "fx"
                                                        : cell.origen_dato === "Mapeo"
                                                        ? "M"
                                                        : "fx";
                                                const fxTitle =
                                                    cell.origen_dato === "Formula"
                                                        ? `${__("Fórmula de Celda:")} ${cell.formula_celda || ""}`
                                                        : cell.origen_dato === "Mapeo"
                                                        ? `${__("Origen: Mapeo")} ${cell.ultima_regla_mapeo ? `(${cell.ultima_regla_mapeo})` : ""}`
                                                        : __("Configurar fórmula u origen de celda");

                                                return `
                                            <td>
                                                <div class="cfe-matrix-cell ${cellClass}">
                                                    <div class="dropdown cfe-matrix-format-dropdown">
                                                        <button class="btn btn-default btn-xs dropdown-toggle cfe-matrix-format-btn" type="button" data-toggle="dropdown" title="${__("Formato")} (${this.escape(cell.formato || __("Por defecto"))})">
                                                            ${this.format_symbol(cell.formato || cell.col_tipo_dato)}
                                                        </button>
                                                        <ul class="dropdown-menu">
                                                            <li><a href="#" class="cfe-format-option" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" data-format="">${__("Por defecto")} (${this.escape(cell.col_tipo_dato)})</a></li>
                                                            <li><a href="#" class="cfe-format-option" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" data-format="Moneda">Moneda ($)</a></li>
                                                            <li><a href="#" class="cfe-format-option" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" data-format="Numero">Numero (#)</a></li>
                                                            <li><a href="#" class="cfe-format-option" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" data-format="Porcentaje">Porcentaje (%)</a></li>
                                                            <li><a href="#" class="cfe-format-option" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" data-format="Texto">Texto (T)</a></li>
                                                        </ul>
                                                    </div>
                                                    <input class="cfe-matrix-input" type="text" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" value="${this.escape(cell.input_value)}" ${cell.read_only ? "readonly" : ""} title="${this.escape(cell.helper || fxTitle)}">
                                                    ${
                                                        !cell.read_only
                                                            ? `<button type="button" class="cfe-matrix-fx-btn ${fxBtnClass}" data-table="${this.escape(matrix.codigo_tabla)}" data-row="${this.escape(row.codigo_fila)}" data-col="${this.escape(cell.codigo_columna)}" title="${this.escape(fxTitle)}">${fxLabel}</button>`
                                                            : ""
                                                    }
                                                </div>
                                                ${cell.helper ? `<span class="cfe-code">${this.escape(cell.helper)}</span>` : ""}
                                            </td>
                                        `;
                                            })
                                            .join("")}
                                    </tr>
                                `
                                    )
                                    .join("")}
                            </tbody>
                        </table>
                    </div>
                `
                              )
                              .join("")
                        : `<div class="cfe-empty" style="margin:0 16px 16px;">${__("Agrega columnas y filas para habilitar la matriz visual.")}</div>`
                }
            </div>
        `;
    }

    open_cell_formula_dialog(event) {
        const section = this.get_current_section();
        if (!section) return;
        const tableCode = this.clean_table(event.currentTarget.dataset.table);
        const rowCode = this.clean_code(event.currentTarget.dataset.row);
        const colCode = this.clean_code(event.currentTarget.dataset.col);
        const cell = this.find_section_cell(section, tableCode, rowCode, colCode, false) || {};

        const dialog = new frappe.ui.Dialog({
            title: __("Configurar Celda: {0} [{1}, {2}]", [tableCode, rowCode, colCode]),
            fields: [
                {
                    fieldname: "origen_dato",
                    fieldtype: "Select",
                    label: __("Origen de Dato"),
                    options: "Manual\nMapeo\nFormula",
                    default: cell.origen_dato || "Manual",
                    reqd: 1,
                },
                {
                    fieldname: "formula_celda",
                    fieldtype: "Code",
                    options: "SQL",
                    label: __("Fórmula de Celda"),
                    default: cell.formula_celda || "",
                    description: __("Ej: BAL(\"101*\"), EST(\"NO_EMP\"), YTD(\"41*\"), SI(ES_ACTUAL(), BAL_ACT(\"101*\"), BAL_COMP(\"101*\"))"),
                },
                {
                    fieldname: "comentario",
                    fieldtype: "Small Text",
                    label: __("Comentario Interno"),
                    default: cell.comentario || "",
                },
            ],
            primary_action_label: __("Aplicar a Celda"),
            primary_action: (values) => {
                const target = this.find_section_cell(section, tableCode, rowCode, colCode, true);
                const formula = String(values.formula_celda || "").trim();
                let origin = String(values.origen_dato || "Manual").trim();
                if (formula && origin === "Manual") {
                    origin = "Formula";
                }
                target.origen_dato = origin;
                target.formula_celda = formula;
                target.comentario = String(values.comentario || "").trim();
                this.mark_dirty(true);
                dialog.hide();
                this.refresh_matrix_card();
            },
        });
        dialog.show();
    }

    toggle_fullscreen(event) {
        const target = event.currentTarget.dataset.target;
        if (!target) return;
        this.state.fullscreen_cards[target] = !this.state.fullscreen_cards[target];
        const $card = this.wrapper.find(`[data-card-id="${target}"]`);
        if ($card.length) {
            if (this.state.fullscreen_cards[target]) {
                $card.addClass("cfe-fullscreen");
                $(event.currentTarget).text(__("Salir de Pantalla Completa"));
            } else {
                $card.removeClass("cfe-fullscreen");
                $(event.currentTarget).text(__("Pantalla Completa"));
            }
        }
        this.sync_body_scroll();
    }

    sync_body_scroll() {
        const anyFullscreen = Object.values(this.state.fullscreen_cards || {}).some((val) => !!val);
        document.body.style.overflow = anyFullscreen ? "hidden" : "";
    }

    note_field_html(fieldname, label, value, type = "text", placeholder = "", extraClass = "") {
        return `<div class="cfe-field ${extraClass}"><label>${label}</label><input class="cfe-note-field" data-field="${fieldname}" type="${type}" value="${this.escape(value)}" placeholder="${this.escape(placeholder)}"></div>`;
    }

    note_select_html(fieldname, label, value, options) {
        return `<div class="cfe-field"><label>${label}</label><select class="cfe-note-field" data-field="${fieldname}">${this.options_html(options.map((row) => ({ value: row, label: row })), value)}</select></div>`;
    }

    note_checkbox_html(fieldname, label, checked) {
        return `<div class="cfe-field"><label>${label}</label><label style="display:flex;align-items:center;gap:8px;font-size:13px;color:#0f172a;text-transform:none;"><input class="cfe-note-field" data-field="${fieldname}" type="checkbox" style="width:16px;height:16px;" ${this.asBool(checked) ? "checked" : ""}>${__("Activo")}</label></div>`;
    }

    note_textarea_html(fieldname, label, value) {
        return `<div class="cfe-field"><label>${label}</label><textarea class="cfe-note-field" data-field="${fieldname}">${this.escape(value)}</textarea></div>`;
    }

    section_field_html(fieldname, label, value, type = "text") {
        return `<div class="cfe-field"><label>${label}</label><input class="cfe-section-field" data-field="${fieldname}" type="${type}" value="${this.escape(value)}"></div>`;
    }

    section_select_html(fieldname, label, value, options) {
        return `<div class="cfe-field"><label>${label}</label><select class="cfe-section-field" data-field="${fieldname}">${this.options_html(options.map((row) => ({ value: row, label: row })), value)}</select></div>`;
    }

    section_checkbox_html(fieldname, label, checked) {
        return `<div class="cfe-field"><label>${label}</label><label style="display:flex;align-items:center;gap:8px;font-size:13px;color:#0f172a;text-transform:none;"><input class="cfe-section-field" data-field="${fieldname}" type="checkbox" style="width:16px;height:16px;" ${this.asBool(checked) ? "checked" : ""}>${__("Activo")}</label></div>`;
    }

    section_textarea_html(fieldname, label, value, extraClass = "") {
        return `<div class="cfe-field ${extraClass}"><label>${label}</label><textarea class="cfe-section-field" data-field="${fieldname}">${this.escape(value)}</textarea></div>`;
    }

    get_doc() {
        return this.state.note?.doc || null;
    }

    get_sections() {
        if (!this.state.note) return [];
        if (!Array.isArray(this.state.note.sections)) this.state.note.sections = [];
        return this.state.note.sections;
    }

    get_current_section() {
        const sections = this.get_sections();
        return sections.find((row) => row._client_id === this.state.current_section_id) || sections[0] || null;
    }

    ensure_note_shape() {
        const doc = this.get_doc();
        if (!doc) return;
        doc.orientacion = doc.orientacion || "Vertical";
        doc.cifras_nota = Array.isArray(doc.cifras_nota) ? doc.cifras_nota : [];
        doc.referenced_in_estados = Array.isArray(doc.referenced_in_estados) ? doc.referenced_in_estados : [];
        this.get_sections().forEach((section, index) => {
            section._client_id = section._client_id || section.name || `sec_local_${index + 1}_${Date.now()}`;
            section.columnas_tabulares = Array.isArray(section.columnas_tabulares) ? section.columnas_tabulares : [];
            section.filas_tabulares = Array.isArray(section.filas_tabulares) ? section.filas_tabulares : [];
            section.celdas_tabulares = Array.isArray(section.celdas_tabulares) ? section.celdas_tabulares : [];
        });
    }

    ensure_current_section() {
        const sections = this.get_sections();
        if (!sections.length) {
            this.state.current_section_id = null;
            return;
        }
        if (!sections.some((row) => row._client_id === this.state.current_section_id)) {
            this.state.current_section_id = sections[0]._client_id;
        }
    }

    sort_current_note_data() {
        const sections = this.get_sections();
        sections.sort((a, b) => this.asInt(a.orden, 0) - this.asInt(b.orden, 0) || String(a.codigo_seccion || "").localeCompare(String(b.codigo_seccion || "")));
        sections.forEach((section) => {
            section.celdas_tabulares.sort((a, b) => {
                const left = `${this.clean_table(a.codigo_tabla)}|${this.clean_code(a.codigo_fila)}|${this.clean_code(a.codigo_columna)}`;
                const right = `${this.clean_table(b.codigo_tabla)}|${this.clean_code(b.codigo_fila)}|${this.clean_code(b.codigo_columna)}`;
                return left.localeCompare(right);
            });
        });
    }

    update_note_field(event) {
        const doc = this.get_doc();
        if (!doc) return;
        const field = event.currentTarget.dataset.field;
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (field === "numero_nota") doc[field] = value === "" ? "" : this.asInt(value, 1);
        else if (field === "tamano_letra_impresion") doc[field] = value === "" ? 12 : this.asFloat(value, 12);
        else doc[field] = value;
        doc.identificador_nota = this.build_note_identifier(doc.numero_nota, doc.sub_nota);
        if (field === "estructura_nota" && value === "Compleja" && !this.get_sections().length) {
            this.get_sections().push(this.new_section(1));
            this.ensure_current_section();
        }
        this.mark_dirty(true);
        if (field === "estructura_nota" || field === "numero_nota" || field === "sub_nota" || field === "titulo") {
            this.render_editor();
        }
    }

    add_figure() {
        const doc = this.get_doc();
        if (!doc) return;
        const nextIndex = (doc.cifras_nota || []).length + 1;
        doc.cifras_nota.push({
            codigo_cifra: `CIFRA_${String(nextIndex).padStart(2, "0")}`,
            concepto: `${__("Concepto")} ${nextIndex}`,
            nivel: 1,
            formato_numero: "Moneda",
            redondear_entero: 0,
            monto_actual: 0,
            monto_comparativo: 0,
            valor_texto_actual: "",
            valor_texto_comparativo: "",
            negrita: 0,
            subrayado: 0,
            es_titulo: 0,
            es_linea_blanco: 0,
            origen_dato: "Manual",
            formula_cifras: "",
            es_total: 0,
            es_subtotal: 0,
            no_imprimir: 0,
        });
        this.mark_dirty(true);
        this.render_editor();
    }

    move_figure(index, dir) {
        const doc = this.get_doc();
        if (!doc || !Array.isArray(doc.cifras_nota)) return;
        const target = index + dir;
        if (index < 0 || target < 0 || index >= doc.cifras_nota.length || target >= doc.cifras_nota.length) return;
        const temp = doc.cifras_nota[index];
        doc.cifras_nota[index] = doc.cifras_nota[target];
        doc.cifras_nota[target] = temp;
        this.mark_dirty(true);
        this.render_editor();
    }

    delete_figure(index) {
        const doc = this.get_doc();
        if (!doc || index < 0) return;
        doc.cifras_nota.splice(index, 1);
        this.mark_dirty(true);
        this.render_editor();
    }

    update_figure_field(event) {
        const doc = this.get_doc();
        const index = this.asInt(event.currentTarget.dataset.index, -1);
        const field = event.currentTarget.dataset.field;
        if (!doc || index < 0 || !doc.cifras_nota[index]) return;
        const row = doc.cifras_nota[index];
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;

        if (field === "codigo_cifra") row[field] = this.clean_code(value);
        else if (field === "formula_cifras") {
            row[field] = String(value || "").trim().toUpperCase();
            if (row[field] && row.origen_dato === "Manual") {
                row.origen_dato = "Formula";
            } else if (!row[field] && row.origen_dato === "Formula") {
                row.origen_dato = "Manual";
            }
        } else if (field === "nivel") row[field] = Math.max(this.asInt(value, 1), 1);
        else if (field === "monto_actual" || field === "monto_comparativo") row[field] = value === "" ? null : this.asFloat(value, 0);
        else row[field] = value;

        if (field === "formato_numero") {
            row.formato_numero = value || "Moneda";
            if (row.formato_numero === "Texto") {
                row.formula_cifras = "";
                row.origen_dato = "Manual";
            }
        }
        if (field === "es_linea_blanco" && this.asBool(row.es_linea_blanco)) {
            row.concepto = "";
            row.formato_numero = "Numero";
            row.es_titulo = 0;
            row.es_total = 0;
            row.es_subtotal = 0;
            row.negrita = 0;
            row.subrayado = 0;
            row.origen_dato = "Manual";
            row.formula_cifras = "";
            row.monto_actual = null;
            row.monto_comparativo = null;
            row.valor_texto_actual = "";
            row.valor_texto_comparativo = "";
            if (!row.codigo_cifra) {
                row.codigo_cifra = `BLANK_LINE_${index + 1}`;
            }
        }
        if (field === "es_titulo" && this.asBool(row.es_titulo)) {
            row.es_linea_blanco = 0;
            row.es_total = 0;
            row.es_subtotal = 0;
            row.origen_dato = "Manual";
            row.formula_cifras = "";
            row.monto_actual = null;
            row.monto_comparativo = null;
            row.valor_texto_actual = "";
            row.valor_texto_comparativo = "";
        }

        this.mark_dirty(true);
        this.compute_figures_formulas();
        this.render_editor();
    }

    new_section(index) {
        return {
            _client_id: `sec_local_${index}_${Date.now()}`,
            codigo_seccion: `SEC_${String(index).padStart(2, "0")}`,
            tipo_seccion: "Tabla",
            titulo_seccion: `${__("Seccion")} ${index}`,
            orden: index,
            mostrar_titulo: 1,
            contenido_narrativo: "",
            observaciones: "",
            columnas_tabulares: [],
            filas_tabulares: [],
            celdas_tabulares: [],
        };
    }

    add_section() {
        const doc = this.get_doc();
        if (!doc) return;
        doc.estructura_nota = "Compleja";
        const sections = this.get_sections();
        const section = this.new_section(sections.length + 1);
        sections.push(section);
        this.state.current_section_id = section._client_id;
        this.mark_dirty(true);
        this.render_editor();
    }

    duplicate_current_section() {
        const current = this.get_current_section();
        if (!current) return;
        const sections = this.get_sections();
        const copy = JSON.parse(JSON.stringify(current));
        const nextIndex = sections.length + 1;
        delete copy.name;
        copy._client_id = `sec_local_${nextIndex}_${Date.now()}`;
        copy.codigo_seccion = `${this.clean_code(current.codigo_seccion || "SEC")}_COPIA`;
        copy.titulo_seccion = `${current.titulo_seccion || __("Seccion")} (${__("Copia")})`;
        copy.orden = nextIndex;
        sections.push(copy);
        this.state.current_section_id = copy._client_id;
        this.mark_dirty(true);
        this.render_editor();
    }

    delete_current_section() {
        const current = this.get_current_section();
        if (!current) return;
        frappe.confirm(
            __("¿Eliminar la sección {0}?", [current.codigo_seccion || current.titulo_seccion || ""]),
            () => {
                const sections = this.get_sections();
                const index = sections.findIndex((row) => row._client_id === current._client_id);
                if (index >= 0) sections.splice(index, 1);
                this.ensure_current_section();
                this.mark_dirty(true);
                this.render_editor();
            }
        );
    }

    update_section_field(event) {
        const section = this.get_current_section();
        if (!section) return;
        const field = event.currentTarget.dataset.field;
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (field === "codigo_seccion") section[field] = this.clean_code(value);
        else if (field === "orden") section[field] = Math.max(this.asInt(value, 1), 1);
        else section[field] = value;
        this.mark_dirty(true);
        if (field === "tipo_seccion" || field === "codigo_seccion" || field === "titulo_seccion" || field === "orden") {
            this.render_editor();
        }
    }

    add_column() {
        const section = this.get_current_section();
        if (!section) return;
        const nextIndex = (section.columnas_tabulares || []).length + 1;
        const defaultTable = section.columnas_tabulares[0]?.codigo_tabla || section.filas_tabulares[0]?.codigo_tabla || "TABLA_1";
        section.columnas_tabulares.push({
            codigo_tabla: defaultTable,
            codigo_columna: `COL_${nextIndex}`,
            etiqueta: `${__("Columna")} ${nextIndex}`,
            grupo_columna: "",
            tipo_dato: "Numero",
            alineacion: "Right",
            redondear_entero: 0,
            es_total: 0,
            formula_columnas: "",
        });
        this.ensure_section_cells(section);
        this.mark_dirty(true);
        this.render_editor();
    }

    move_column(index, dir) {
        const section = this.get_current_section();
        if (!section || !Array.isArray(section.columnas_tabulares)) return;
        const cols = section.columnas_tabulares;
        const target = index + dir;
        if (index < 0 || target < 0 || index >= cols.length || target >= cols.length) return;
        const temp = cols[index];
        cols[index] = cols[target];
        cols[target] = temp;
        this.mark_dirty(true);
        this.render_editor();
    }

    delete_column(index) {
        const section = this.get_current_section();
        if (!section || index < 0 || !section.columnas_tabulares[index]) return;
        const removed = section.columnas_tabulares.splice(index, 1)[0];
        section.celdas_tabulares = (section.celdas_tabulares || []).filter(
            (cell) => !(this.clean_table(cell.codigo_tabla) === this.clean_table(removed.codigo_tabla) && this.clean_code(cell.codigo_columna) === this.clean_code(removed.codigo_columna))
        );
        this.mark_dirty(true);
        this.render_editor();
    }

    update_column_field(event) {
        const section = this.get_current_section();
        const index = this.asInt(event.currentTarget.dataset.index, -1);
        const field = event.currentTarget.dataset.field;
        if (!section || index < 0 || !section.columnas_tabulares[index]) return;
        const row = section.columnas_tabulares[index];
        const prevTable = this.clean_table(row.codigo_tabla);
        const prevCode = this.clean_code(row.codigo_columna);
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (field === "codigo_tabla") row[field] = this.clean_table(value);
        else if (field === "codigo_columna") row[field] = this.clean_code(value);
        else if (field === "formula_columnas") row[field] = String(value || "").trim().toUpperCase();
        else row[field] = value;
        const nextTable = this.clean_table(row.codigo_tabla);
        const nextCode = this.clean_code(row.codigo_columna);
        (section.celdas_tabulares || []).forEach((cell) => {
            if (this.clean_table(cell.codigo_tabla) === prevTable && this.clean_code(cell.codigo_columna) === prevCode) {
                cell.codigo_tabla = nextTable;
                cell.codigo_columna = nextCode;
            }
        });
        this.ensure_section_cells(section);
        this.mark_dirty(true);
        this.refresh_matrix_card();
    }

    add_row() {
        const section = this.get_current_section();
        if (!section) return;
        const nextIndex = (section.filas_tabulares || []).length + 1;
        const defaultTable = section.filas_tabulares[0]?.codigo_tabla || section.columnas_tabulares[0]?.codigo_tabla || "TABLA_1";
        section.filas_tabulares.push({
            codigo_tabla: defaultTable,
            codigo_fila: `FILA_${String(nextIndex).padStart(2, "0")}`,
            descripcion: `${__("Fila")} ${nextIndex}`,
            nivel: 1,
            tipo_fila: "Detalle",
            formula_filas: "",
            negrita: 0,
            subrayado: 0,
        });
        this.ensure_section_cells(section);
        this.mark_dirty(true);
        this.render_editor();
    }

    move_row(index, dir) {
        const section = this.get_current_section();
        if (!section || !Array.isArray(section.filas_tabulares)) return;
        const rows = section.filas_tabulares;
        const target = index + dir;
        if (index < 0 || target < 0 || index >= rows.length || target >= rows.length) return;
        const temp = rows[index];
        rows[index] = rows[target];
        rows[target] = temp;
        this.mark_dirty(true);
        this.render_editor();
    }

    delete_row(index) {
        const section = this.get_current_section();
        if (!section || index < 0 || !section.filas_tabulares[index]) return;
        const removed = section.filas_tabulares.splice(index, 1)[0];
        section.celdas_tabulares = (section.celdas_tabulares || []).filter(
            (cell) => !(this.clean_table(cell.codigo_tabla) === this.clean_table(removed.codigo_tabla) && this.clean_code(cell.codigo_fila) === this.clean_code(removed.codigo_fila))
        );
        this.mark_dirty(true);
        this.render_editor();
    }

    update_row_field(event) {
        const section = this.get_current_section();
        const index = this.asInt(event.currentTarget.dataset.index, -1);
        const field = event.currentTarget.dataset.field;
        if (!section || index < 0 || !section.filas_tabulares[index]) return;
        const row = section.filas_tabulares[index];
        const prevTable = this.clean_table(row.codigo_tabla);
        const prevCode = this.clean_code(row.codigo_fila);
        const value = event.currentTarget.type === "checkbox" ? (event.currentTarget.checked ? 1 : 0) : event.currentTarget.value;
        if (field === "codigo_tabla") row[field] = this.clean_table(value);
        else if (field === "codigo_fila") row[field] = this.clean_code(value);
        else if (field === "nivel") row[field] = Math.max(this.asInt(value, 1), 1);
        else if (field === "formula_filas") row[field] = String(value || "").trim().toUpperCase();
        else row[field] = value;
        if (field === "tipo_fila" && value === "Titulo") {
            row.formula_filas = "";
        }
        const nextTable = this.clean_table(row.codigo_tabla);
        const nextCode = this.clean_code(row.codigo_fila);
        (section.celdas_tabulares || []).forEach((cell) => {
            if (this.clean_table(cell.codigo_tabla) === prevTable && this.clean_code(cell.codigo_fila) === prevCode) {
                cell.codigo_tabla = nextTable;
                cell.codigo_fila = nextCode;
            }
        });
        this.ensure_section_cells(section);
        this.mark_dirty(true);
        this.refresh_matrix_card();
    }

    find_section_cell(section, tableCode, rowCode, colCode, create = true) {
        const t = this.clean_table(tableCode);
        const r = this.clean_code(rowCode);
        const c = this.clean_code(colCode);
        let cell = (section.celdas_tabulares || []).find(
            (row) => this.clean_table(row.codigo_tabla) === t && this.clean_code(row.codigo_fila) === r && this.clean_code(row.codigo_columna) === c
        );
        if (!cell && create) {
            cell = {
                codigo_tabla: t,
                codigo_fila: r,
                codigo_columna: c,
                valor_numero: null,
                valor_texto: "",
                formato_numero: "",
                redondear_entero: 0,
                origen_dato: "Manual",
                formula_celda: "",
                comentario: "",
            };
            section.celdas_tabulares.push(cell);
        }
        return cell;
    }

    section_cell_is_default(cell) {
        if (!cell) return true;
        const hasNumber = cell.valor_numero !== null && cell.valor_numero !== undefined && cell.valor_numero !== "";
        const hasText = String(cell.valor_texto || "").trim() !== "";
        const hasFormat = String(cell.formato_numero || "").trim() !== "";
        const hasComment = String(cell.comentario || "").trim() !== "";
        const hasFormula = String(cell.formula_celda || "").trim() !== "";
        const hasRule = String(cell.ultima_regla_mapeo || "").trim() !== "";
        const nonManual = String(cell.origen_dato || "Manual").trim() !== "Manual";
        return !hasNumber && !hasText && !hasFormat && !hasComment && !hasFormula && !hasRule && !nonManual;
    }

    ensure_section_cells(section) {
        if (!section) return;
        const validTables = new Set();
        const validRows = new Set();
        const validCols = new Set();

        (section.filas_tabulares || []).forEach((row) => {
            const tableCode = this.clean_table(row.codigo_tabla);
            const rowCode = this.clean_code(row.codigo_fila);
            validTables.add(tableCode);
            if (String(row.tipo_fila || "Detalle") !== "Titulo") {
                validRows.add(`${tableCode}::${rowCode}`);
            }
        });
        (section.columnas_tabulares || []).forEach((col) => {
            const tableCode = this.clean_table(col.codigo_tabla);
            const colCode = this.clean_code(col.codigo_columna);
            validTables.add(tableCode);
            validCols.add(`${tableCode}::${colCode}`);
        });

        section.celdas_tabulares = (section.celdas_tabulares || []).filter((cell) => {
            const tableCode = this.clean_table(cell.codigo_tabla);
            const rowKey = `${tableCode}::${this.clean_code(cell.codigo_fila)}`;
            const colKey = `${tableCode}::${this.clean_code(cell.codigo_columna)}`;
            if (!validTables.has(tableCode) || !validRows.has(rowKey) || !validCols.has(colKey)) {
                return false;
            }
            return !this.section_cell_is_default(cell);
        });
    }

    update_matrix_value(event) {
        const section = this.get_current_section();
        if (!section) return;
        const tableCode = this.clean_table(event.currentTarget.dataset.table);
        const rowCode = this.clean_code(event.currentTarget.dataset.row);
        const colCode = this.clean_code(event.currentTarget.dataset.col);
        const rawValue = String(event.currentTarget.value ?? "").trim();
        const cell = this.find_section_cell(section, tableCode, rowCode, colCode, true);

        // Allow typing =FORMULA directly into a cell
        if (rawValue.startsWith("=")) {
            const expr = rawValue.slice(1).trim();
            cell.origen_dato = "Formula";
            cell.formula_celda = expr;
            this.mark_dirty(true);
            this.refresh_matrix_card();
            return;
        }

        const column = (section.columnas_tabulares || []).find(
            (row) => this.clean_table(row.codigo_tabla) === tableCode && this.clean_code(row.codigo_columna) === colCode
        );
        const effFormat = cell.formato_numero || column?.tipo_dato || "Numero";
        if (effFormat === "Texto") {
            cell.valor_texto = rawValue;
            cell.valor_numero = null;
        } else {
            const parsed = this.parse_localized_number(rawValue);
            if (rawValue === "") {
                cell.valor_numero = null;
                cell.valor_texto = "";
            } else if (parsed !== null) {
                cell.valor_numero = parsed;
                cell.valor_texto = "";
            } else {
                cell.valor_texto = rawValue;
                cell.valor_numero = null;
            }
        }
        if (cell.origen_dato !== "Formula") {
            cell.origen_dato = "Manual";
        }
        if (this.section_cell_is_default(cell)) {
            section.celdas_tabulares = (section.celdas_tabulares || []).filter((row) => row !== cell);
        }
        this.mark_dirty(true);
        this.refresh_matrix_card();
    }

    update_matrix_format(event) {
        const section = this.get_current_section();
        if (!section) return;
        const tableCode = this.clean_table(event.currentTarget.dataset.table);
        const rowCode = this.clean_code(event.currentTarget.dataset.row);
        const colCode = this.clean_code(event.currentTarget.dataset.col);
        const fmt = event.currentTarget.dataset.format || "";
        const cell = this.find_section_cell(section, tableCode, rowCode, colCode, true);
        cell.formato_numero = fmt;
        if (this.section_cell_is_default(cell)) {
            section.celdas_tabulares = (section.celdas_tabulares || []).filter((row) => row !== cell);
        }
        this.mark_dirty(true);
        this.refresh_matrix_card();
    }

    refresh_matrix_card() {
        const section = this.get_current_section();
        const $card = this.wrapper.find('[data-role="matrix-card"]');
        if (!section || !$card.length) {
            this.render_editor();
            return;
        }
        $card.replaceWith(this.render_matrix_editor(section));
    }

    format_symbol(fmt) {
        if (fmt === "Moneda") return "$";
        if (fmt === "Numero") return "#";
        if (fmt === "Porcentaje") return "%";
        if (fmt === "Texto") return "T";
        return "&bull;";
    }

    compute_matrix(section) {
        this.ensure_section_cells(section);
        const tableCodes = [];
        const addTable = (value) => {
            const code = this.clean_table(value);
            if (!tableCodes.includes(code)) tableCodes.push(code);
        };
        (section.columnas_tabulares || []).forEach((row) => addTable(row.codigo_tabla));
        (section.filas_tabulares || []).forEach((row) => addTable(row.codigo_tabla));
        if (!tableCodes.length) return [];

        return tableCodes.map((tableCode) => {
            let columns = (section.columnas_tabulares || []).filter((row) => this.clean_table(row.codigo_tabla) === tableCode);
            const rows = (section.filas_tabulares || []).filter((row) => this.clean_table(row.codigo_tabla) === tableCode);
            if (!columns.length && rows.length) {
                columns = [
                    {
                        codigo_tabla: tableCode,
                        codigo_columna: "VALOR",
                        etiqueta: "Valor",
                        grupo_columna: "",
                        tipo_dato: "Numero",
                        alineacion: "Right",
                        formula_columnas: "",
                    },
                ];
            }
            const colMap = new Map(columns.map((row) => [this.clean_code(row.codigo_columna), row]));
            const rowMap = new Map(rows.map((row) => [this.clean_code(row.codigo_fila), row]));
            const cellMap = new Map();
            (section.celdas_tabulares || [])
                .filter((row) => this.clean_table(row.codigo_tabla) === tableCode)
                .forEach((cell) => {
                    cellMap.set(`${this.clean_code(cell.codigo_fila)}::${this.clean_code(cell.codigo_columna)}`, cell);
                });

            const numCache = new Map();
            const resolveNumber = (rowCode, colCode, stack = new Set()) => {
                const key = `${rowCode}::${colCode}`;
                if (numCache.has(key)) return numCache.get(key);
                const row = rowMap.get(rowCode);
                const col = colMap.get(colCode);
                const cell = cellMap.get(key);
                if (!row || !col || row.tipo_fila === "Titulo") return 0;

                const effFormat = cell?.formato_numero || col.tipo_dato || "Numero";
                if (effFormat === "Texto") return 0;
                if (stack.has(key)) return 0;

                const nextStack = new Set(stack);
                nextStack.add(key);

                // Match SeccionNotaEEFF._calcular_tablas() precedence:
                // 1. Cell with origen_dato === "Formula" and formula_celda
                // 2. Column with formula_columnas
                // 3. Row with formula_filas
                // 4. Direct cell valor_numero
                const isCellFormula = cell?.origen_dato === "Formula" && String(cell?.formula_celda || "").trim() !== "";
                let value = 0;

                if (isCellFormula) {
                    value = this.asFloat(cell?.valor_numero, 0);
                } else if (String(col.formula_columnas || "").trim()) {
                    value = this.parse_formula(col.formula_columnas).reduce(
                        (acc, item) => acc + item.sign * resolveNumber(rowCode, item.code, nextStack),
                        0
                    );
                } else if (String(row.formula_filas || "").trim()) {
                    value = this.parse_formula(row.formula_filas).reduce(
                        (acc, item) => acc + item.sign * resolveNumber(item.code, colCode, nextStack),
                        0
                    );
                } else {
                    value = this.asFloat(cell?.valor_numero, 0);
                }

                numCache.set(key, value);
                return value;
            };

            const grupos = [];
            columns.forEach((col) => {
                const group = String(col.grupo_columna || "").trim();
                const last = grupos[grupos.length - 1];
                if (group) {
                    if (last && last.es_grupo && last.grupo === group) {
                        last.columnas.push(col);
                        last.colspan += 1;
                    } else {
                        grupos.push({ es_grupo: true, grupo: group, colspan: 1, columnas: [col] });
                    }
                } else {
                    grupos.push({ es_grupo: false, columna: col });
                }
            });

            return {
                codigo_tabla: tableCode,
                columnas: columns,
                grupos_encabezado: grupos,
                tiene_grupos: grupos.some((row) => row.es_grupo),
                filas: rows.map((row) => {
                    const rowCode = this.clean_code(row.codigo_fila);
                    const isTitle = row.tipo_fila === "Titulo";
                    return {
                        ...row,
                        codigo_fila: rowCode,
                        celdas: columns.map((col) => {
                            const colCode = this.clean_code(col.codigo_columna);
                            const cell = cellMap.get(`${rowCode}::${colCode}`);
                            const isCellFormula = cell?.origen_dato === "Formula" && String(cell?.formula_celda || "").trim() !== "";
                            const hasColFormula = !isCellFormula && !!String(col.formula_columnas || "").trim();
                            const hasRowFormula = !isCellFormula && !hasColFormula && !!String(row.formula_filas || "").trim();
                            const readOnly = isTitle || hasRowFormula || hasColFormula;

                            const effFormat = cell?.formato_numero || col.tipo_dato || "Numero";
                            const decimals = this.asBool(cell?.redondear_entero) || this.asBool(col.redondear_entero) ? 0 : 2;
                            let inputValue = "";
                            if (!isTitle) {
                                if (effFormat === "Texto") {
                                    inputValue = cell?.valor_texto || (cell?.valor_numero !== null && cell?.valor_numero !== undefined ? String(cell.valor_numero) : "");
                                } else if (hasRowFormula || hasColFormula) {
                                    inputValue = this.format_number(resolveNumber(rowCode, colCode), decimals);
                                } else if (cell && String(cell.valor_texto || "").trim()) {
                                    inputValue = String(cell.valor_texto).trim();
                                } else if (cell && cell.valor_numero !== null && cell.valor_numero !== undefined && cell.valor_numero !== "") {
                                    inputValue = this.format_number(cell.valor_numero, decimals);
                                }
                            }
                            let helper = "";
                            if (hasColFormula) helper = `Col = ${col.formula_columnas}`;
                            else if (hasRowFormula) helper = `Fila = ${row.formula_filas}`;
                            else if (isCellFormula) helper = `fx = ${cell.formula_celda}`;
                            else if (cell?.origen_dato === "Mapeo") helper = `Mapeo${cell.ultima_regla_mapeo ? `: ${cell.ultima_regla_mapeo}` : ""}`;

                            return {
                                codigo_columna: colCode,
                                is_title: isTitle,
                                read_only: readOnly,
                                input_value: inputValue,
                                helper,
                                formato: cell?.formato_numero || "",
                                col_tipo_dato: col.tipo_dato || "Numero",
                                origen_dato: cell?.origen_dato || "Manual",
                                formula_celda: cell?.formula_celda || "",
                                ultima_regla_mapeo: cell?.ultima_regla_mapeo || "",
                            };
                        }),
                    };
                }),
            };
        });
    }

    run_package_mapping() {
        const pkg = this.state.package_name || this.get_doc()?.paquete_eeff;
        if (!pkg) {
            frappe.msgprint(__("Selecciona primero un paquete EEFF."));
            return;
        }
        const execute = () => {
            frappe.call({
                method: "mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.ejecutar_mapeo",
                args: { paquete_name: pkg },
                freeze: true,
                freeze_message: __("Ejecutando mapeo contable y fórmulas del paquete..."),
                callback: (r) => {
                    const result = r.message || {};
                    const alertas = Array.isArray(result.alertas) ? result.alertas : [];
                    frappe.show_alert({
                        message: __("Mapeo aplicado al paquete {0}", [pkg]),
                        indicator: alertas.length ? "orange" : "green",
                    });
                    if (alertas.length) {
                        frappe.msgprint({
                            title: __("Mapeo con Alertas"),
                            indicator: "orange",
                            message: alertas.slice(0, 10).join("<br>"),
                        });
                    }
                    this.load_bootstrap({ package_name: pkg, note_name: this.get_doc()?.name || this.state.selected_note_name }, true);
                },
            });
        };

        if (this.state.is_dirty && this.get_doc()) {
            frappe.confirm(
                __("Tienes cambios sin guardar en la nota actual. ¿Deseas guardar la nota primero y luego ejecutar el mapeo?"),
                () => this.save_current_note(() => execute()),
                () => execute()
            );
            return;
        }
        execute();
    }

    print_current_note() {
        const doc = this.get_doc();
        if (!doc?.name) {
            frappe.msgprint(__("Selecciona una nota para imprimir."));
            return;
        }
        const url = frappe.urllib.get_full_url(
            `/printview?doctype=${encodeURIComponent("Nota EEFF")}&name=${encodeURIComponent(doc.name)}&format=${encodeURIComponent("Nota EEFF - Individual")}&trigger_print=1`
        );
        window.open(url, "_blank");
    }

    delete_current_note() {
        const doc = this.get_doc();
        if (!doc?.name) {
            frappe.msgprint(__("No hay una nota seleccionada para eliminar."));
            return;
        }
        const noteLabel = doc.identificador_nota || doc.numero_nota || doc.name;
        frappe.confirm(
            __("¿Estás seguro de eliminar permanentemente la Nota {0} ({1})?", [noteLabel, doc.titulo || ""]),
            () => {
                frappe.call({
                    method: "mfi_tools.mfi_tools.page.asistente_notas_eeff.asistente_notas_eeff.delete_note_from_editor",
                    args: { note_name: doc.name },
                    freeze: true,
                    freeze_message: __("Eliminando nota..."),
                    callback: (r) => {
                        this.absorb_bootstrap(r.message || {});
                        this.render_all();
                        frappe.show_alert({
                            message: __("Nota {0} eliminada.", [noteLabel]),
                            indicator: "green",
                        });
                    },
                });
            }
        );
    }

    save_current_note(afterSaveCallback = null) {
        const doc = this.get_doc();
        if (!doc) {
            frappe.msgprint(__("Selecciona una nota antes de guardar."));
            return;
        }
        this.get_sections().forEach((section) => this.ensure_section_cells(section));
        this.sort_current_note_data();
        const payload = {
            doc,
            sections: this.get_sections().map((section, index) => ({
                ...section,
                orden: index + 1,
            })),
        };
        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_notas_eeff.asistente_notas_eeff.save_note_editor",
            args: { note_payload: JSON.stringify(payload) },
            freeze: true,
            freeze_message: __("Guardando nota..."),
            callback: (r) => {
                const currentSectionCode = this.get_current_section()?.codigo_seccion;
                this.absorb_bootstrap(r.message || {});
                const match = this.get_sections().find((row) => row.codigo_seccion === currentSectionCode);
                if (match) this.state.current_section_id = match._client_id;
                this.render_all();
                frappe.show_alert({ message: __("Nota guardada correctamente."), indicator: "green" });
                if (typeof afterSaveCallback === "function") {
                    afterSaveCallback();
                }
            },
        });
    }

    open_create_note_dialog() {
        if (!this.state.package_name) {
            frappe.msgprint(__("Selecciona primero un paquete EEFF."));
            return;
        }
        const nextNumber = this.state.summary?.next_numero_nota || 1;
        const dialog = new frappe.ui.Dialog({
            title: __("Nueva Nota EEFF"),
            fields: [
                { fieldname: "numero_nota", fieldtype: "Int", label: __("Numero Nota"), reqd: 1, default: nextNumber },
                { fieldname: "sub_nota", fieldtype: "Data", label: __("Sub Nota"), description: __("Opcional para subnotas como 7 (a), 7 (b).") },
                { fieldname: "titulo", fieldtype: "Data", label: __("Titulo"), reqd: 1, default: `${__("Nota")} ${nextNumber}` },
                { fieldname: "estructura_nota", fieldtype: "Select", label: __("Estructura"), options: "Simple\nCompleja", default: "Simple", reqd: 1 },
                { fieldname: "orientacion", fieldtype: "Select", label: __("Orientacion de Pagina"), options: "Vertical\nHorizontal", default: "Vertical" },
                { fieldname: "tamano_letra_impresion", fieldtype: "Float", label: __("Tamano Letra Tabla (pt)"), default: 12 },
                { fieldname: "ancho_tabla_impresion", fieldtype: "Data", label: __("Ancho de Tablas"), default: "100%" },
                { fieldname: "alineacion_tabla_impresion", fieldtype: "Select", label: __("Ubicacion de Tablas"), options: "Izquierda\nCentro\nDerecha", default: "Centro" },
                { fieldname: "centrar_valores_verticalmente", fieldtype: "Check", label: __("Centrar Valores Verticalmente"), default: 0 },
                { fieldname: "contenido_narrativo", fieldtype: "Small Text", label: __("Contenido Narrativo") },
                { fieldname: "observaciones", fieldtype: "Small Text", label: __("Observaciones") },
            ],
            primary_action_label: __("Crear Nota"),
            primary_action: (values) => {
                frappe.call({
                    method: "mfi_tools.mfi_tools.page.asistente_notas_eeff.asistente_notas_eeff.create_note_for_editor",
                    args: {
                        package_name: this.state.package_name,
                        ...values,
                    },
                    freeze: true,
                    freeze_message: __("Creando nota..."),
                    callback: (r) => {
                        dialog.hide();
                        this.absorb_bootstrap(r.message || {});
                        this.render_all();
                        frappe.show_alert({ message: __("Nota creada."), indicator: "green" });
                    },
                });
            },
        });
        dialog.show();
    }

    open_package_form() {
        if (!this.state.package_name) {
            frappe.msgprint(__("No hay paquete seleccionado."));
            return;
        }
        frappe.set_route("Form", "Paquete EEFF", this.state.package_name);
    }

    open_current_note_form() {
        const doc = this.get_doc();
        if (!doc?.name) {
            frappe.msgprint(__("No hay nota seleccionada."));
            return;
        }
        frappe.set_route("Form", "Nota EEFF", doc.name);
    }

    open_note_list() {
        if (!this.state.package_name) {
            frappe.set_route("List", "Nota EEFF");
            return;
        }
        frappe.set_route("List", "Nota EEFF", { paquete_eeff: this.state.package_name });
    }

    download_current_section_csv() {
        const section = this.get_current_section();
        if (!section) return;
        const rows = [["record_type", "codigo_tabla", "codigo_columna", "etiqueta", "grupo_columna", "tipo_dato", "alineacion", "redondear_entero", "es_total", "formula_columnas", "codigo_fila", "descripcion", "nivel", "tipo_fila", "formula_filas", "negrita", "subrayado", "valor_numero", "valor_texto", "formato_numero", "origen_dato", "formula_celda", "comentario"]];
        (section.columnas_tabulares || []).forEach((col) =>
            rows.push([
                "COLUMN",
                col.codigo_tabla || "TABLA_1",
                col.codigo_columna || "",
                col.etiqueta || "",
                col.grupo_columna || "",
                col.tipo_dato || "Numero",
                col.alineacion || "Right",
                this.asBool(col.redondear_entero) ? 1 : 0,
                this.asBool(col.es_total) ? 1 : 0,
                col.formula_columnas || "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ])
        );
        (section.filas_tabulares || []).forEach((row) =>
            rows.push([
                "ROW",
                row.codigo_tabla || "TABLA_1",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                row.codigo_fila || "",
                row.descripcion || "",
                row.nivel || 1,
                row.tipo_fila || "Detalle",
                row.formula_filas || "",
                this.asBool(row.negrita) ? 1 : 0,
                this.asBool(row.subrayado) ? 1 : 0,
                "",
                "",
                "",
                "",
                "",
                "",
            ])
        );
        (section.celdas_tabulares || []).forEach((cell) =>
            rows.push([
                "CELL",
                cell.codigo_tabla || "TABLA_1",
                cell.codigo_columna || "",
                "",
                "",
                "",
                "",
                this.asBool(cell.redondear_entero) ? 1 : 0,
                "",
                "",
                cell.codigo_fila || "",
                "",
                "",
                "",
                "",
                "",
                "",
                cell.valor_numero ?? "",
                cell.valor_texto || "",
                cell.formato_numero || "",
                cell.origen_dato || "Manual",
                cell.formula_celda || "",
                cell.comentario || "",
            ])
        );
        const content = rows.map((row) => row.map((value) => this.csv_escape(value)).join(",")).join("\r\n");
        const blob = new Blob(["\ufeff", content], { type: "text/csv;charset=utf-8;" });
        const link = document.createElement("a");
        const doc = this.get_doc();
        link.href = URL.createObjectURL(blob);
        link.download = `${this.clean_code(doc?.identificador_nota || doc?.numero_nota || "NOTA")}_${this.clean_code(section.codigo_seccion || "SECCION")}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    open_csv_picker() {
        const input = this.wrapper.find(".cfe-csv-input").get(0);
        if (!input) return;
        input.value = "";
        input.click();
    }

    handle_csv_upload(event) {
        const file = event.currentTarget.files?.[0];
        const section = this.get_current_section();
        if (!file || !section) return;
        const reader = new FileReader();
        reader.onload = () => {
            try {
                this.import_section_csv(section, String(reader.result || ""));
                this.mark_dirty(true);
                this.render_editor();
                frappe.show_alert({ message: __("CSV cargado en la sección actual."), indicator: "green" });
            } catch (error) {
                frappe.msgprint({ title: __("CSV Inválido"), indicator: "red", message: error?.message || __("No se pudo procesar el archivo CSV.") });
            }
        };
        reader.readAsText(file, "utf-8");
    }

    import_section_csv(section, text) {
        const matrix = this.parse_csv(text);
        if (!matrix.length) throw new Error(__("El archivo CSV está vacío."));
        const headers = matrix[0].map((value) => String(value || "").replace(/^\ufeff/, "").trim());
        const cols = [];
        const rows = [];
        const cells = [];
        matrix.slice(1).forEach((values) => {
            if (!values.some((value) => String(value || "").trim())) return;
            const item = {};
            headers.forEach((header, idx) => {
                item[header] = values[idx] ?? "";
            });
            const type = String(item.record_type || "").trim().toUpperCase();
            if (type === "COLUMN") {
                cols.push({
                    codigo_tabla: this.clean_table(item.codigo_tabla),
                    codigo_columna: this.clean_code(item.codigo_columna),
                    etiqueta: item.etiqueta || item.codigo_columna || __("Columna"),
                    grupo_columna: item.grupo_columna || "",
                    tipo_dato: item.tipo_dato || "Numero",
                    alineacion: item.alineacion || "Right",
                    redondear_entero: this.asBool(item.redondear_entero) ? 1 : 0,
                    es_total: this.asBool(item.es_total) ? 1 : 0,
                    formula_columnas: String(item.formula_columnas || "").trim().toUpperCase(),
                });
            } else if (type === "ROW") {
                rows.push({
                    codigo_tabla: this.clean_table(item.codigo_tabla),
                    codigo_fila: this.clean_code(item.codigo_fila),
                    descripcion: item.descripcion || item.codigo_fila || __("Fila"),
                    nivel: Math.max(this.asInt(item.nivel, 1), 1),
                    tipo_fila: item.tipo_fila || "Detalle",
                    formula_filas: String(item.formula_filas || "").trim().toUpperCase(),
                    negrita: this.asBool(item.negrita) ? 1 : 0,
                    subrayado: this.asBool(item.subrayado) ? 1 : 0,
                });
            } else if (type === "CELL") {
                cells.push({
                    codigo_tabla: this.clean_table(item.codigo_tabla),
                    codigo_fila: this.clean_code(item.codigo_fila),
                    codigo_columna: this.clean_code(item.codigo_columna),
                    valor_numero: String(item.valor_numero || "").trim() === "" ? null : this.asFloat(item.valor_numero, 0),
                    valor_texto: item.valor_texto || "",
                    formato_numero: item.formato_numero || "",
                    redondear_entero: this.asBool(item.redondear_entero) ? 1 : 0,
                    origen_dato: item.origen_dato || (String(item.formula_celda || "").trim() ? "Formula" : "Manual"),
                    formula_celda: item.formula_celda || "",
                    comentario: item.comentario || "",
                });
            }
        });
        section.columnas_tabulares = cols;
        section.filas_tabulares = rows;
        section.celdas_tabulares = cells;
        this.ensure_section_cells(section);
    }

    parse_csv(text) {
        const rows = [];
        let row = [];
        let current = "";
        let inQuotes = false;
        for (let i = 0; i < text.length; i += 1) {
            const char = text[i];
            const next = text[i + 1];
            if (inQuotes) {
                if (char === '"' && next === '"') {
                    current += '"';
                    i += 1;
                } else if (char === '"') {
                    inQuotes = false;
                } else {
                    current += char;
                }
            } else if (char === '"') {
                inQuotes = true;
            } else if (char === ",") {
                row.push(current);
                current = "";
            } else if (char === "\r" && next === "\n") {
                row.push(current);
                rows.push(row);
                row = [];
                current = "";
                i += 1;
            } else if (char === "\n" || char === "\r") {
                row.push(current);
                rows.push(row);
                row = [];
                current = "";
            } else {
                current += char;
            }
        }
        if (current !== "" || row.length) {
            row.push(current);
            rows.push(row);
        }
        return rows;
    }

    csv_escape(value) {
        const raw = value === null || value === undefined ? "" : String(value);
        if (!/[",\r\n]/.test(raw)) return raw;
        return `"${raw.replace(/"/g, '""')}"`;
    }

    parse_formula(expression) {
        return String(expression || "")
            .split(/[\n,;]+/)
            .map((raw) => String(raw || "").trim().toUpperCase())
            .filter(Boolean)
            .map((token) => {
                let sign = 1;
                let code = token;
                if (token[0] === "+" || token[0] === "-") {
                    sign = token[0] === "-" ? -1 : 1;
                    code = token.slice(1).trim();
                }
                return { sign, code: this.clean_code(code) };
            })
            .filter((row) => row.code);
    }

    build_note_identifier(number, subNote) {
        const cleanNumber = String(number || "").trim();
        const cleanSub = String(subNote || "").replace(/^\((.*)\)$/, "$1").trim();
        if (!cleanNumber) return "";
        return cleanSub ? `${cleanNumber} (${cleanSub})` : cleanNumber;
    }

    approval_pill_class(status) {
        if (status === "Aprobado" || status === "Emitido") return "approved";
        if (status === "En Revision" || status === "Revision") return "review";
        return "draft";
    }

    options_html(options, selectedValue) {
        return (options || [])
            .map((row) => `<option value="${this.escape(row.value)}" ${String(row.value) === String(selectedValue || "") ? "selected" : ""}>${this.escape(row.label)}</option>`)
            .join("");
    }

    clean_code(value) {
        return String(value || "").trim().toUpperCase().replace(/[^A-Z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
    }

    clean_table(value) {
        return this.clean_code(value) || "TABLA_1";
    }

    asInt(value, fallback = 0) {
        const parsed = parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    asFloat(value, fallback = 0) {
        const parsed = parseFloat(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    asBool(value) {
        if (typeof value === "boolean") return value;
        if (typeof value === "number") return value !== 0;
        return ["1", "true", "si", "yes", "checked"].includes(String(value || "").trim().toLowerCase());
    }

    format_number(value, decimals = 2) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "";
        return num.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }

    parse_localized_number(raw) {
        let text = String(raw ?? "").trim();
        if (!text) return null;
        let negative = false;
        if (text.startsWith("(") && text.endsWith(")")) {
            negative = true;
            text = text.slice(1, -1).trim();
        }
        text = text.replace(/\s+/g, "");
        if (!/^[-+]?[\d.,]+$/.test(text)) return null;
        if (text.includes(",") && text.includes(".")) {
            if (text.lastIndexOf(",") > text.lastIndexOf(".")) {
                text = text.replace(/\./g, "").replace(",", ".");
            } else {
                text = text.replace(/,/g, "");
            }
        } else if (text.includes(",")) {
            const parts = text.split(",");
            if (parts.length > 2) text = parts.join("");
            else if (parts[1].length === 3 && parts[0].replace(/^[-+]/, "").length >= 1) text = parts.join("");
            else text = `${parts[0]}.${parts[1]}`;
        }
        const parsed = Number(text);
        if (!Number.isFinite(parsed)) return null;
        return negative ? -Math.abs(parsed) : parsed;
    }

    escape(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }
}
