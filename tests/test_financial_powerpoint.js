const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const JSZip = require('jszip');

function snapshot() {
  const keys = [
    'revenue', 'portfolio_income', 'other_income', 'expenses', 'financial_expenses',
    'personnel', 'general', 'provisions', 'depreciation', 'tax', 'operating', 'net',
    'cash', 'gross_portfolio', 'net_portfolio', 'assets', 'liabilities', 'equity',
    'equity_result', 'portfolio_change',
  ];
  const months = Array.from({length: 13}, (_, i) => {
    const date = new Date(Date.UTC(2025, 9 + i, 1));
    return {key: date.toISOString().slice(0, 7), label: `Mes ${i + 1}`, source: 'Balanza de prueba'};
  });
  const labels = Object.fromEntries(keys.map(key => [key, key]));
  const series = Object.fromEntries(keys.map(key => [key, months.map((_, i) => 1000 + i * 100)]));
  Object.assign(series, {
    assets: months.map((_, i) => 20000 + i * 100),
    liabilities: months.map((_, i) => 12000 + i * 50),
    equity: months.map((_, i) => 8000 + i * 50),
    net: months.map((_, i) => 100 + i),
    cash: months.map((_, i) => 5000 + i * 100),
    portfolio_change: months.map((_, i) => 100 + i),
  });
  const ytd = Object.fromEntries(keys.map(key => [key, 10000]));
  const balanceRow = (key, section) => ({
    key, label: key, section, values: [1000, 1100, 1200],
    variation: {amount: 100, percent: 9.09},
  });
  return {
    version: 1, scale: 1000,
    meta: {company: 'Empresa de prueba', currency: 'NIO', cutoff: '2026-10-31', scope: 'Consolidado'},
    months, labels, series, ytd, prior_ytd: ytd,
    branches: [{label: 'Sucursal de prueba', monthly: ytd, ytd, series: series.net}],
    balance_summary: {
      dates: ['2025-10', '2025-12', '2026-10'], base_date: '2025-12',
      rows: [balanceRow('assets', true), balanceRow('liabilities', true), balanceRow('equity', true)],
    },
    findings: ['Hallazgo de prueba'], warnings: [], comments: '',
    reconciliation: {equity_difference: 0}, definitions: ['Definición de prueba'],
  };
}

test('genera un PowerPoint editable con tablas y gráficos', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mfi-pptx-test-'));
  try {
    const source = path.join(directory, 'datos.json');
    const target = path.join(directory, 'informe.pptx');
    fs.writeFileSync(source, JSON.stringify(snapshot()));
    execFileSync(process.execPath, [path.resolve(__dirname, '../scripts/informe_financiero.cjs'), source, target]);
    const archive = await JSZip.loadAsync(fs.readFileSync(target));
    assert.ok(archive.file('ppt/presentation.xml'));
    assert.ok(archive.file('ppt/slides/slide1.xml'));
    assert.ok(Object.keys(archive.files).filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name)).length >= 12);
    assert.ok(Object.keys(archive.files).some(name => /^ppt\/charts\/chart\d+\.xml$/.test(name)));
  } finally {
    fs.rmSync(directory, {recursive: true, force: true});
  }
});
