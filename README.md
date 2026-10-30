# MFI Tools

App Frappe para preparar EEFF por periodo (`cliente + mes + anio`) con flujo operativo:

- Carga de balanza de comprobacion por CSV.
- Preparacion de paquete EEFF (estados, notas y datos estadisticos).
- Mapeo contable por reglas hacia lineas/cifras/celdas destino.
- Validaciones de formulas y estructura.
- Indicadores de emision y exportacion a Word.

## Versiones y acceso en Frappe v16

- La rama `v15` conserva la version anterior. El desarrollo para v16 continua en `main`.
- MFI Tools 0.2.2 se verifico en WSL con Frappe 16.52.0, ERPNext 16.51.1 y Python 3.14.
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

- Pagina `indicadores_emision_eeff`: KPIs de cuadre, lineas huerfanas, formulas rotas y notas faltantes.
- Workspace `panel_mfi_tools`.

## Indicadores de emision

La pagina `indicadores-emision-eeff` requiere el rol `System Manager` y permiso de lectura sobre el paquete y sus documentos vinculados. La evaluacion no guarda ni recalcula los importes de estados y notas en la base de datos.

- Cuadre: suma las columnas de saldo de las lineas de la balanza, con la misma tolerancia de 0.0001 que el documento. Una balanza vacia o de otra entidad/periodo no se considera cuadrada.
- Jerarquia: comprueba padres de lineas imprimibles y filas de estados complejos por tabla.
- Formulas: comprueba referencias y ciclos de formulas de lineas y tablas complejas. Reconoce formulas de datos (`BAL`, `EST`, `VAR`, funciones de periodo), cuya sintaxis y argumentos valida sin ejecutarlas. No sustituye la ejecucion del mapeo ni certifica los valores de las fuentes.
- Notas: comprueba secuencia, referencias desde estados y contenido visible. Titulos, saltos, espacios HTML y celdas vacias no completan una nota.
- Integridad: detecta estados faltantes o sin filas imprimibles y totales de balanza desactualizados. Se examinan todos los estados, notas y secciones del paquete.

El score mantiene las penalizaciones por cuadre (35 por error o 10 por advertencia), huerfanas (2 por hallazgo, maximo 25), formulas (3, maximo 25) y notas (2, maximo 15); agrega integridad (5, maximo 20). Cualquier error limita el score a 59; cualquier advertencia lo limita a 84. El panel identifica el paquete, periodo y hora de evaluacion, y descarta resultados anteriores cuando cambian los filtros o falla la consulta.

## Print formats

- `Estado Financiero EEFF Base`
- `Nota EEFF Individual`
- `Paquete EEFF Completo`

## Endpoints `whitelist`

### Balanza

- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.cargar_balanza_archivo(balanza_name, file_url=None, csv_content=None, tasa_cambio=None, moneda=None)`
- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.cargar_balanza_csv(balanza_name, csv_content, tasa_cambio=None, moneda=None)`
- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.descargar_balanza_excel(balanza_name)`
- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.descargar_plantilla_excel(balanza_name=None)`
- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.descargar_archivo_isc(balanza_name, id_moneda=0, longitud_cuenta="8", incluir_moneda_0=1, omitir_ceros=1, separador="|", tasa_cambio=1.0)`
- `mfi_tools.mfi_tools.doctype.balanza_comprobacion_eeff.balanza_comprobacion_eeff.validar_datos_isc(balanza_name, id_moneda=0, longitud_cuenta="8", incluir_moneda_0=1, omitir_ceros=1, separador="|", tasa_cambio=1.0)`

### Paquete

- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.ejecutar_mapeo(paquete_name)`
- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.exportar_paquete_word(paquete_name)`
- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.aplicar_plantillas_reutilizables(paquete_name, plantilla_estado=None, plantilla_nota=None, plantilla_dato_estadistico=None, marco_referencia=None, limpiar_estados=0, limpiar_notas=0, limpiar_datos_estadisticos=0)`
- `mfi_tools.mfi_tools.doctype.paquete_eeff.paquete_eeff.copiar_notas_desde_paquete(paquete_name, paquete_fuente, limpiar_notas=0)`

### Indicadores de emision

- `mfi_tools.mfi_tools.page.indicadores_emision_eeff.indicadores_emision_eeff.get_indicator_bootstrap(cliente=None, anio=None, mes=None, paquete_name=None)`
- `mfi_tools.mfi_tools.page.indicadores_emision_eeff.indicadores_emision_eeff.run_emission_indicators(paquete_name)`

## Formato de archivo de balanza (Excel / CSV)

`cargar_balanza_archivo` y `cargar_balanza_csv` aceptan archivos Excel (.xlsx, .xls) o CSV con detección automática de encabezados y alias equivalentes:

- Cuenta: `cuenta`, `codigo_cuenta`, `account`
- Descripcion: `descripcion`, `descripcion_cuenta`, `account_name`
- Debe: `debe`, `debit`
- Haber: `haber`, `credit`
- Centro de costo: `centro_costo`, `cost_center`

## Generación de Archivo ISC (CONAMI)

De acuerdo con el *Manual para el Envío de Información de Saldos Contables (ISC)* de la CONAMI (Nicaragua), el botón **Generar ISC (TXT)** genera el archivo oficial `isc_saldos.txt`:

- **Formato:** Archivo plano de texto delimitado por pleca (`|`), sin encabezado.
- **Estructura (6 campos):**
  1. `cta_contable` (Varchar 8, caracteres numéricos sin puntos ni guiones)
  2. `Id_moneda` (0 = Integradora, 1 = Nac c/MV, 2 = Nac s/MV, 3 = Extranjera)
  3. `Saldo_inicial` (numeric 20,2)
  4. `creditos_mes` (numeric 20,2)
  5. `debitos_mes` (numeric 20,2)
  6. `Saldo` (numeric 20,2)
- **Validaciones automáticas:** Cuadre de saldos (Σ Deudoras = Σ Acreedoras), agregación de cuentas por moneda, y generación de registros consolidados para la moneda integradora (0).

## Notas tecnicas

- Los nombres de documentos de balanza y paquete se sincronizan con el periodo.
- El mapeo y calculos formulan referencias por codigo y validan ciclos.
- Los indicadores de emision son informativos y no bloquean la emision.
