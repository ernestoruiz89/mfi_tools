const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function setup() {
    const calls = [];
    const routes = [];
    const field = (value = "") => ({
        value, handlers: {},
        val(next) { if (arguments.length) this.value = next; return this.value; },
        on(event, handler) { this.handlers[event] = handler; },
        html() {}, prop() {},
    });
    const context = {
        frappe: {
            pages: {"indicadores-emision-eeff": {}},
            call: (options) => calls.push(options), msgprint() {}, show_alert() {},
            set_route: (...route) => routes.push(route),
            utils: {escape_html: (text) => text},
        },
        __: (text) => text,
    };
    vm.createContext(context);
    const source = fs.readFileSync(path.join(__dirname,
        "../mfi_tools/mfi_tools/page/indicadores_emision_eeff/indicadores_emision_eeff.js"), "utf8");
    vm.runInContext(source + "\nglobalThis.Controller = IndicadoresEmisionEEFF;", context);
    const controller = new context.Controller({main: {find: () => field(), on() {}}});
    for (const name of ["cliente", "anio", "mes", "paquete"]) controller[`$${name}`] = field();
    controller.$meta = {value: "", text(text) { this.value = text; }};
    controller.render_indicators = () => {};
    controller.render_all = () => {};
    return {controller, calls, routes};
}

test("new filter requests supersede earlier responses", () => {
    const {controller: c, calls} = setup();
    c.state.anio = 2025;
    c.load_bootstrap();
    c.state.anio = 2026;
    c.load_bootstrap();
    calls[1].callback({message: {anio: 2026, packages: [{value: "NEW"}]}});
    calls[0].callback({message: {anio: 2025, packages: [{value: "OLD"}]}});
    assert.equal(c.state.anio, 2026);
    assert.equal(c.state.packages[0].value, "NEW");
});

test("explicit empty bootstrap clears previously evaluated package", () => {
    const {controller: c} = setup();
    c.state.paquete_name = "OLD";
    c.state.indicators = {kpis: {score: 100}};
    c.absorb_bootstrap({paquete_name: null, indicators: null, cliente: null, anio: null, mes: null});
    assert.equal(c.state.paquete_name, "");
    assert.equal(c.state.indicators, null);
});

test("an old evaluation cannot overwrite the newly selected package", () => {
    const {controller: c, calls} = setup();
    c.$paquete.val("A"); c.run_indicators();
    c.$paquete.val("B"); c.run_indicators();
    calls[1].callback({message: {package: {name: "B"}}});
    calls[0].callback({message: {package: {name: "A"}}});
    assert.equal(c.state.indicators.package.name, "B");
    assert.equal(c.loading, false);
});

test("a failed evaluation leaves no stale score", () => {
    const {controller: c, calls} = setup();
    c.state.indicators = {kpis: {score: 100}};
    c.$paquete.val("B"); c.run_indicators();
    assert.equal(c.state.indicators, null);
    calls[0].error();
    assert.equal(c.state.indicators, null);
    assert.equal(c.loading, false);
    assert.match(c.$meta.value, /fallo/);
});

test("clearing a filter invalidates the old package before fetching", () => {
    const {controller: c, calls} = setup();
    c.bind_events();
    c.state.paquete_name = "OLD";
    c.state.indicators = {kpis: {score: 100}};
    c.$cliente.val("Other");
    c.$cliente.handlers.change();
    assert.equal(c.state.paquete_name, "");
    assert.equal(c.state.indicators, null);
    assert.equal(calls[0].args.paquete_name, null);
});

test("empty visible selection never opens a previously selected package", () => {
    const {controller: c, routes} = setup();
    c.state.paquete_name = "OLD";
    c.$paquete.val("");
    c.open_package_form();
    assert.equal(routes.length, 0);
});
