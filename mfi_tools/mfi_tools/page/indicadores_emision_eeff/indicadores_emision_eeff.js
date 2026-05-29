frappe.pages["indicadores-emision-eeff"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Indicadores de Emision EEFF",
        single_column: true,
    });

    frappe.pages["indicadores-emision-eeff"].indicatorPage = new IndicadoresEmisionEEFF(page);
    frappe.pages["indicadores-emision-eeff"].indicatorPage.init();
};

frappe.pages["indicadores-emision-eeff"].on_page_show = function () {
    const controller = frappe.pages["indicadores-emision-eeff"].indicatorPage;
    if (!controller) return;
    controller.apply_route_options();
    controller.load_bootstrap();
};

class IndicadoresEmisionEEFF {
    constructor(page) {
        this.page = page;
        this.wrapper = page.main;
        this.state = {
            cliente: "",
            anio: new Date().getFullYear(),
            mes: "",
            paquete_name: "",
            clients: [],
            packages: [],
            meses: [],
            indicators: null,
            route_options: {},
        };
        this.loading = false;
    }

    init() {
        this.setup_styles();
        this.render_shell();
        this.bind_events();
        this.page.set_primary_action(__("Evaluar Indicadores"), () => this.run_indicators(), "play");
    }

    apply_route_options() {
        this.state.route_options = frappe.route_options || {};
        frappe.route_options = null;
    }

    setup_styles() {
        if (document.getElementById("cf-indicator-style")) return;
        const style = document.createElement("style");
        style.id = "cf-indicator-style";
        style.textContent = `
            .cfi-shell{display:grid;grid-template-columns:1fr;gap:14px;padding:16px;border:1px solid #dbe4ee;border-radius:16px;background:linear-gradient(170deg,#f8fbff 0%,#f4f8ff 50%,#fffdf7 100%)}
            .cfi-card{background:#fff;border:1px solid #dbe4ee;border-radius:14px;box-shadow:0 8px 20px rgba(15,23,42,.05)}
            .cfi-head{padding:14px 16px;border-bottom:1px solid #eef2f7}
            .cfi-head h3{margin:0;color:#0f172a;font-size:15px;font-weight:800}
            .cfi-head p{margin:6px 0 0;color:#64748b;font-size:12px}
            .cfi-body{padding:14px 16px}
            .cfi-grid{display:grid;gap:10px}
            .cfi-grid.filters{grid-template-columns:repeat(4,minmax(0,1fr))}
            .cfi-field{display:flex;flex-direction:column;gap:6px}
            .cfi-field label{font-size:11px;text-transform:uppercase;letter-spacing:.35px;color:#64748b;font-weight:800}
            .cfi-field input,.cfi-field select{width:100%;border:1px solid #cbd5e1;border-radius:10px;padding:8px 10px;font-size:13px;background:#fff}
            .cfi-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
            .cfi-btn{border:1px solid #cbd5e1;background:#fff;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:700;color:#0f172a;cursor:pointer}
            .cfi-btn.primary{background:#166534;border-color:#166534;color:#fff}
            .cfi-kpis{display:grid;gap:10px;grid-template-columns:repeat(5,minmax(0,1fr))}
            .cfi-kpi{padding:12px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc}
            .cfi-kpi strong{display:block;font-size:18px;color:#0f172a}
            .cfi-kpi span{display:block;margin-top:4px;color:#64748b;font-size:11px;text-transform:uppercase;font-weight:800}
            .cfi-kpi small{display:block;margin-top:6px;color:#475569;font-size:11px}
            .cfi-ok{border-color:#22c55e;background:#f0fdf4}
            .cfi-warning{border-color:#f59e0b;background:#fffbeb}
            .cfi-error{border-color:#ef4444;background:#fef2f2}
            .cfi-alert{padding:10px;border-radius:10px;border:1px solid #bfdbfe;background:#eff6ff;color:#1e3a8a;font-size:12px}
            .cfi-table{width:100%;border-collapse:collapse;margin-top:8px}
            .cfi-table th,.cfi-table td{border:1px solid #e2e8f0;padding:6px 8px;font-size:12px;vertical-align:top}
            .cfi-table th{background:#f8fafc;text-align:left}
            @media (max-width: 1200px){.cfi-grid.filters,.cfi-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
        `;
        document.head.appendChild(style);
    }

    render_shell() {
        this.wrapper.html(`
            <div class="cfi-shell">
                <div class="cfi-card">
                    <div class="cfi-head">
                        <h3>${__("Selector de Periodo")}</h3>
                        <p>${__("Selecciona el paquete y ejecuta una validacion informativa de emision.")}</p>
                    </div>
                    <div class="cfi-body">
                        <div class="cfi-grid filters">
                            <div class="cfi-field">
                                <label>${__("Cliente")}</label>
                                <select data-role="cliente"></select>
                            </div>
                            <div class="cfi-field">
                                <label>${__("Anio")}</label>
                                <input data-role="anio" type="number" min="1900" max="2200" />
                            </div>
                            <div class="cfi-field">
                                <label>${__("Mes")}</label>
                                <select data-role="mes"></select>
                            </div>
                            <div class="cfi-field">
                                <label>${__("Paquete")}</label>
                                <select data-role="paquete"></select>
                            </div>
                        </div>
                        <div class="cfi-actions">
                            <button class="cfi-btn primary" data-action="run">${__("Evaluar Indicadores")}</button>
                            <button class="cfi-btn" data-action="refresh">${__("Refrescar")}</button>
                            <button class="cfi-btn" data-action="open-package">${__("Abrir Paquete")}</button>
                        </div>
                    </div>
                </div>

                <div class="cfi-card">
                    <div class="cfi-head">
                        <h3>${__("Indicadores de Emision")}</h3>
                    </div>
                    <div class="cfi-body">
                        <div class="cfi-alert" data-role="meta">${__("Estos indicadores son informativos y no bloquean la emision.")}</div>
                        <div class="cfi-kpis" data-role="kpis" style="margin-top:10px;"></div>
                    </div>
                </div>

                <div class="cfi-card">
                    <div class="cfi-head">
                        <h3>${__("Detalle de Hallazgos")}</h3>
                    </div>
                    <div class="cfi-body" data-role="details"></div>
                </div>
            </div>
        `);

        this.$cliente = this.wrapper.find('[data-role="cliente"]');
        this.$anio = this.wrapper.find('[data-role="anio"]');
        this.$mes = this.wrapper.find('[data-role="mes"]');
        this.$paquete = this.wrapper.find('[data-role="paquete"]');
        this.$kpis = this.wrapper.find('[data-role="kpis"]');
        this.$meta = this.wrapper.find('[data-role="meta"]');
        this.$details = this.wrapper.find('[data-role="details"]');

        this.$anio.val(this.state.anio || new Date().getFullYear());
    }

    bind_events() {
        this.$cliente.on("change", () => {
            this.state.cliente = this.$cliente.val() || "";
            this.load_bootstrap();
        });
        this.$anio.on("change", () => {
            this.state.anio = this.as_int(this.$anio.val(), new Date().getFullYear());
            this.load_bootstrap();
        });
        this.$mes.on("change", () => {
            this.state.mes = this.$mes.val() || "";
            this.load_bootstrap();
        });
        this.$paquete.on("change", () => {
            this.state.paquete_name = this.$paquete.val() || "";
            this.run_indicators();
        });

        this.wrapper.on("click", "[data-action='run']", () => this.run_indicators());
        this.wrapper.on("click", "[data-action='refresh']", () => this.load_bootstrap());
        this.wrapper.on("click", "[data-action='open-package']", () => this.open_package_form());
    }

    load_bootstrap() {
        if (this.loading) return;
        this.loading = true;

        const route = this.state.route_options || {};
        this.state.route_options = {};

        const args = {
            cliente: route.cliente || this.state.cliente || null,
            anio: route.anio || this.state.anio || null,
            mes: route.mes || this.state.mes || null,
            paquete_name: route.package_name || route.paquete_name || this.state.paquete_name || null,
        };

        frappe.call({
            method: "mfi_tools.mfi_tools.page.indicadores_emision_eeff.indicadores_emision_eeff.get_indicator_bootstrap",
            args,
            callback: (r) => {
                this.loading = false;
                const data = r.message || {};
                this.absorb_bootstrap(data);
                this.render_all();
            },
            error: () => {
                this.loading = false;
            }
        });
    }

    run_indicators() {
        const paquete_name = this.$paquete.val() || this.state.paquete_name;
        if (!paquete_name) {
            frappe.msgprint(__("Selecciona un paquete para evaluar."));
            return;
        }

        frappe.call({
            method: "mfi_tools.mfi_tools.page.indicadores_emision_eeff.indicadores_emision_eeff.run_emission_indicators",
            args: { paquete_name },
            freeze: true,
            freeze_message: __("Evaluando indicadores de emision..."),
            callback: (r) => {
                this.state.paquete_name = paquete_name;
                this.state.indicators = r.message || null;
                this.render_indicators();
                frappe.show_alert({ message: __("Indicadores actualizados."), indicator: "green" });
            },
        });
    }

    absorb_bootstrap(data) {
        this.state.cliente = data.cliente || this.state.cliente || "";
        this.state.anio = this.as_int(data.anio, this.state.anio || new Date().getFullYear());
        this.state.mes = data.mes || this.state.mes || "";
        this.state.paquete_name = data.paquete_name || this.state.paquete_name || "";
        this.state.clients = data.clients || [];
        this.state.packages = data.packages || [];
        this.state.meses = data.meses || [];
        this.state.indicators = data.indicators || this.state.indicators || null;
    }

    render_all() {
        this.set_select_options(this.$cliente, this.state.clients, this.state.cliente);
        this.set_select_options(this.$mes, (this.state.meses || []).map((row) => ({ value: row, label: row })), this.state.mes);
        this.set_select_options(this.$paquete, this.state.packages, this.state.paquete_name);
        this.$anio.val(this.state.anio || new Date().getFullYear());
        this.render_indicators();
    }

    render_indicators() {
        const data = this.state.indicators;
        if (!data || !data.kpis) {
            this.$kpis.html(`<div class="cfi-kpi"><strong>-</strong><span>${this.escape(__("Sin evaluacion"))}</span></div>`);
            this.$details.html(`<p>${this.escape(__("Selecciona un paquete y ejecuta la evaluacion."))}</p>`);
            return;
        }

        this.$meta.text((data.meta && data.meta.message) || __("Estos indicadores son informativos y no bloquean la emision."));

        const cards = [
            {
                title: __("Score de Emision"),
                value: `${data.kpis.score || 0}/100`,
                detail: data.kpis.health_level || "-",
                status: data.kpis.health_status || "warning",
            },
            {
                title: data.kpis.cuadre.title || __("Cuadre Automatico"),
                value: data.kpis.cuadre.value || "-",
                detail: data.kpis.cuadre.detail || "-",
                status: data.kpis.cuadre.status || "warning",
            },
            {
                title: data.kpis.lineas_huerfanas.title || __("Lineas Huerfanas"),
                value: `${data.kpis.lineas_huerfanas.value || 0}`,
                detail: data.kpis.lineas_huerfanas.detail || "-",
                status: data.kpis.lineas_huerfanas.status || "warning",
            },
            {
                title: data.kpis.formulas_rotas.title || __("Formulas Rotas"),
                value: `${data.kpis.formulas_rotas.value || 0}`,
                detail: data.kpis.formulas_rotas.detail || "-",
                status: data.kpis.formulas_rotas.status || "warning",
            },
            {
                title: data.kpis.notas_faltantes.title || __("Notas Faltantes"),
                value: `${data.kpis.notas_faltantes.value || 0}`,
                detail: data.kpis.notas_faltantes.detail || "-",
                status: data.kpis.notas_faltantes.status || "warning",
            },
        ];

        this.$kpis.html(cards.map((card) => `
            <div class="cfi-kpi cfi-${this.escape(card.status)}">
                <strong>${this.escape(card.value)}</strong>
                <span>${this.escape(card.title)}</span>
                <small>${this.escape(card.detail)}</small>
            </div>
        `).join(""));

        this.render_details(data.details || {});
    }

    render_details(details) {
        const orphanRows = details.lineas_huerfanas || [];
        const formulaRows = details.formulas_rotas || [];
        const noteRows = details.notas_faltantes || [];

        const orphanHtml = orphanRows.length
            ? `<table class="cfi-table">
                    <thead><tr><th>Estado</th><th>Codigo</th><th>Descripcion</th><th>Nivel</th><th>Motivo</th></tr></thead>
                    <tbody>
                        ${orphanRows.map((row) => `<tr><td>${this.escape(row.estado)}</td><td>${this.escape(row.codigo)}</td><td>${this.escape(row.descripcion)}</td><td>${this.escape(String(row.nivel || "-"))}</td><td>${this.escape(row.motivo || "-")}</td></tr>`).join("")}
                    </tbody>
               </table>`
            : `<p>${this.escape(__("Sin lineas huerfanas."))}</p>`;

        const formulaHtml = formulaRows.length
            ? `<table class="cfi-table">
                    <thead><tr><th>Scope</th><th>Documento</th><th>Codigo</th><th>Referencia</th><th>Motivo</th></tr></thead>
                    <tbody>
                        ${formulaRows.map((row) => `<tr><td>${this.escape(row.scope || "-")}</td><td>${this.escape(row.documento || "-")}</td><td>${this.escape(row.codigo || "-")}</td><td>${this.escape(row.referencia || "-")}</td><td>${this.escape(row.motivo || "-")}</td></tr>`).join("")}
                    </tbody>
               </table>`
            : `<p>${this.escape(__("Sin formulas rotas."))}</p>`;

        const noteHtml = noteRows.length
            ? `<table class="cfi-table">
                    <thead><tr><th>Tipo</th><th>Detalle</th></tr></thead>
                    <tbody>
                        ${noteRows.map((row) => `<tr><td>${this.escape(row.tipo || "-")}</td><td>${this.escape(row.detalle || "-")}</td></tr>`).join("")}
                    </tbody>
               </table>`
            : `<p>${this.escape(__("Sin notas faltantes."))}</p>`;

        this.$details.html(`
            <h4>${this.escape(__("Lineas Huerfanas"))}</h4>
            ${orphanHtml}
            <h4 style="margin-top:14px;">${this.escape(__("Formulas Rotas"))}</h4>
            ${formulaHtml}
            <h4 style="margin-top:14px;">${this.escape(__("Notas Faltantes"))}</h4>
            ${noteHtml}
        `);
    }

    open_package_form() {
        const packageName = this.$paquete.val() || this.state.paquete_name;
        if (!packageName) {
            frappe.msgprint(__("No hay paquete seleccionado."));
            return;
        }
        frappe.set_route("Form", "Paquete EEFF", packageName);
    }

    set_select_options($field, rows, selected) {
        if (!$field) return;
        const options = [`<option value=""></option>`];
        (rows || []).forEach((row) => {
            const value = row.value || "";
            const label = row.label || value;
            const isSelected = selected && selected === value ? "selected" : "";
            options.push(`<option value="${this.escape(value)}" ${isSelected}>${this.escape(label)}</option>`);
        });
        $field.html(options.join(""));
    }

    as_int(value, fallback = 0) {
        const parsed = parseInt(value, 10);
        return Number.isNaN(parsed) ? fallback : parsed;
    }

    escape(value) {
        return frappe.utils.escape_html(String(value || ""));
    }
}
