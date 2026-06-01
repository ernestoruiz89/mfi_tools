frappe.pages["helper-mapeo-notas-eeff"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Helper Mapeo Notas EEFF",
        single_column: true,
    });

    frappe.pages["helper-mapeo-notas-eeff"].helper = new HelperMapeoNotasEEFF(page);
    frappe.pages["helper-mapeo-notas-eeff"].helper.init();
};

frappe.pages["helper-mapeo-notas-eeff"].on_page_show = function () {
    const helper = frappe.pages["helper-mapeo-notas-eeff"].helper;
    if (!helper) return;
    helper.apply_route_options();
    const hasRouteOptions = !!Object.keys(helper.state.route_options || {}).length;
    if (hasRouteOptions || !helper.bootstrapped) {
        helper.load_bootstrap({}, true);
    }
};

class HelperMapeoNotasEEFF {
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
            note_name: "",
            clients: [],
            meses: [],
            packages: [],
            notes: [],
            summary: null,
            note: null,
            route_options: {},
            fullscreen_cards: {},
        };
    }

    init() {
        this.setup_styles();
        this.render_shell();
        this.bind_events();
        this.page.set_primary_action(__("Ejecutar Mapeo"), () => this.run_mapping(), "play");
        this.page.set_secondary_action(__("Nueva Regla"), () => this.create_generic_rule());
        this.page.add_menu_item(__("Abrir Paquete"), () => this.open_package_form());
        this.page.add_menu_item(__("Abrir Nota"), () => this.open_note_form());
        this.page.add_menu_item(__("Abrir Editor de Notas"), () => this.open_note_editor());
        this.page.add_menu_item(__("Ver Reglas de la Nota"), () => this.open_rule_list());
        this.render_all();
    }

    apply_route_options() {
        this.state.route_options = frappe.route_options || {};
        frappe.route_options = null;
    }

    setup_styles() {
        if (document.getElementById("cf-note-mapping-helper-style")) return;
        const style = document.createElement("style");
        style.id = "cf-note-mapping-helper-style";
        style.textContent = `
            .cfnm-shell{display:grid;grid-template-columns:320px minmax(0,1fr);gap:16px;padding:18px;border:1px solid #d6dee8;border-radius:24px;background:linear-gradient(160deg,#f7fbf8 0%,#eef5ff 50%,#fff8ef 100%)}
            .cfnm-sidebar,.cfnm-card{background:#fff;border:1px solid #dbe4ee;border-radius:20px;box-shadow:0 14px 30px rgba(15,23,42,.06)}
            .cfnm-sidebar{overflow:hidden}.cfnm-main{display:flex;flex-direction:column;gap:14px;min-width:0}
            .cfnm-head{padding:15px 16px;border-bottom:1px solid #edf2f7}
            .cfnm-head h3{margin:0;font-size:15px;font-weight:800;color:#0f172a}
            .cfnm-head p{margin:6px 0 0;font-size:12px;color:#64748b}
            .cfnm-section{padding:15px 16px}
            .cfnm-grid{display:grid;gap:12px}
            .cfnm-grid.filters{grid-template-columns:repeat(2,minmax(0,1fr))}
            .cfnm-field{display:flex;flex-direction:column;gap:6px}
            .cfnm-field label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:800}
            .cfnm-field input,.cfnm-field select{width:100%;border:1px solid #cbd5e1;border-radius:10px;padding:9px 10px;font-size:13px;background:#fff}
            .cfnm-actions,.cfnm-toolbar,.cfnm-inline-actions{display:flex;gap:8px;flex-wrap:wrap}
            .cfnm-actions{margin-top:12px}
            .cfnm-btn{border:1px solid #cbd5e1;background:#fff;color:#0f172a;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:700;cursor:pointer}
            .cfnm-btn.primary{background:#0f766e;border-color:#0f766e;color:#fff}
            .cfnm-btn.alt{background:#1d4ed8;border-color:#1d4ed8;color:#fff}
            .cfnm-btn.soft{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
            .cfnm-btn.warn{background:#fff7ed;border-color:#fed7aa;color:#9a3412}
            .cfnm-note-list{max-height:calc(100vh - 290px);overflow:auto}
            .cfnm-note-item{padding:12px 16px;border-top:1px solid #edf2f7;cursor:pointer}
            .cfnm-note-item:first-child{border-top:0}
            .cfnm-note-item:hover{background:#f8fafc}
            .cfnm-note-item.active{background:#e0f2fe}
            .cfnm-note-title{display:flex;align-items:center;justify-content:space-between;gap:8px}
            .cfnm-note-title strong{font-size:13px;color:#0f172a}
            .cfnm-note-item span{display:block;margin-top:5px;color:#64748b;font-size:11px}
            .cfnm-pills,.cfnm-stats{display:flex;gap:8px;flex-wrap:wrap}
            .cfnm-pill{display:inline-flex;align-items:center;justify-content:center;padding:4px 9px;border-radius:999px;font-size:10px;font-weight:800;text-transform:uppercase}
            .cfnm-pill.simple{background:#dbeafe;color:#1d4ed8}
            .cfnm-pill.complex{background:#dcfce7;color:#166534}
            .cfnm-pill.draft{background:#e2e8f0;color:#334155}
            .cfnm-pill.review{background:#ffedd5;color:#9a3412}
            .cfnm-pill.approved{background:#dcfce7;color:#166534}
            .cfnm-pill.manual{background:#fee2e2;color:#b91c1c}
            .cfnm-pill.formula{background:#ede9fe;color:#6d28d9}
            .cfnm-empty{padding:42px 24px;text-align:center;color:#64748b;border:1px dashed #cbd5e1;border-radius:18px;background:rgba(255,255,255,.75)}
            .cfnm-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
            .cfnm-kpi{padding:12px;border:1px solid #e2e8f0;border-radius:14px;background:#f8fafc}
            .cfnm-kpi strong{display:block;font-size:18px;color:#0f172a}
            .cfnm-kpi span{display:block;margin-top:4px;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.04em}
            .cfnm-table-wrap,.cfnm-matrix{overflow:auto;padding:0 16px 16px}
            .cfnm-table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}
            .cfnm-table th,.cfnm-table td{padding:9px 8px;border-bottom:1px solid #edf2f7;vertical-align:top}
            .cfnm-table th{background:#f8fafc;color:#475569;font-size:11px;text-transform:uppercase;font-weight:800}
            .cfnm-code{font-family:Consolas,monospace;font-size:12px;color:#0f172a}
            .cfnm-muted{color:#64748b;font-size:11px}
            .cfnm-matrix table{width:100%;border-collapse:separate;border-spacing:0}
            .cfnm-matrix th,.cfnm-matrix td{border-bottom:1px solid #edf2f7;border-right:1px solid #edf2f7;padding:10px;vertical-align:top}
            .cfnm-matrix th{background:#f8fafc;color:#475569;font-size:11px;text-transform:uppercase;font-weight:800}
            .cfnm-matrix tr th:first-child,.cfnm-matrix tr td:first-child{position:sticky;left:0;background:#fff;z-index:1;min-width:220px}
            .cfnm-cell{display:flex;flex-direction:column;gap:6px;min-width:180px}
            .cfnm-cell.mapped{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:8px}
            .cfnm-cell.manual{background:#fff1f2;border:1px solid #fecdd3;border-radius:12px;padding:8px}
            .cfnm-cell-value{font-weight:800;color:#0f172a}
            .cfnm-cell-meta{font-size:11px;color:#64748b}
            .cfnm-rule-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:0 16px 16px}
            .cfnm-rule-card{border:1px solid #e2e8f0;border-radius:16px;padding:12px;background:#fff}
            .cfnm-rule-card h4{margin:0;font-size:13px;color:#0f172a}
            .cfnm-rule-card p{margin:6px 0 0;color:#64748b;font-size:11px}
            .cfnm-fullscreen{position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;z-index:9999!important;margin:0!important;border-radius:0!important;display:flex;flex-direction:column}
            .cfnm-fullscreen .cfnm-table-wrap,.cfnm-fullscreen .cfnm-matrix{flex:1;max-height:none}
            @media (max-width:1280px){.cfnm-shell{grid-template-columns:1fr}.cfnm-grid.filters,.cfnm-summary-grid,.cfnm-rule-grid{grid-template-columns:1fr}.cfnm-matrix tr th:first-child,.cfnm-matrix tr td:first-child{position:static}}
        `;
        document.head.appendChild(style);
    }

    render_shell() {
        this.wrapper.html(`
            <div class="cfnm-shell">
                <aside class="cfnm-sidebar">
                    <div class="cfnm-head">
                        <h3>${__("Helper de Mapeo de Notas")}</h3>
                        <p>${__("Encuentra destinos, revisa reglas actuales y abre nuevas reglas ya prellenadas.")}</p>
                    </div>
                    <div class="cfnm-section" data-role="filters"></div>
                    <div class="cfnm-section" data-role="summary"></div>
                    <div class="cfnm-note-list" data-role="notes"></div>
                </aside>
                <section class="cfnm-main" data-role="main"></section>
            </div>
        `);
        this.$filters = this.wrapper.find('[data-role="filters"]');
        this.$summary = this.wrapper.find('[data-role="summary"]');
        this.$notes = this.wrapper.find('[data-role="notes"]');
        this.$main = this.wrapper.find('[data-role="main"]');
    }

    bind_events() {
        this.wrapper.on("change", "[data-filter='cliente']", (event) => this.load_bootstrap({ cliente: event.currentTarget.value || null, package_name: null, note_name: null }));
        this.wrapper.on("change", "[data-filter='anio']", (event) => this.load_bootstrap({ anio: this.asInt(event.currentTarget.value, new Date().getFullYear()), package_name: null, note_name: null }));
        this.wrapper.on("change", "[data-filter='mes']", (event) => this.load_bootstrap({ mes: event.currentTarget.value || null, package_name: null, note_name: null }));
        this.wrapper.on("change", "[data-filter='package']", (event) => this.load_bootstrap({ package_name: event.currentTarget.value || null, note_name: null }));
        this.wrapper.on("click", "[data-action='refresh-bootstrap']", () => this.load_bootstrap({}, true));
        this.wrapper.on("click", "[data-action='open-package']", () => this.open_package_form());
        this.wrapper.on("click", "[data-action='open-note-editor']", () => this.open_note_editor());
        this.wrapper.on("click", "[data-action='open-note-form']", () => this.open_note_form());
        this.wrapper.on("click", "[data-action='open-rule-list']", () => this.open_rule_list());
        this.wrapper.on("click", ".cfnm-note-item", (event) => {
            const noteName = event.currentTarget.dataset.noteName;
            if (noteName) this.load_bootstrap({ note_name: noteName });
        });
        this.wrapper.on("click", "[data-action='create-generic-rule']", () => this.create_generic_rule());
        this.wrapper.on("click", "[data-action='run-mapping']", () => this.run_mapping());
        this.wrapper.on("click", "[data-action='create-figure-rule']", (event) => this.create_rule_for_figure(event.currentTarget.dataset.code || ""));
        this.wrapper.on("click", "[data-action='view-figure-rules']", (event) => this.open_rule_list({ destino_tipo: "Cifra Nota", destino_codigo_cifra: event.currentTarget.dataset.code || "" }));
        this.wrapper.on("click", "[data-action='create-cell-rule']", (event) => {
            this.create_rule_for_cell({
                sectionName: event.currentTarget.dataset.sectionName || "",
                sectionCode: event.currentTarget.dataset.sectionCode || "",
                tableCode: event.currentTarget.dataset.tableCode || "",
                rowCode: event.currentTarget.dataset.rowCode || "",
                columnCode: event.currentTarget.dataset.columnCode || "",
                period: event.currentTarget.dataset.period || "Actual",
            });
        });
        this.wrapper.on("click", "[data-action='view-cell-rules']", (event) => {
            this.open_rule_list({
                destino_tipo: "Celda Seccion Nota",
                destino_codigo_seccion: event.currentTarget.dataset.sectionCode || "",
                destino_codigo_tabla: event.currentTarget.dataset.tableCode || "",
                destino_codigo_fila: event.currentTarget.dataset.rowCode || "",
                destino_codigo_columna: event.currentTarget.dataset.columnCode || "",
            });
        });
        this.wrapper.on("click", "[data-action='open-rule']", (event) => {
            const name = event.currentTarget.dataset.ruleName;
            if (name) frappe.set_route("Form", "Regla Mapeo Contable EEFF", name);
        });
        this.wrapper.on("click", "[data-action='edit-rule']", (event) => {
            const name = event.currentTarget.dataset.ruleName;
            if (name) this.open_edit_rule_modal(name);
        });
        this.wrapper.on("click", ".cfnm-toggle-fullscreen", (event) => this.toggle_fullscreen(event));
    }

    load_bootstrap(overrides = {}, force = false) {
        if (this.loading) return;
        const route = this.state.route_options || {};
        const args = {
            cliente: overrides.cliente !== undefined ? overrides.cliente : (route.cliente || this.state.cliente || null),
            anio: overrides.anio !== undefined ? overrides.anio : (route.anio || this.state.anio || null),
            mes: overrides.mes !== undefined ? overrides.mes : (route.mes || this.state.mes || null),
            package_name: overrides.package_name !== undefined ? overrides.package_name : (route.package_name || this.state.package_name || null),
            note_name: overrides.note_name !== undefined ? overrides.note_name : (route.note_name || this.state.note_name || null),
        };
        const bootstrapKey = JSON.stringify(args);
        this.state.route_options = {};
        if (!force && bootstrapKey === this.last_bootstrap_key) return;
        this.loading = true;
        frappe.call({
            method: "mfi_tools.mfi_tools.page.helper_mapeo_notas_eeff.helper_mapeo_notas_eeff.get_mapping_helper_bootstrap",
            args,
            freeze: true,
            freeze_message: __("Cargando helper de mapeo..."),
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
        this.state.note_name = data.note_name || "";
        this.state.clients = data.clients || [];
        this.state.meses = data.meses || [];
        this.state.packages = data.packages || [];
        this.state.notes = data.notes || [];
        this.state.summary = data.summary || null;
        this.state.note = data.note || null;
        this.state.fullscreen_cards = this.state.fullscreen_cards || {};
        const doc = this.get_note_doc();
        if (doc && doc.name) this.state.note_name = doc.name;
    }

    render_all() {
        this.render_filters();
        this.render_summary();
        this.render_notes();
        this.render_main();
    }

    render_filters() {
        this.$filters.html(`
            <div class="cfnm-grid filters">
                <div class="cfnm-field">
                    <label>${__("Cliente")}</label>
                    <select data-filter="cliente"><option value=""></option>${this.options_html(this.state.clients || [], this.state.cliente)}</select>
                </div>
                <div class="cfnm-field">
                    <label>${__("Anio")}</label>
                    <input data-filter="anio" type="number" min="1900" max="2200" value="${this.escape(this.state.anio || new Date().getFullYear())}">
                </div>
                <div class="cfnm-field">
                    <label>${__("Mes")}</label>
                    <select data-filter="mes"><option value=""></option>${this.options_html((this.state.meses || []).map((row) => ({ value: row, label: row })), this.state.mes)}</select>
                </div>
                <div class="cfnm-field">
                    <label>${__("Paquete")}</label>
                    <select data-filter="package"><option value=""></option>${this.options_html(this.state.packages || [], this.state.package_name)}</select>
                </div>
            </div>
            <div class="cfnm-actions">
                <button class="cfnm-btn" data-action="refresh-bootstrap">${__("Refrescar")}</button>
                <button class="cfnm-btn" data-action="open-package">${__("Abrir Paquete")}</button>
                <button class="cfnm-btn" data-action="open-rule-list">${__("Ver Reglas")}</button>
            </div>
        `);
    }

    render_summary() {
        const summary = this.state.summary;
        const doc = this.get_note_doc();
        if (!summary) {
            this.$summary.html(`<div class="cfnm-empty">${__("Selecciona un paquete para cargar notas y destinos de mapeo.")}</div>`);
            return;
        }

        this.$summary.html(`
            <div class="cfnm-head" style="padding:0 0 12px 0;border:none;">
                <h3>${__("Contexto Activo")}</h3>
                <p>${this.escape(summary.package_name || "-")}</p>
            </div>
            <div class="cfnm-pills">
                <span class="cfnm-pill ${doc && doc.estructura_nota === "Compleja" ? "complex" : "simple"}">${this.escape(doc ? (doc.estructura_nota || "Simple") : __("Sin nota"))}</span>
                <span class="cfnm-pill draft">${this.escape(summary.estado_preparacion || "Borrador")}</span>
            </div>
            <div class="cfnm-stats" style="margin-top:12px;">
                <div><strong>${this.escape(summary.total_notas || 0)}</strong><div class="cfnm-muted">${__("Notas")}</div></div>
                <div><strong>${this.escape(summary.total_notas_complejas || 0)}</strong><div class="cfnm-muted">${__("Complejas")}</div></div>
                <div><strong>${this.escape(summary.reglas_notas_activas || 0)}</strong><div class="cfnm-muted">${__("Reglas")}</div></div>
            </div>
        `);
    }

    render_notes() {
        if (!this.state.package_name) {
            this.$notes.html(`<div class="cfnm-empty">${__("No hay paquete seleccionado.")}</div>`);
            return;
        }
        if (!this.state.notes.length) {
            this.$notes.html(`<div class="cfnm-empty">${__("El paquete no tiene notas registradas.")}</div>`);
            return;
        }

        const currentName = this.state.note_name || (this.get_note_doc() || {}).name;
        this.$notes.html((this.state.notes || []).map((note) => `
            <div class="cfnm-note-item ${note.name === currentName ? "active" : ""}" data-note-name="${this.escape(note.name)}">
                <div class="cfnm-note-title">
                    <strong>${this.escape(note.identificador_nota || note.numero_nota || note.name)}</strong>
                    <span class="cfnm-pill ${note.estructura_nota === "Compleja" ? "complex" : "simple"}">${this.escape(note.estructura_nota || "Simple")}</span>
                </div>
                <span>${this.escape(note.titulo || __("Sin titulo"))}</span>
                <span>${__("Cifras: {0} | Secciones: {1}", [note.total_cifras || 0, note.total_secciones_complejas || 0])}</span>
            </div>
        `).join(""));
    }

    render_main() {
        const summary = this.state.summary;
        const note = this.state.note;
        const doc = this.get_note_doc();
        if (!summary) {
            this.state.fullscreen_cards = {};
            this.sync_body_scroll();
            this.$main.html(`<div class="cfnm-empty">${__("Filtra por cliente, periodo y paquete para empezar.")}</div>`);
            return;
        }
        if (!note || !doc) {
            this.state.fullscreen_cards = {};
            this.sync_body_scroll();
            this.$main.html(`<div class="cfnm-empty">${__("Selecciona una nota para ver sus cifras, secciones y reglas de mapeo.")}</div>`);
            return;
        }

        this.$main.html(`
            ${this.render_note_header(doc, note.stats || {})}
            ${this.render_figures_card(note.figures || [])}
            ${doc.estructura_nota === "Compleja" ? this.render_sections_card(note.sections || []) : ""}
            ${this.render_rules_card(note.rules || [])}
        `);
        this.sync_body_scroll();
    }

    render_note_header(doc, stats) {
        return `
            <div class="cfnm-card">
                <div class="cfnm-head">
                    <h3>${__("Nota {0}", [this.escape(doc.identificador_nota || "-")])}</h3>
                    <p>${this.escape(doc.titulo || __("Sin titulo"))}</p>
                </div>
                <div class="cfnm-section">
                    <div class="cfnm-pills">
                        <span class="cfnm-pill ${doc.estructura_nota === "Compleja" ? "complex" : "simple"}">${this.escape(doc.estructura_nota || "Simple")}</span>
                        <span class="cfnm-pill ${this.approval_pill_class(doc.estado_aprobacion)}">${this.escape(doc.estado_aprobacion || "Borrador")}</span>
                    </div>
                    <div class="cfnm-summary-grid" style="margin-top:14px;">
                        ${this.kpi_html(stats.total_reglas || 0, __("Reglas de Nota"))}
                        ${this.kpi_html(stats.reglas_activas || 0, __("Reglas Activas"))}
                        ${this.kpi_html(stats.cifras_con_regla || 0, __("Cifras con Regla"))}
                        ${this.kpi_html(stats.celdas_con_regla || 0, __("Celdas con Regla"))}
                    </div>
                    <div class="cfnm-actions" style="margin-top:14px;">
                        <button class="cfnm-btn primary" data-action="run-mapping">${__("Ejecutar Mapeo")}</button>
                        <button class="cfnm-btn alt" data-action="create-generic-rule">${__("Nueva Regla")}</button>
                        <button class="cfnm-btn" data-action="open-note-form">${__("Abrir Nota")}</button>
                        <button class="cfnm-btn" data-action="open-note-editor">${__("Abrir Editor")}</button>
                    </div>
                </div>
            </div>
        `;
    }

    render_figures_card(figures) {
        const isExpanded = this.is_fullscreen_card("mapped_figures");
        return `
            <div class="cfnm-card ${isExpanded ? "cfnm-fullscreen" : ""}" data-fullscreen-key="mapped_figures">
                <div class="cfnm-head">
                    <h3>${__("Cifras Mapeables")}</h3>
                    <p>${__("Usa esta tabla para ubicar rapido el codigo destino de cada cifra y abrir la regla ya prellenada.")}</p>
                </div>
                <div class="cfnm-toolbar" style="padding:12px 16px 0;">
                    <button class="cfnm-btn cfnm-toggle-fullscreen" style="margin-left:auto;">${isExpanded ? __("Contraer") : __("Expandir")}</button>
                </div>
                <div class="cfnm-table-wrap">
                    <table class="cfnm-table">
                        <thead>
                            <tr>
                                <th>${__("Codigo")}</th>
                                <th>${__("Concepto")}</th>
                                <th>${__("Actual")}</th>
                                <th>${__("Comparativo")}</th>
                                <th>${__("Origen")}</th>
                                <th>${__("Reglas")}</th>
                                <th>${__("Acciones")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${figures.length ? figures.map((row) => {
                                const isMappable = !this.asInt(row.es_titulo) && !this.asInt(row.es_linea_blanco) && !this.asInt(row.es_manual);
                                const isFormula = this.asInt(row.calculo_automatico) || String(row.origen_dato || "").trim().toLowerCase() === "formula";
                                const firstRule = Array.isArray(row.rules) && row.rules.length ? row.rules[0] : null;
                                return `
                                    <tr>
                                        <td>
                                            <div class="cfnm-code">${this.escape(row.codigo_cifra || "-")}</div>
                                            ${this.figure_flags_html(row)}
                                        </td>
                                        <td>${this.escape(row.concepto || "-")}</td>
                                        <td>${this.escape(row.display_actual || "-")}</td>
                                        <td>${this.escape(row.display_comparativo || "-")}</td>
                                        <td>${this.escape(row.origen_dato || "-")}</td>
                                        <td>${this.escape(row.rules_count || 0)}</td>
                                        <td>
                                            ${isFormula
                                                ? `<div class="cfnm-muted">${__("Sin acciones")}</div>`
                                                : `<div class="cfnm-inline-actions">
                                                    ${firstRule
                                                        ? `<button class="cfnm-btn soft" data-action="edit-rule" data-rule-name="${this.escape(firstRule.name || "")}" ${isMappable ? "" : "disabled"}>${__("Editar")}</button>`
                                                        : `<button class="cfnm-btn soft" data-action="create-figure-rule" data-code="${this.escape(row.codigo_cifra || "")}" ${isMappable ? "" : "disabled"}>${__("Crear")}</button>`
                                                    }
                                                    <button class="cfnm-btn" data-action="view-figure-rules" data-code="${this.escape(row.codigo_cifra || "")}" ${this.asInt(row.rules_count) ? "" : "disabled"}>${__("Ver")}</button>
                                                </div>`
                                            }
                                        </td>
                                    </tr>
                                `;
                            }).join("") : `<tr><td colspan="7">${__("La nota no tiene cifras registradas.")}</td></tr>`}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    render_sections_card(sections) {
        if (!sections.length) {
            return `
                <div class="cfnm-card">
                    <div class="cfnm-head">
                        <h3>${__("Secciones Complejas")}</h3>
                        <p>${__("La nota esta marcada como compleja, pero aun no tiene secciones para mapear.")}</p>
                    </div>
                    <div class="cfnm-section"><div class="cfnm-empty">${__("Agrega secciones en la nota o en el editor de notas.")}</div></div>
                </div>
            `;
        }

        return sections.map((section) => {
            const cardKey = `section_${section.name || section.codigo_seccion || "section"}`;
            const isExpanded = this.is_fullscreen_card(cardKey);
            return `
            <div class="cfnm-card ${isExpanded ? "cfnm-fullscreen" : ""}" data-fullscreen-key="${this.escape(cardKey)}">
                <div class="cfnm-head">
                    <h3>${__("Seccion {0}", [this.escape(section.codigo_seccion || "-")])}</h3>
                    <p>${this.escape(section.titulo_seccion || __("Sin titulo"))}</p>
                </div>
                <div class="cfnm-section">
                    <div class="cfnm-pills">
                        <span class="cfnm-pill ${section.tipo_seccion === "Tabla" ? "complex" : "simple"}">${this.escape(section.tipo_seccion || "Narrativa")}</span>
                        <span class="cfnm-pill draft">${__("Tablas {0}", [this.asInt((section.tables || []).length)])}</span>
                        <span class="cfnm-pill draft">${__("Celdas {0}", [this.asInt(section.total_celdas || 0)])}</span>
                    </div>
                </div>
                <div class="cfnm-toolbar" style="padding:0 16px 12px;">
                    <button class="cfnm-btn cfnm-toggle-fullscreen" style="margin-left:auto;">${isExpanded ? __("Contraer") : __("Expandir")}</button>
                </div>
                ${(section.tables || []).map((table) => this.render_section_table(section, table)).join("")}
            </div>
        `;
        }).join("");
    }

    render_section_table(section, table) {
        const columns = table.columnas || [];
        const rows = table.filas || [];
        return `
            <div class="cfnm-head" style="border-top:1px solid #edf2f7;">
                <h3>${__("Tabla {0}", [this.escape(table.codigo_tabla || "-")])}</h3>
                <p>${__("Filas: {0} | Columnas: {1}", [rows.length, columns.length])}</p>
            </div>
            <div class="cfnm-matrix">
                <table>
                    <thead>
                        <tr>
                            <th>${__("Fila / Columna")}</th>
                            ${columns.map((column) => `<th><div class="cfnm-code">${this.escape(column.codigo_columna || "-")}</div><div class="cfnm-muted">${this.escape(column.etiqueta || "-")}</div></th>`).join("")}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.length ? rows.map((row) => `
                            <tr>
                                <td>
                                    <div class="cfnm-code">${this.escape(row.codigo_fila || "-")}</div>
                                    <div>${this.escape(row.descripcion || "-")}</div>
                                    <div class="cfnm-muted">${this.escape(row.tipo_fila || "Detalle")}</div>
                                </td>
                                ${(row.celdas || []).map((cell) => {
                                    const isMappable = !this.asInt(cell.es_manual) && row.tipo_fila !== "Titulo";
                                    const firstRule = Array.isArray(cell.rules) && cell.rules.length ? cell.rules[0] : null;
                                    return `
                                        <td>
                                            <div class="cfnm-cell ${this.asInt(cell.rules_count) ? "mapped" : ""} ${this.asInt(cell.es_manual) ? "manual" : ""}">
                                                <div class="cfnm-cell-value">${this.escape(cell.display_value || "-")}</div>
                                                <div class="cfnm-cell-meta">
                                                    ${this.escape(cell.formato_numero || "Numero")} | ${this.escape(cell.origen_dato || "Manual")}
                                                    ${cell.ultima_regla_mapeo ? `| ${__("Ultima")}: ${this.escape(cell.ultima_regla_mapeo)}` : ""}
                                                </div>
                                                <div class="cfnm-inline-actions">
                                                    ${firstRule
                                                        ? `<button class="cfnm-btn soft" data-action="edit-rule" data-rule-name="${this.escape(firstRule.name || "")}" ${isMappable ? "" : "disabled"}>${__("Editar")}</button>`
                                                        : `<button class="cfnm-btn soft" data-action="create-cell-rule" data-section-name="${this.escape(section.name)}" data-section-code="${this.escape(section.codigo_seccion || "")}" data-table-code="${this.escape(table.codigo_tabla || "")}" data-row-code="${this.escape(row.codigo_fila || "")}" data-column-code="${this.escape(cell.codigo_columna || "")}" ${isMappable ? "" : "disabled"}>${__("Crear")}</button>`
                                                    }
                                                    <button class="cfnm-btn" data-action="view-cell-rules" data-section-code="${this.escape(section.codigo_seccion || "")}" data-table-code="${this.escape(table.codigo_tabla || "")}" data-row-code="${this.escape(row.codigo_fila || "")}" data-column-code="${this.escape(cell.codigo_columna || "")}" ${this.asInt(cell.rules_count) ? "" : "disabled"}>${__("Ver")}</button>
                                                </div>
                                            </div>
                                        </td>
                                    `;
                                }).join("")}
                            </tr>
                        `).join("") : `<tr><td colspan="${columns.length + 1}">${__("La tabla no tiene estructura registrada.")}</td></tr>`}
                    </tbody>
                </table>
            </div>
        `;
    }

    render_rules_card(rules) {
        return `
            <div class="cfnm-card">
                <div class="cfnm-head">
                    <h3>${__("Reglas de la Nota")}</h3>
                    <p>${__("Revisa rapidamente que ya esta mapeado y abre la regla exacta cuando necesites ajustarla.")}</p>
                </div>
                <div class="cfnm-rule-grid">
                    ${rules.length ? rules.map((rule) => `
                        <div class="cfnm-rule-card">
                            <h4>${this.escape(rule.name || "-")}</h4>
                            <p>${this.escape(rule.destino_tipo || "-")} | ${this.escape(rule.target_label || "-")}</p>
                            <p>${__("Fuente")}: ${this.escape(rule.fuente_tipo || "-")}${this.build_rule_period_summary(rule)}</p>
                            <div class="cfnm-inline-actions" style="margin-top:10px;">
                                <span class="cfnm-pill ${this.asInt(rule.activo) ? "complex" : "draft"}">${this.asInt(rule.activo) ? __("Activa") : __("Inactiva")}</span>
                                <button class="cfnm-btn soft" data-action="edit-rule" data-rule-name="${this.escape(rule.name || "")}">${__("Editar")}</button>
                                <button class="cfnm-btn" data-action="open-rule" data-rule-name="${this.escape(rule.name || "")}">${__("Abrir")}</button>
                            </div>
                        </div>
                    `).join("") : `<div class="cfnm-empty">${__("La nota aun no tiene reglas de mapeo vinculadas.")}</div>`}
                </div>
            </div>
        `;
    }

    figure_flags_html(row) {
        const flags = [];
        if (this.asInt(row.es_titulo)) flags.push(`<span class="cfnm-pill draft">${__("Titulo")}</span>`);
        if (this.asInt(row.es_linea_blanco)) flags.push(`<span class="cfnm-pill draft">${__("Blanco")}</span>`);
        if (this.asInt(row.es_manual)) flags.push(`<span class="cfnm-pill manual">${__("Manual")}</span>`);
        if (this.asInt(row.calculo_automatico)) flags.push(`<span class="cfnm-pill formula">${__("Formula")}</span>`);
        return flags.length ? `<div class="cfnm-pills" style="margin-top:8px;">${flags.join("")}</div>` : "";
    }

    approval_pill_class(value) {
        const current = String(value || "").toLowerCase();
        if (current.includes("aprob")) return "approved";
        if (current.includes("revis")) return "review";
        return "draft";
    }

    kpi_html(value, label) {
        return `<div class="cfnm-kpi"><strong>${this.escape(value)}</strong><span>${this.escape(label)}</span></div>`;
    }

    build_default_account_row() {
        return {
            cuenta: "",
            campo_balanza: "codigo_cuenta",
            operacion: "+",
            porcentaje: 100,
            centro_costo: "",
            comentario: "",
        };
    }

    get_figure_period_options() {
        return "Actual\nComparativo\nSaldo Anterior Actual\nMovimiento Mes Actual\nSaldo Anterior Comparativo\nMovimiento Mes Comparativo\nYTD Actual\nYTD Comparativo\nYTD Año Anterior Actual\nYTD Año Anterior Comparativo";
    }

    get_cell_period_options() {
        return "Actual\nComparativo\nBase Actual\nBase Comparativo\nSaldo Anterior Actual\nMovimiento Mes Actual\nSaldo Anterior Comparativo\nMovimiento Mes Comparativo\nYTD Actual\nYTD Comparativo\nYTD Año Anterior Actual\nYTD Año Anterior Comparativo";
    }

    build_rule_period_summary(rule) {
        if (rule.destino_tipo === "Celda Seccion Nota") {
            return ` | ${__("Periodo")}: ${this.escape(rule.destino_periodo_celda || "Actual")}`;
        }
        if (rule.destino_tipo === "Cifra Nota" && this.asInt(rule.usar_periodos_especiales_cifra)) {
            return ` | ${__("Actual")}: ${this.escape(rule.destino_periodo_cifra_actual || "Actual")} | ${__("Comp")}: ${this.escape(rule.destino_periodo_cifra_comparativo || "Comparativo")}`;
        }
        return "";
    }

    build_rule_target_html(config) {
        const ruleName = config.name || config.nombre_regla || "";
        const nameLabel = ruleName
            ? `<strong>${__("Nombre Regla")}:</strong> ${this.escape(ruleName)}<br>`
            : `<strong>${__("Nombre Regla")}:</strong> ${__("Se generara al guardar")}<br>`;
        const destinoTipo = config.destino_tipo || "Cifra Nota";
        if (destinoTipo === "Celda Seccion Nota") {
            return `
                <div class="cfnm-muted">
                    ${nameLabel}
                    <strong>${__("Nota")}:</strong> ${this.escape(config.noteLabel || this.state.note_name || "-")}<br>
                    <strong>${__("Seccion")}:</strong> ${this.escape(config.destino_codigo_seccion || "-")}<br>
                    <strong>${__("Tabla")}:</strong> ${this.escape(config.destino_codigo_tabla || "-")}<br>
                    <strong>${__("Fila")}:</strong> ${this.escape(config.destino_codigo_fila || "-")}<br>
                    <strong>${__("Columna")}:</strong> ${this.escape(config.destino_codigo_columna || "-")}
                </div>
            `;
        }

        return `
            <div class="cfnm-muted">
                ${nameLabel}
                <strong>${__("Nota")}:</strong> ${this.escape(config.noteLabel || this.state.note_name || "-")}<br>
                <strong>${__("Codigo Cifra")}:</strong> ${this.escape(config.destino_codigo_cifra || "-")}
            </div>
        `;
    }

    get_dialog_account_rows(dialog) {
        const grid = dialog.fields_dict.cuentas && dialog.fields_dict.cuentas.grid;
        const rows = grid && typeof grid.get_data === "function" ? grid.get_data() : (dialog.get_value("cuentas") || []);
        return (rows || []).map((row) => ({
            cuenta: String(row.cuenta || "").trim(),
            campo_balanza: String(row.campo_balanza || "codigo_cuenta").trim() || "codigo_cuenta",
            operacion: String(row.operacion || "+").trim() || "+",
            porcentaje: row.porcentaje === "" || row.porcentaje == null ? 100 : row.porcentaje,
            centro_costo: String(row.centro_costo || "").trim(),
            comentario: String(row.comentario || "").trim(),
        })).filter((row) => row.cuenta);
    }

    open_rule_modal(config = {}) {
        const noteName = config.noteName || this.state.note_name;
        if (!noteName) {
            frappe.msgprint(__("Selecciona una nota antes de crear o editar reglas."));
            return;
        }

        const initialAccounts = Array.isArray(config.cuentas) && config.cuentas.length
            ? config.cuentas.map((row) => ({ ...this.build_default_account_row(), ...row }))
            : [this.build_default_account_row()];
        const isCell = config.destino_tipo === "Celda Seccion Nota";
        const isFigure = config.destino_tipo === "Cifra Nota";
        const editableFigureCode = !!config.editableFigureCode && isFigure;
        let dialog = null;
        const refreshFigurePeriodFields = () => {
            if (!dialog || !isFigure) return;
            const setFieldVisibility = (fieldname, visible) => {
                const field = dialog.fields_dict[fieldname];
                if (!field) return;
                field.df.hidden = visible ? 0 : 1;
                if (field.$wrapper) field.$wrapper.toggle(!!visible);
                if (typeof field.refresh === "function") field.refresh();
            };
            const sourceType = String(dialog.get_value("fuente_tipo") || "Balanza").trim() || "Balanza";
            const allowSpecialPeriods = sourceType === "Balanza";
            if (!allowSpecialPeriods && this.asInt(dialog.get_value("usar_periodos_especiales_cifra"))) {
                dialog.set_value("usar_periodos_especiales_cifra", 0);
                return;
            }
            const enabled = allowSpecialPeriods && this.asInt(dialog.get_value("usar_periodos_especiales_cifra"));
            setFieldVisibility("destino_periodo_cifra_actual", enabled);
            setFieldVisibility("destino_periodo_cifra_comparativo", enabled);
        };

        dialog = new frappe.ui.Dialog({
            title: config.title || __("Regla de Mapeo"),
            size: "extra-large",
            fields: [
                {
                    fieldtype: "HTML",
                    fieldname: "target_info",
                    options: `<div style="padding:8px 0 4px;">${this.build_rule_target_html(config)}</div>`,
                },
                {
                    fieldtype: "Column Break",
                },
                {
                    fieldtype: "Check",
                    fieldname: "activo",
                    label: __("Activa"),
                    default: this.asInt(config.activo, 1),
                },
                {
                    fieldtype: "Int",
                    fieldname: "orden",
                    label: __("Orden"),
                    default: this.asInt(config.orden, 0),
                },
                {
                    fieldtype: "Section Break",
                    label: __("Configuracion"),
                },
                {
                    fieldtype: "Select",
                    fieldname: "fuente_tipo",
                    label: __("Fuente Tipo"),
                    options: "Balanza\nDato Estadistico",
                    default: config.fuente_tipo || "Balanza",
                    reqd: 1,
                    change: () => refreshFigurePeriodFields(),
                },
                editableFigureCode
                    ? {
                        fieldtype: "Data",
                        fieldname: "destino_codigo_cifra",
                        label: __("Codigo Cifra"),
                        default: config.destino_codigo_cifra || "",
                        reqd: 1,
                    }
                    : {
                        fieldtype: "Data",
                        fieldname: "destino_codigo_cifra",
                        hidden: 1,
                        default: config.destino_codigo_cifra || "",
                    },
                isFigure
                    ? {
                        fieldtype: "Check",
                        fieldname: "usar_periodos_especiales_cifra",
                        label: __("Habilitar periodos especiales"),
                        description: __("Solo para casos especiales cuando la fuente es Balanza."),
                        default: this.asInt(config.usar_periodos_especiales_cifra, 0),
                        change: () => refreshFigurePeriodFields(),
                    }
                    : {
                        fieldtype: "Data",
                        fieldname: "usar_periodos_especiales_cifra",
                        hidden: 1,
                        default: 0,
                    },
                isFigure
                    ? {
                        fieldtype: "Select",
                        fieldname: "destino_periodo_cifra_actual",
                        label: __("Valor para columna Actual"),
                        options: this.get_figure_period_options(),
                        default: config.destino_periodo_cifra_actual || "Actual",
                    }
                    : {
                        fieldtype: "Data",
                        fieldname: "destino_periodo_cifra_actual",
                        hidden: 1,
                        default: "Actual",
                    },
                isFigure
                    ? {
                        fieldtype: "Select",
                        fieldname: "destino_periodo_cifra_comparativo",
                        label: __("Valor para columna Comparativo"),
                        options: this.get_figure_period_options(),
                        default: config.destino_periodo_cifra_comparativo || "Comparativo",
                    }
                    : {
                        fieldtype: "Data",
                        fieldname: "destino_periodo_cifra_comparativo",
                        hidden: 1,
                        default: "Comparativo",
                    },
                isCell
                    ? {
                        fieldtype: "Select",
                        fieldname: "destino_periodo_celda",
                        label: __("Periodo Valor Celda"),
                        options: this.get_cell_period_options(),
                        default: config.destino_periodo_celda || "Actual",
                        reqd: 1,
                    }
                    : {
                        fieldtype: "Data",
                        fieldname: "destino_periodo_celda",
                        hidden: 1,
                        default: config.destino_periodo_celda || "Actual",
                    },
                {
                    fieldtype: "Section Break",
                    label: __("Observaciones"),
                },
                {
                    fieldtype: "Small Text",
                    fieldname: "observaciones",
                    label: __("Observaciones"),
                    default: config.observaciones || "",
                },
                {
                    fieldtype: "Section Break",
                    label: __("Cuentas / Origenes"),
                },
                {
                    fieldtype: "Table",
                    fieldname: "cuentas",
                    label: __("Cuentas"),
                    cannot_add_rows: false,
                    in_place_edit: true,
                    reqd: 1,
                    data: initialAccounts,
                    fields: [
                        { fieldtype: "Data", fieldname: "cuenta", label: __("Cuenta"), in_list_view: 1, reqd: 1 },
                        { fieldtype: "Select", fieldname: "campo_balanza", label: __("Campo"), options: "codigo_cuenta\ndescripcion_cuenta", default: "codigo_cuenta", in_list_view: 1 },
                        { fieldtype: "Select", fieldname: "operacion", label: __("Operacion"), options: "+\n-", default: "+", in_list_view: 1 },
                        { fieldtype: "Percent", fieldname: "porcentaje", label: __("Porcentaje"), default: 100, in_list_view: 1 },
                        { fieldtype: "Data", fieldname: "centro_costo", label: __("Centro Costo") },
                        { fieldtype: "Small Text", fieldname: "comentario", label: __("Comentario") },
                    ],
                },
            ],
            primary_action_label: config.name ? __("Guardar Regla") : __("Crear Regla"),
            primary_action: (values) => {
                const cuentas = this.get_dialog_account_rows(dialog);
                if (!cuentas.length) {
                    frappe.msgprint(__("Agrega al menos una cuenta o codigo origen antes de guardar."));
                    return;
                }

                const payload = {
                    name: config.name || "",
                    activo: values.activo ? 1 : 0,
                    orden: this.asInt(values.orden, 0),
                    fuente_tipo: values.fuente_tipo || "Balanza",
                    observaciones: values.observaciones || "",
                    destino_tipo: config.destino_tipo || "Cifra Nota",
                    destino_codigo_cifra: editableFigureCode ? (values.destino_codigo_cifra || "") : (config.destino_codigo_cifra || ""),
                    seccion_nota_eeff: config.seccion_nota_eeff || "",
                    destino_codigo_seccion: config.destino_codigo_seccion || "",
                    destino_codigo_tabla: config.destino_codigo_tabla || "",
                    destino_codigo_fila: config.destino_codigo_fila || "",
                    destino_codigo_columna: config.destino_codigo_columna || "",
                    usar_periodos_especiales_cifra: isFigure && values.usar_periodos_especiales_cifra ? 1 : 0,
                    destino_periodo_cifra_actual: isFigure && values.usar_periodos_especiales_cifra
                        ? (values.destino_periodo_cifra_actual || "Actual")
                        : "Actual",
                    destino_periodo_cifra_comparativo: isFigure && values.usar_periodos_especiales_cifra
                        ? (values.destino_periodo_cifra_comparativo || "Comparativo")
                        : "Comparativo",
                    destino_periodo_celda: isCell ? (values.destino_periodo_celda || "Actual") : "Actual",
                    cuentas,
                };

                frappe.call({
                    method: "mfi_tools.mfi_tools.page.helper_mapeo_notas_eeff.helper_mapeo_notas_eeff.save_mapping_rule_from_helper",
                    args: {
                        note_name: noteName,
                        rule_payload: payload,
                    },
                    freeze: true,
                    freeze_message: config.name ? __("Guardando regla...") : __("Creando regla..."),
                    callback: () => {
                        dialog.hide();
                        frappe.show_alert({
                            message: config.name ? __("Regla actualizada.") : __("Regla creada."),
                            indicator: "green",
                        });
                        this.load_bootstrap({}, true);
                    },
                });
            },
        });

        dialog.show();
        if (isFigure) {
            const specialField = dialog.fields_dict.usar_periodos_especiales_cifra;
            const sourceField = dialog.fields_dict.fuente_tipo;
            if (specialField && specialField.$wrapper) {
                specialField.$wrapper.find("input, select").on("change", () => refreshFigurePeriodFields());
            }
            if (sourceField && sourceField.$wrapper) {
                sourceField.$wrapper.find("input, select").on("change", () => refreshFigurePeriodFields());
            }
        }
        refreshFigurePeriodFields();
        const grid = dialog.fields_dict.cuentas && dialog.fields_dict.cuentas.grid;
        if (grid) {
            grid.refresh();
        }
    }

    open_edit_rule_modal(ruleName) {
        frappe.call({
            method: "mfi_tools.mfi_tools.page.helper_mapeo_notas_eeff.helper_mapeo_notas_eeff.get_mapping_rule_detail",
            args: { rule_name: ruleName },
            freeze: true,
            freeze_message: __("Cargando regla..."),
            callback: (r) => {
                const rule = r.message || {};
                this.open_rule_modal({
                    ...rule,
                    title: __("Editar Regla {0}", [rule.name || ruleName]),
                    noteName: rule.nota_eeff || this.state.note_name,
                    noteLabel: this.get_note_doc() ? (this.get_note_doc().identificador_nota || this.get_note_doc().name) : this.state.note_name,
                    editableFigureCode: false,
                });
            },
        });
    }

    toggle_fullscreen(event) {
        const $card = $(event.currentTarget).closest("[data-fullscreen-key]");
        const key = String($card.data("fullscreenKey") || "").trim();
        $card.toggleClass("cfnm-fullscreen");
        const isFull = $card.hasClass("cfnm-fullscreen");
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
        const hasDomFullscreen = $(".cfnm-fullscreen").length > 0;
        document.body.style.overflow = hasStateFullscreen || hasDomFullscreen ? "hidden" : "";
    }

    run_mapping() {
        if (!this.state.package_name) {
            frappe.msgprint(__("Selecciona un paquete antes de ejecutar el mapeo."));
            return;
        }

        frappe.call({
            method: "mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.ejecutar_mapeo",
            args: { paquete_name: this.state.package_name },
            freeze: true,
            freeze_message: __("Ejecutando mapeo del paquete actual..."),
            callback: (r) => {
                const result = r.message || {};
                const alertas = Array.isArray(result.alertas) ? result.alertas : [];
                frappe.show_alert({
                    message: __("Mapeo ejecutado para {0}", [this.state.package_name]),
                    indicator: alertas.length ? "orange" : "green",
                });
                if (alertas.length) {
                    frappe.msgprint({
                        title: __("Mapeo con Alertas"),
                        indicator: "orange",
                        message: alertas.slice(0, 10).join("<br>"),
                    });
                }
                this.load_bootstrap({}, true);
            },
        });
    }

    create_generic_rule() {
        const doc = this.get_note_doc();
        if (!this.state.package_name) {
            frappe.msgprint(__("Selecciona un paquete antes de crear una regla."));
            return;
        }
        this.open_rule_modal({
            title: __("Nueva Regla de Nota"),
            noteName: doc ? doc.name : this.state.note_name,
            destino_tipo: "Cifra Nota",
            destino_codigo_cifra: "",
            editableFigureCode: true,
            activo: 1,
            fuente_tipo: "Balanza",
            cuentas: [this.build_default_account_row()],
        });
    }

    create_rule_for_figure(code) {
        const doc = this.get_note_doc();
        if (!doc || !code) return;
        this.open_rule_modal({
            title: __("Mapear Cifra {0}", [code]),
            noteName: doc.name,
            noteLabel: doc.identificador_nota || doc.name,
            destino_tipo: "Cifra Nota",
            destino_codigo_cifra: code,
            activo: 1,
            fuente_tipo: "Balanza",
            cuentas: [this.build_default_account_row()],
        });
    }

    create_rule_for_cell({ sectionName, sectionCode, tableCode, rowCode, columnCode, period }) {
        const doc = this.get_note_doc();
        if (!doc || !sectionName || !sectionCode || !tableCode || !rowCode || !columnCode) return;
        this.open_rule_modal({
            title: __("Mapear Celda {0}/{1}/{2}", [tableCode, rowCode, columnCode]),
            noteName: doc.name,
            noteLabel: doc.identificador_nota || doc.name,
            destino_tipo: "Celda Seccion Nota",
            seccion_nota_eeff: sectionName,
            destino_codigo_seccion: sectionCode,
            destino_codigo_tabla: tableCode,
            destino_codigo_fila: rowCode,
            destino_codigo_columna: columnCode,
            destino_periodo_celda: period || "Actual",
            activo: 1,
            fuente_tipo: "Balanza",
            cuentas: [this.build_default_account_row()],
        });
    }

    open_package_form() {
        if (!this.state.package_name) {
            frappe.msgprint(__("No hay paquete seleccionado."));
            return;
        }
        frappe.set_route("Form", "Paquete EEFF", this.state.package_name);
    }

    open_note_form() {
        const doc = this.get_note_doc();
        if (!doc || !doc.name) {
            frappe.msgprint(__("No hay nota seleccionada."));
            return;
        }
        frappe.set_route("Form", "Nota EEFF", doc.name);
    }

    open_note_editor() {
        const doc = this.get_note_doc();
        frappe.route_options = {
            cliente: this.state.cliente || "",
            anio: this.state.anio || "",
            mes: this.state.mes || "",
            package_name: this.state.package_name || "",
            note_name: doc ? doc.name : "",
        };
        frappe.set_route("asistente-notas-eeff");
    }

    open_rule_list(extraFilters = {}) {
        const doc = this.get_note_doc();
        const filters = {
            destino_numero_nota: doc ? (doc.identificador_nota || doc.numero_nota || undefined) : undefined,
            ...extraFilters,
        };
        Object.keys(filters).forEach((key) => {
            if (filters[key] === undefined || filters[key] === null || filters[key] === "") {
                delete filters[key];
            }
        });
        frappe.set_route("List", "Regla Mapeo Contable EEFF", filters);
    }

    get_note_doc() {
        return this.state.note && this.state.note.doc ? this.state.note.doc : null;
    }

    options_html(options, selectedValue) {
        return (options || []).map((option) => {
            const value = option && option.value !== undefined ? option.value : "";
            const label = option && option.label !== undefined ? option.label : value;
            return `<option value="${this.escape(value)}" ${String(value) === String(selectedValue || "") ? "selected" : ""}>${this.escape(label)}</option>`;
        }).join("");
    }

    asInt(value, fallback = 0) {
        if (typeof value === "boolean") {
            return value ? 1 : 0;
        }
        if (typeof value === "number" && Number.isFinite(value)) {
            return Math.trunc(value);
        }
        const parsed = parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    escape(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }
}
