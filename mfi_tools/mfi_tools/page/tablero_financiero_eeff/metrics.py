"""Pure monthly calculations for the board dashboard (no database writes)."""
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

MONTHS = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')
METRICS = {
    'revenue': 'Ingresos totales', 'portfolio_income': 'Ingresos de cartera',
    'other_income': 'Otros ingresos', 'expenses': 'Gastos totales',
    'financial_expenses': 'Gastos financieros y cambiarios', 'personnel': 'Personal',
    'general': 'Otros gastos operativos', 'provisions': 'Provisiones y saneamientos',
    'depreciation': 'Depreciación y amortización', 'tax': 'Impuesto a la renta',
    'operating': 'Resultado antes de provisiones, depreciación e IR', 'net': 'Resultado neto',
    'cash': 'Disponibilidades', 'gross_portfolio': 'Cartera bruta',
    'net_portfolio': 'Cartera neta', 'portfolio_allowance': 'Provisiones de cartera',
    'assets': 'Activos', 'liabilities': 'Pasivos', 'equity': 'Patrimonio',
    'equity_result': 'Resultado del ejercicio en patrimonio',
    'portfolio_change': 'Variación mensual de cartera', 'margin': 'Margen neto (%)',
    'efficiency': 'Gastos / ingresos (%)', 'capital_ratio': 'Patrimonio / activos (%)',
    'cf_operating': 'Flujo de operación', 'cf_investing': 'Flujo de inversión',
    'cf_financing': 'Flujo de financiamiento', 'cf_exchange': 'Efecto cambiario en efectivo',
    'cf_opening': 'Efectivo inicial', 'cf_closing': 'Efectivo final',
}
FLOW_KEYS = ('revenue', 'portfolio_income', 'other_income', 'expenses', 'financial_expenses',
             'personnel', 'general', 'provisions', 'depreciation', 'tax', 'operating', 'net')


def money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def month_shift(d, offset):
    n = d.year * 12 + d.month - 1 + offset
    return date(n // 12, n % 12 + 1, 1)


def month_end(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def last_closed(today):
    # User's reporting convention: previous calendar month, not a fiscal-year PCV.
    return month_end(month_shift(today, -1))


def reporting_months(cutoff, count=13):
    return [dict(key=(d := month_shift(cutoff, n)).strftime('%Y-%m'),
                 label=f'{MONTHS[d.month - 1]} {d.year}',
                 from_date=d.isoformat(), to_date=month_end(d).isoformat())
            for n in range(1-count, 1)]


def ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0: return None
    return round(numerator / denominator * 100, 2)


def variation(current, previous):
    if current is None or previous is None: return {'amount': None, 'percent': None}
    amount = money(Decimal(str(current)) - Decimal(str(previous)))
    # A negative/zero comparison base makes conventional percentage growth misleading.
    return {'amount': amount, 'percent': round(amount/previous*100, 2) if previous > 0 else None}


def summarize_balance(balances, cutoff):
    """Compact MUC balance: every component once; variation against prior December."""
    base = f'{cutoff.year-1}-12'
    current = cutoff.strftime('%Y-%m')
    dates = list(dict.fromkeys([f'{cutoff.year-1}-{cutoff.month:02d}', base, current]))
    definitions = [
        ('assets', 'Activos', ('assets',), True, False),
        ('cash', 'Disponibilidades', ('cash',), False, False),
        ('net_portfolio', 'Cartera de créditos (neta)', ('net_portfolio',), False, False),
        ('receivables', 'Otras cuentas por cobrar', ('receivables',), False, False),
        ('fixed_assets', 'Inmuebles, mobiliario y equipo (neto)', ('fixed_assets',), False, False),
        ('other_assets', 'Otros activos e inversiones', ('investments','foreclosed','permanent_investments','other_assets'), False, False),
        ('liabilities', 'Pasivos', ('liabilities',), True, False),
        ('financing', 'Obligaciones financieras', ('financial_obligations','institutional_financing'), False, False),
        ('payables', 'Otras cuentas por pagar', ('payables',), False, False),
        ('liability_provisions', 'Provisiones', ('liability_provisions',), False, False),
        ('other_liabilities', 'Otros pasivos y deuda subordinada', ('other_liabilities','subordinated_debt'), False, True),
        ('equity', 'Patrimonio', ('equity',), True, False),
        ('capital', 'Capital social / Aportes', ('capital','additional_capital'), False, False),
        ('other_equity', 'Reservas y ajustes al patrimonio', ('equity_adjustments','reserves'), False, True),
        ('retained_earnings', 'Resultados acumulados', ('retained_earnings',), False, False),
        ('equity_result', 'Resultado del ejercicio', ('equity_result',), False, False),
    ]
    rows = []
    for key, label, components, section, hide_empty in definitions:
        values = []
        for period in dates:
            amounts = [balances.get(k, {}).get(period) for k in components]
            values.append(None if any(v is None for v in amounts) else money(sum(Decimal(str(v)) for v in amounts)))
        if hide_empty and all(v == 0 for v in values):
            continue
        rows.append(dict(key=key, label=label, section=section, values=values,
                         variation=variation(values[dates.index(current)], values[dates.index(base)])))
    return dict(dates=dates, base_date=base, rows=rows)
