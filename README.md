# MFI Tools

App Frappe para preparar EEFF por periodo (`cliente + mes + anio`) con flujo operativo:

- Carga de balanza de comprobacion por CSV.
- Preparacion de paquete EEFF (estados, notas y datos estadisticos).
- Mapeo contable por reglas hacia lineas/cifras/celdas destino.
- Validaciones de formulas y estructura.
- Indicadores de emision y exportacion a Word.

## Versiones y acceso en Frappe v16

- La rama `v15` conserva la version anterior. El desarrollo para v16 continua en `main`.
- MFI Tools 0.2.1 se verifico en WSL con Frappe 16.52.0, ERPNext 16.51.1 y Python 3.14.
- Requiere ERPNext y `python-docx` para la exportacion Word; Bench instala esta dependencia Python.
- Se incluyen `Sidebar` y `Dock` para la navegacion nueva, y `Workspace Sidebar` para versiones como Frappe 16.5. El menu de compatibilidad se exporta en `mfi_tools/workspace_sidebar/panel_mfi_tools.json`.
- El acceso **MFI Tools** aparece tanto en Apps como en Desk con el icono `mfi_tools/public/images/mfi-tools.svg`. Su destino es `/desk/panel-mfi-tools`, sin depender de rutas con el nombre del modulo.
- El menu lateral agrupa Preparacion EEFF, Estados y notas y Configuracion. El panel agrega cuatro accesos rapidos y las mismas tres secciones.
- La visibilidad de la app respeta el permiso de lectura de `Paquete EEFF` para usuarios del Desk. Los roles actuales de los documentos y paginas siguen siendo `System Manager`.
- Las tasas de cambio se editan dentro de cada **Balanza Comprobacion EEFF**, en **Tasas de Cambio por Moneda**. `Tasa Cambio Balanza EEFF` es una tabla hija y no tiene lista independiente.

Instalacion en un bench v16 con ERPNext instalado:

```bash
bench get-app /ruta/a/mfi_tools --soft-link --skip-assets
bench --site nombre-del-sitio backup --with-files
bench --site nombre-del-sitio install-app mfi_tools
bench build --app mfi_tools
bench --site nombre-del-sitio migrate
bench --site nombre-del-sitio clear-cache
```

En un sitio que ya tiene MFI Tools, actualizar `main`, instalar sus dependencias con `bench setup requirements --python` y ejecutar build, migrate y clear-cache. La navegacion se importa desde los JSON de la app; las personalizaciones del sitio y del usuario se administran con las capas de Frappe. Recargar el navegador despues de actualizar.

## Alcance funcional actual

- `Balanza Comprobacion EEFF`: normaliza lineas, calcula `saldo`, totales `debe/haber`, valida duplicados y determina `cuadra`.
- `Paquete EEFF`: sincroniza nombre/periodo, controla totales, calcula formulas en datos estadisticos.
- `Estado Financiero EEFF`: calcula lineas formula (`formula_lineas`) con deteccion de referencias circulares.
- `Nota EEFF`: calcula cifras formula (`formula_cifras`) y normaliza cifras/celdas.
- `Regla Mapeo Contable EEFF`: valida origen/destino, cuentas (+/-) y periodo de valor para celdas de tablas complejas.
- Servicios de mapeo: aplica reglas y actualiza destinos del paquete.
- Exportacion Word: genera documento consolidado del paquete.

## Doctypes

- `Balanza Comprobacion EEFF`
- `Linea Balanza Comprobacion EEFF`
- `Paquete EEFF`
- `Estado Financiero EEFF`
- `Linea Estado Financiero EEFF`
- `Nota EEFF`
- `Cifra Nota EEFF`
- `Celda Nota EEFF`
- `Dato Estadistico EEFF`
- `Regla Mapeo Contable EEFF`
- `Cuenta Regla Mapeo EEFF`
- `Plantilla Estado Financiero EEFF`
- `Fila Plantilla Estado Financiero EEFF`
- `Plantilla Nota EEFF`
- `Fila Plantilla Nota EEFF`
- `Plantilla Dato Estadistico EEFF`
- `Fila Plantilla Dato Estadistico EEFF`

## Paginas y Workspace

- Pagina `asistente_eeff`: flujo guiado para preparar paquete, cargar CSV y mapear.
- Pagina `indicadores_emision_eeff`: KPIs de cuadre, lineas huerfanas, formulas rotas y notas faltantes.
- Pagina `helper_mapeo_notas_eeff`: helper visual para mapear cifras y celdas de notas complejas.
- Workspace `panel_mfi_tools`.

## Print formats

- `Estado Financiero EEFF Base`
- `Nota EEFF Individual`
- `Paquete EEFF Completo`

## Endpoints `whitelist`

### Balanza

- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.cargar_balanza_csv(balanza_name, csv_content)`

### Paquete

- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.ejecutar_mapeo(paquete_name)`
- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.exportar_paquete_word(paquete_name)`
- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.aplicar_plantillas_reutilizables(paquete_name, plantilla_estado=None, plantilla_nota=None, plantilla_dato_estadistico=None, marco_referencia=None, limpiar_estados=0, limpiar_notas=0, limpiar_datos_estadisticos=0)`
- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.copiar_notas_desde_paquete(paquete_name, paquete_fuente, limpiar_notas=0)`

### Asistente EEFF

- `mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.get_wizard_bootstrap(cliente=None, anio=None, mes=None, package_name=None, balanza_name=None)`
- `mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.prepare_package(cliente, anio, mes, package_name=None, balanza_name=None)`
- `mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.upload_balanza_csv_from_wizard(balanza_name, csv_content)`
- `mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.run_mapping_from_wizard(package_name)`
- `mfi_tools.mfi_tools.page.asistente_eeff.asistente_eeff.one_click_upload_and_map(cliente, anio, mes, csv_content, package_name=None, balanza_name=None)`

### Indicadores de emision

- `mfi_tools.mfi_tools.page.indicadores_emision_eeff.indicadores_emision_eeff.get_indicator_bootstrap(cliente=None, anio=None, mes=None, paquete_name=None)`
- `mfi_tools.mfi_tools.page.indicadores_emision_eeff.indicadores_emision_eeff.run_emission_indicators(paquete_name)`

## Formato CSV de balanza

`cargar_balanza_csv` acepta encabezados equivalentes:

- Cuenta: `cuenta`, `codigo_cuenta`, `account`
- Descripcion: `descripcion`, `descripcion_cuenta`, `account_name`
- Debe: `debe`, `debit`
- Haber: `haber`, `credit`
- Centro de costo: `centro_costo`, `cost_center`

## Notas tecnicas

- Los nombres de documentos de balanza y paquete se sincronizan con el periodo.
- El mapeo y calculos formulan referencias por codigo y validan ciclos.
- Los indicadores de emision son informativos y no bloquean la emision.
