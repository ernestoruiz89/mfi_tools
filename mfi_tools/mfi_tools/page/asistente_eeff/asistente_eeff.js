frappe.pages["asistente-eeff"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Asistente EEFF",
        single_column: true,
    });

    frappe.pages["asistente-eeff"].wizard = new AsistenteEEFF(page);
    frappe.pages["asistente-eeff"].wizard.init();
};

frappe.pages["asistente-eeff"].on_page_show = function () {
    const wizard = frappe.pages["asistente-eeff"].wizard;
    if (!wizard) return;
    wizard.apply_route_options();
    wizard.load_bootstrap();
};

class AsistenteEEFF {
    constructor(page) {
        this.page = page;
        this.wrapper = page.main;
        this.state = {
            cliente: "",
            anio: new Date().getFullYear(),
            mes: "",
            package_name: "",
            balanza_name: "",
            clients: [],
            packages: [],
            balanzas: [],
            meses: [],
            status: null,
            route_options: {},
            moneda_tasa_cambio: "USD",
            tasa_cambio: 1,
        };
        this.loading = false;
    }

    init() {
        this.setup_styles();
        this.render_shell();
        this.bind_events();
        this.page.set_primary_action(__("Cargar y Mapear"), () => this.one_click_upload_and_map(), "play");
        this.page.set_secondary_action(__("Preparar Paquete"), () => this.prepare_package());
    }

    apply_route_options() {
        this.state.route_options = frappe.route_options || {};
        frappe.route_options = null;
    }

    setup_styles() {
        if (document.getElementById("cf-wizard-style")) return;
        const style = document.createElement("style");
        style.id = "cf-wizard-style";
        style.textContent = `
            .cf-shell{display:grid;grid-template-columns:1fr;gap:14px;padding:16px;border:1px solid #dbe4ee;border-radius:16px;background:linear-gradient(170deg,#f8fbff 0%,#f2f8f5 55%,#fffdf7 100%)}
            .cf-card{background:#fff;border:1px solid #dbe4ee;border-radius:14px;box-shadow:0 8px 20px rgba(15,23,42,.05)}
            .cf-head{padding:14px 16px;border-bottom:1px solid #eef2f7}
            .cf-head h3{margin:0;color:#0f172a;font-size:15px;font-weight:800}
            .cf-head p{margin:6px 0 0;color:#64748b;font-size:12px}
            .cf-body{padding:14px 16px}
            .cf-grid{display:grid;gap:10px}
            .cf-grid.filters{grid-template-columns:repeat(5,minmax(0,1fr))}
            .cf-field{display:flex;flex-direction:column;gap:6px}
            .cf-field label{font-size:11px;text-transform:uppercase;letter-spacing:.35px;color:#64748b;font-weight:800}
            .cf-field input,.cf-field select,.cf-field textarea{width:100%;border:1px solid #cbd5e1;border-radius:10px;padding:8px 10px;font-size:13px;background:#fff}
            .cf-field textarea{min-height:220px;resize:vertical;font-family:Consolas,Monaco,monospace}
            .cf-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
            .cf-btn{border:1px solid #cbd5e1;background:#fff;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:700;color:#0f172a;cursor:pointer}
            .cf-btn.primary{background:#166534;border-color:#166534;color:#fff}
            .cf-btn.secondary{background:#0f766e;border-color:#0f766e;color:#fff}
            .cf-status{display:grid;gap:10px;grid-template-columns:repeat(5,minmax(0,1fr))}
            .cf-kpi{padding:12px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc}
            .cf-kpi strong{display:block;font-size:18px;color:#0f172a}
            .cf-kpi span{display:block;margin-top:4px;color:#64748b;font-size:11px;text-transform:uppercase;font-weight:800}
            .cf-log{margin-top:10px;padding:10px;border-radius:10px;background:#f8fafc;border:1px solid #e2e8f0;color:#334155;font-size:12px;white-space:pre-wrap}
            @media (max-width: 1200px){.cf-grid.filters,.cf-status{grid-template-columns:repeat(2,minmax(0,1fr))}}
        `;
        document.head.appendChild(style);
    }

    render_shell() {
        this.wrapper.html(`
            <div class="cf-shell">
                <div class="cf-card">
                    <div class="cf-head">
                        <h3>${__("1) Contexto del Periodo")}</h3>
                        <p>${__("Selecciona cliente, anio, mes y prepara o reutiliza paquete/balanza.")}</p>
                    </div>
                    <div class="cf-body">
                        <div class="cf-grid filters">
                            <div class="cf-field">
                                <label>${__("Cliente")}</label>
                                <select data-role="cliente"></select>
                            </div>
                            <div class="cf-field">
                                <label>${__("Anio")}</label>
                                <input data-role="anio" type="number" min="1900" max="2200" />
                            </div>
                            <div class="cf-field">
                                <label>${__("Mes")}</label>
                                <select data-role="mes"></select>
                            </div>
                            <div class="cf-field">
                                <label>${__("Paquete")}</label>
                                <select data-role="package"></select>
                            </div>
                            <div class="cf-field">
                                <label>${__("Balanza")}</label>
                                <select data-role="balanza"></select>
                            </div>
                        </div>
                        <div class="cf-actions">
                            <button class="cf-btn secondary" data-action="prepare">${__("Preparar Paquete/Balanza")}</button>
                            <button class="cf-btn" data-action="refresh">${__("Refrescar")}</button>
                            <button class="cf-btn" data-action="open-package">${__("Abrir Paquete")}</button>
                            <button class="cf-btn" data-action="open-balanza">${__("Abrir Balanza")}</button>
                        </div>
                    </div>
                </div>

                <div class="cf-card">
                    <div class="cf-head">
                        <h3>${__("2) Cargar Balanza CSV")}</h3>
                        <p>${__("Pega el CSV o selecciona archivo. Formato sugerido: codigo_cuenta,descripcion_cuenta,centro_costo,debe_saldo_anterior,haber_saldo_anterior,debe_mes,haber_mes,debe_saldo,haber_saldo. Si tu sistema solo exporta saldo neto, puedes usar la columna saldo o valores negativos en debe_saldo y debe_saldo_anterior.")}</p>
                    </div>
                    <div class="cf-body">
                        <div class="cf-grid" style="grid-template-columns: repeat(2, minmax(0, 220px));">
                            <div class="cf-field">
                                <label>${__("Moneda TC")}</label>
                                <input data-role="moneda-tc" type="text" placeholder="USD" />
                            </div>
                            <div class="cf-field">
                                <label>${__("Tasa de Cambio")}</label>
                                <input data-role="tasa-cambio" type="number" step="0.0001" min="0.0001" />
                            </div>
                        </div>
                        <div class="cf-field">
                            <label>${__("Contenido CSV")}</label>
                            <textarea data-role="csv"></textarea>
                        </div>
                        <input data-role="csv-file" type="file" accept=".csv,text/csv" style="display:none;" />
                        <div class="cf-actions">
                            <button class="cf-btn secondary" data-action="download-template">${__("Descargar Plantilla CSV")}</button>
                            <button class="cf-btn" data-action="pick-file">${__("Seleccionar CSV")}</button>
                            <button class="cf-btn" data-action="upload">${__("Cargar CSV")}</button>
                        </div>
                    </div>
                </div>

                <div class="cf-card">
                    <div class="cf-head">
                        <h3>${__("3) Ejecutar Mapeo")}</h3>
                        <p>${__("Ejecuta solo mapeo o haz carga + mapeo en un clic.")}</p>
                    </div>
                    <div class="cf-body">
                        <div class="cf-actions">
                            <button class="cf-btn" data-action="map">${__("Ejecutar Mapeo")}</button>
                            <button class="cf-btn primary" data-action="one-click">${__("Cargar y Mapear")}</button>
                        </div>
                        <div class="cf-log" data-role="log">${__("Listo.")}</div>
                    </div>
                </div>

                <div class="cf-card">
                    <div class="cf-head">
                        <h3>${__("Estado del Flujo")}</h3>
                    </div>
                    <div class="cf-body">
                        <div class="cf-status" data-role="status"></div>
                    </div>
                </div>
            </div>
        `);

        this.$cliente = this.wrapper.find('[data-role="cliente"]');
        this.$anio = this.wrapper.find('[data-role="anio"]');
        this.$mes = this.wrapper.find('[data-role="mes"]');
        this.$package = this.wrapper.find('[data-role="package"]');
        this.$balanza = this.wrapper.find('[data-role="balanza"]');
        this.$monedaTC = this.wrapper.find('[data-role="moneda-tc"]');
        this.$tasaCambio = this.wrapper.find('[data-role="tasa-cambio"]');
        this.$csv = this.wrapper.find('[data-role="csv"]');
        this.$csvFile = this.wrapper.find('[data-role="csv-file"]');
        this.$status = this.wrapper.find('[data-role="status"]');
        this.$log = this.wrapper.find('[data-role="log"]');

        this.$anio.val(this.state.anio || new Date().getFullYear());
        this.$monedaTC.val(this.state.moneda_tasa_cambio || "USD");
        this.$tasaCambio.val(this.state.tasa_cambio || 1);
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
        this.$package.on("change", () => {
            this.state.package_name = this.$package.val() || "";
            this.load_bootstrap();
        });
        this.$balanza.on("change", () => {
            this.state.balanza_name = this.$balanza.val() || "";
            this.load_bootstrap();
        });
        this.$monedaTC.on("change", () => {
            this.state.moneda_tasa_cambio = this.get_moneda_tasa_cambio();
        });
        this.$tasaCambio.on("change", () => {
            this.state.tasa_cambio = this.get_tasa_cambio();
        });

        this.wrapper.on("click", "[data-action='prepare']", () => this.prepare_package());
        this.wrapper.on("click", "[data-action='refresh']", () => this.load_bootstrap());
        this.wrapper.on("click", "[data-action='download-template']", () => this.download_csv_template());
        this.wrapper.on("click", "[data-action='pick-file']", () => this.$csvFile.trigger("click"));
        this.wrapper.on("click", "[data-action='upload']", () => this.upload_csv());
        this.wrapper.on("click", "[data-action='map']", () => this.run_mapping());
        this.wrapper.on("click", "[data-action='one-click']", () => this.one_click_upload_and_map());
        this.wrapper.on("click", "[data-action='open-package']", () => this.open_package_form());
        this.wrapper.on("click", "[data-action='open-balanza']", () => this.open_balanza_form());

        this.$csvFile.on("change", (event) => this.handle_csv_file(event));
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
            package_name: route.package_name || this.state.package_name || null,
            balanza_name: route.balanza_name || this.state.balanza_name || null,
        };

        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.get_wizard_bootstrap",
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

    absorb_bootstrap(data) {
        this.state.cliente = data.cliente || this.state.cliente || "";
        this.state.anio = this.as_int(data.anio, this.state.anio || new Date().getFullYear());
        this.state.mes = data.mes || this.state.mes || "";
        this.state.package_name = data.package_name || this.state.package_name || "";
        this.state.balanza_name = data.balanza_name || this.state.balanza_name || "";
        this.state.clients = data.clients || [];
        this.state.packages = data.packages || [];
        this.state.balanzas = data.balanzas || [];
        this.state.meses = data.meses || [];
        this.state.status = data.status || null;
        const statusCurrency = String((this.state.status || {}).moneda_tasa_cambio || "").trim().toUpperCase();
        if (statusCurrency) {
            this.state.moneda_tasa_cambio = statusCurrency;
        } else if (!this.state.moneda_tasa_cambio) {
            this.state.moneda_tasa_cambio = "USD";
        }
        const statusRate = this.as_float((this.state.status || {}).tasa_cambio, 0);
        if (statusRate > 0) {
            this.state.tasa_cambio = statusRate;
        } else if (!this.state.tasa_cambio || this.state.tasa_cambio <= 0) {
            this.state.tasa_cambio = 1;
        }

        if (!this.state.package_name && this.state.packages.length === 1) {
            this.state.package_name = this.state.packages[0].value;
        }
        if (!this.state.balanza_name && this.state.balanzas.length === 1) {
            this.state.balanza_name = this.state.balanzas[0].value;
        }
    }

    render_all() {
        this.set_select_options(this.$cliente, this.state.clients, this.state.cliente);
        this.set_select_options(this.$mes, (this.state.meses || []).map((row) => ({ value: row, label: row })), this.state.mes);
        this.set_select_options(this.$package, this.state.packages, this.state.package_name);
        this.set_select_options(this.$balanza, this.state.balanzas, this.state.balanza_name);
        this.$anio.val(this.state.anio || new Date().getFullYear());
        this.$monedaTC.val(this.state.moneda_tasa_cambio || "USD");
        this.$tasaCambio.val(this.state.tasa_cambio || 1);
        this.render_status();
    }

    render_status() {
        const st = this.state.status || {};
        const rows = [
            { label: __("Cliente"), value: st.cliente_label || st.cliente || "-" },
            { label: __("Paquete"), value: st.package_name || "-" },
            { label: __("Balanza"), value: st.balanza_name || "-" },
            { label: __("Estado Flujo"), value: st.estado_preparacion || "-" },
            { label: __("Lineas Balanza"), value: this.as_int(st.total_lineas, 0) },
            { label: __("Reglas Activas"), value: this.as_int(st.reglas_activas, 0) },
            { label: __("Total Estados"), value: this.as_int(st.total_estados, 0) },
            { label: __("Total Notas"), value: this.as_int(st.total_notas, 0) },
            { label: __("Total Debe Saldo"), value: this.format_currency(st.total_debe || 0) },
            { label: __("Total Haber Saldo"), value: this.format_currency(st.total_haber || 0) },
            { label: __("Moneda TC"), value: st.moneda_tasa_cambio || "-" },
            { label: __("Tasa Cambio"), value: this.as_float(st.tasa_cambio, 1) },
            { label: __("Tasas Registradas"), value: this.as_int(st.total_tasas_cambio, 0) },
            { label: __("Cuadra"), value: this.as_int(st.cuadra, 0) ? __("Si") : __("No") },
        ];

        this.$status.html(rows.map((row) => `
            <div class="cf-kpi">
                <strong>${this.escape(String(row.value))}</strong>
                <span>${this.escape(row.label)}</span>
            </div>
        `).join(""));
    }

    prepare_package() {
        const args = this.context_args();
        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.prepare_package",
            args,
            freeze: true,
            freeze_message: __("Preparando paquete y balanza..."),
            callback: (r) => {
                this.absorb_bootstrap(r.message || {});
                this.render_all();
                this.log(__("Paquete y balanza listos para trabajar."));
                frappe.show_alert({ message: __("Contexto preparado."), indicator: "green" });
            }
        });
    }

    upload_csv() {
        const balanza_name = this.$balanza.val() || this.state.balanza_name;
        const csv = (this.$csv.val() || "").trim();
        if (!balanza_name) {
            frappe.msgprint(__("Primero prepara o selecciona una balanza."));
            return;
        }
        if (!csv) {
            frappe.msgprint(__("Debes pegar o cargar contenido CSV."));
            return;
        }

        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.upload_balanza_csv_from_wizard",
            args: {
                balanza_name,
                csv_content: csv,
                moneda: this.get_moneda_tasa_cambio(),
                tasa_cambio: this.get_tasa_cambio(),
            },
            freeze: true,
            freeze_message: __("Cargando balanza..."),
            callback: (r) => {
                const data = r.message || {};
                this.state.status = data.status || this.state.status;
                this.render_status();
                const upload = data.upload || {};
                this.log([
                    __("CSV cargado en balanza {0}", [upload.balanza || balanza_name]),
                    __("Lineas: {0}", [upload.total_lineas || 0]),
                    __("Tasa de cambio ({0}): {1}", [
                        upload.moneda_tasa_cambio || this.get_moneda_tasa_cambio(),
                        upload.tasa_cambio || this.get_tasa_cambio(),
                    ]),
                    __("Cuadra: {0}", [upload.cuadra ? __("Si") : __("No")]),
                ].join("\n"));
                frappe.show_alert({ message: __("CSV cargado."), indicator: "green" });
            }
        });
    }

    run_mapping() {
        const package_name = this.$package.val() || this.state.package_name;
        if (!package_name) {
            frappe.msgprint(__("Primero prepara o selecciona un paquete."));
            return;
        }

        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.run_mapping_from_wizard",
            args: { package_name },
            freeze: true,
            freeze_message: __("Aplicando mapeo..."),
            callback: (r) => {
                const data = r.message || {};
                this.state.status = data.status || this.state.status;
                this.render_status();
                const mapping = data.mapping || {};
                this.log([
                    __("Mapeo ejecutado para paquete {0}", [mapping.paquete || package_name]),
                    __("Reglas: {0}", [mapping.reglas || 0]),
                    __("Estados actualizados: {0}", [mapping.estados_actualizados || 0]),
                    __("Notas actualizadas: {0}", [mapping.notas_actualizadas || 0]),
                    (mapping.alertas || []).length ? __("Alertas: {0}", [(mapping.alertas || []).join(" | ")]) : __("Sin alertas."),
                ].join("\n"));
                frappe.show_alert({ message: __("Mapeo aplicado."), indicator: "green" });
            }
        });
    }

    one_click_upload_and_map() {
        const csv = (this.$csv.val() || "").trim();
        if (!csv) {
            frappe.msgprint(__("Debes pegar o cargar CSV para usar 'Cargar y Mapear'."));
            return;
        }

        const args = {
            ...this.context_args(),
            csv_content: csv,
            moneda: this.get_moneda_tasa_cambio(),
            tasa_cambio: this.get_tasa_cambio(),
        };

        frappe.call({
            method: "mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.one_click_upload_and_map",
            args,
            freeze: true,
            freeze_message: __("Cargando balanza y aplicando mapeo..."),
            callback: (r) => {
                const data = r.message || {};
                this.state.status = data.status || this.state.status;
                this.render_status();
                const upload = data.upload || {};
                const mapping = data.mapping || {};
                this.log([
                    __("Flujo completo ejecutado."),
                    __("Balanza: {0}", [upload.balanza || this.state.balanza_name || "-"]),
                    __("Lineas: {0}", [upload.total_lineas || 0]),
                    __("Tasa de cambio ({0}): {1}", [
                        upload.moneda_tasa_cambio || this.get_moneda_tasa_cambio(),
                        upload.tasa_cambio || this.get_tasa_cambio(),
                    ]),
                    __("Reglas: {0}", [mapping.reglas || 0]),
                    __("Estados actualizados: {0}", [mapping.estados_actualizados || 0]),
                    __("Notas actualizadas: {0}", [mapping.notas_actualizadas || 0]),
                ].join("\n"));
                frappe.show_alert({ message: __("Carga + mapeo completados."), indicator: "green" });
            }
        });
    }

    download_csv_template() {
        const filename = "plantilla_balanza_comprobacion.csv";
        const csv = `\ufeff${this.build_balance_csv_template()}`;
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
        this.log(__("Plantilla CSV descargada: {0}", [filename]));
        frappe.show_alert({ message: __("Plantilla descargada."), indicator: "green" });
    }

    handle_csv_file(event) {
        const file = event.target.files && event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            this.$csv.val(reader.result || "");
            this.log(__("Archivo CSV cargado en memoria: {0}", [file.name]));
        };
        reader.readAsText(file, "utf-8");
    }

    open_package_form() {
        const package_name = this.$package.val() || this.state.package_name;
        if (!package_name) {
            frappe.msgprint(__("No hay paquete seleccionado."));
            return;
        }
        frappe.set_route("Form", "Paquete EEFF", package_name);
    }

    open_balanza_form() {
        const balanza_name = this.$balanza.val() || this.state.balanza_name;
        if (!balanza_name) {
            frappe.msgprint(__("No hay balanza seleccionada."));
            return;
        }
        frappe.set_route("Form", "Balanza Comprobacion EEFF", balanza_name);
    }

    context_args() {
        return {
            cliente: this.$cliente.val() || this.state.cliente || null,
            anio: this.as_int(this.$anio.val(), this.state.anio || new Date().getFullYear()),
            mes: this.$mes.val() || this.state.mes || null,
            package_name: this.$package.val() || this.state.package_name || null,
            balanza_name: this.$balanza.val() || this.state.balanza_name || null,
        };
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

    log(message) {
        this.$log.text(message || __("Listo."));
    }

    as_int(value, fallback = 0) {
        const parsed = parseInt(value, 10);
        return Number.isNaN(parsed) ? fallback : parsed;
    }

    as_float(value, fallback = 0) {
        const parsed = parseFloat(value);
        return Number.isNaN(parsed) ? fallback : parsed;
    }

    get_tasa_cambio() {
        const value = this.as_float(this.$tasaCambio.val(), this.state.tasa_cambio || 1);
        return value > 0 ? value : 1;
    }

    get_moneda_tasa_cambio() {
        const value = String(this.$monedaTC.val() || this.state.moneda_tasa_cambio || "USD").trim().toUpperCase();
        return value || "USD";
    }

    format_currency(value) {
        return frappe.format(value || 0, { fieldtype: "Currency" });
    }

    build_balance_csv_template() {
        const rows = [
            [
                "codigo_cuenta",
                "descripcion_cuenta",
                "centro_costo",
                "debe_saldo_anterior",
                "haber_saldo_anterior",
                "debe_mes",
                "haber_mes",
                "debe_saldo",
                "haber_saldo",
            ],
            ["1101", "Caja General", "ADM", "1500.00", "0.00", "250.00", "100.00", "1650.00", "0.00"],
            ["1201", "Cuentas por Cobrar", "COM", "2000.00", "0.00", "500.00", "200.00", "2300.00", "0.00"],
            ["6101", "Gasto Administrativo", "ADM", "0.00", "0.00", "300.00", "0.00", "300.00", "0.00"],
            ["6101", "Gasto Administrativo", "VEN", "0.00", "0.00", "200.00", "0.00", "200.00", "0.00"],
            ["2101", "Proveedores", "BOD", "0.00", "1800.00", "400.00", "900.00", "-2300.00", "0.00"],
            ["3101", "Capital Social", "", "0.00", "1650.00", "0.00", "0.00", "0.00", "1650.00"],
            ["4101", "Ingresos Operativos", "", "0.00", "0.00", "0.00", "500.00", "0.00", "500.00"],
        ];
        return rows.map((row) => this.to_csv_row(row)).join("\n");
    }

    to_csv_row(row) {
        return (row || [])
            .map((value) => `"${String(value ?? "").replace(/"/g, "\"\"")}"`)
            .join(",");
    }

    escape(value) {
        return frappe.utils.escape_html(String(value || ""));
    }
}
