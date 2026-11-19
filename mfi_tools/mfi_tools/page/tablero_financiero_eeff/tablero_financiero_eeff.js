frappe.pages['tablero-financiero-eeff'].on_page_load = function(wrapper) {
  wrapper.jd = new MfiFinancialDashboard(wrapper);
};
frappe.pages['tablero-financiero-eeff'].on_page_show = function(wrapper) {
  if (wrapper.jd?.data && !wrapper.jd.charts.length) wrapper.jd.render();
};
frappe.pages['tablero-financiero-eeff'].on_page_hide = function(wrapper) {
  wrapper.jd?.disposeCharts();
};

class MfiFinancialDashboard {
  constructor(wrapper) {
    this.page = frappe.ui.make_app_page({parent:wrapper,title:'Tablero financiero',single_column:true});
    this.api='mfi_tools.mfi_tools.page.tablero_financiero_eeff.financial_report.';
    this.charts=[];this.sequence=0;this.notes=new Map();this.scale=1000;
    this.$root=$('<div class="mfi-financial" aria-live="polite"></div>').appendTo(this.page.main);
    this.page.set_primary_action('Generar PowerPoint',()=>this.export());
    this.page.set_secondary_action('Actualizar',()=>this.ready?this.load(true):this.init());
    this.disableExport(true);
    this.page.add_menu_item('Pantalla completa',()=>this.fullscreen());
    this.init();
  }
  escape(v) { return frappe.utils.escape_html(String(v??'')); }
  unit() {
    const currency=this.data?.meta.currency || this.currency.get_value();
    return (this.scale===1000?'Miles de ':this.scale===1000000?'Millones de ':'')+(currency==='NIO'?'C$':currency);
  }
  number(v,ratio=false) {
    if(v===null||v===undefined||!Number.isFinite(Number(v))) return 'Sin datos';
    return new Intl.NumberFormat('es-NI',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(v)/(ratio?1:this.scale))+(ratio?'%':'');
  }
  disableExport(disabled) {this.page.btn_primary?.prop('disabled',disabled);}
  async call(method,args) {return (await frappe.call({method:this.api+method,args,type:method==='generate_powerpoint'?'POST':'GET'})).message;}
  async init() {
    this.$root.html('<div class="mfi-eeff-loading" role="status">Preparando el tablero…</div>');
    try {
      const [options] = await Promise.all([this.call('get_options'),frappe.require('/assets/mfi_tools/vendor/echarts-6.1.0.min.js')]);
      this.options=options;
      if(!options.companies.length) throw new Error('No hay balanzas EEFF disponibles para tu usuario.');
      this.company=this.page.add_field({fieldname:'jd_company',label:'Empresa',fieldtype:'Select',
        options:options.companies.map(x=>x.name),default:options.companies[0].name,
        change:()=>{if(this.ready){this.updateCurrencies();this.load();}}});
      this.cutoff=this.page.add_field({fieldname:'jd_month',label:'Mes de corte',fieldtype:'Data',default:options.default_cutoff.slice(0,7),change:()=>{if(this.ready){this.updateCurrencies(true);this.load();}}});
      this.cutoff.$input.attr({type:'month',max:options.default_cutoff.slice(0,7),min:'2000-01','aria-label':'Mes de corte'});
      this.currency=this.page.add_field({fieldname:'jd_currency',label:'Moneda',fieldtype:'Select',
        options:options.companies[0].currencies,default:options.companies[0].currencies[0],change:()=>{if(this.ready)this.load();}});
      this.units=this.page.add_field({fieldname:'jd_scale',label:'Importes',fieldtype:'Select',options:['Miles','Unidades','Millones'],default:'Miles',
        change:()=>{this.scale={'Unidades':1,'Miles':1000,'Millones':1000000}[this.units.get_value()];if(this.data)this.render();}});
      this.updateCurrencies();this.ready=true;await this.load();
    } catch(e) {this.error(e);}
  }
  updateCurrencies(keepSelection=false) {
    const was=this.ready;this.ready=false;
    const company=this.options.companies.find(item=>item.name===this.company.get_value());
    const cutoff=this.cutoff.get_value();
    const keys=Object.keys(company.periods).filter(key=>key<=cutoff).sort().reverse();
    const reference=company.periods[keys[0]];
    const defaultCurrency=reference?.base || company.currencies[0];
    // Offer currencies available within the displayed thirteen-month window.
    const firstMonth=String(Number(cutoff.slice(0,4))-1)+cutoff.slice(4);
    const currencies=new Set([defaultCurrency]);
    for(const key of keys.filter(key=>key>=firstMonth)){
      for(const value of company.periods[key].currencies) currencies.add(value);
    }
    const current=this.currency.get_value();
    const selected=keepSelection && current!==this.baseCurrency && currencies.has(current)?current:defaultCurrency;
    this.baseCurrency=defaultCurrency;
    this.currencyChoices=[...currencies];
    this.currency.df.options=this.currencyChoices;
    this.currency.refresh();this.currency.set_value(selected);
    this.ready=was;
  }
  noteKey() {return this.data?JSON.stringify([this.data.meta.company,this.data.meta.cutoff,this.data.meta.currency]):'';}
  rememberNotes() {const input=this.$root.find('.mfi-eeff-comments');if(input.length&&this.data)this.notes.set(this.noteKey(),input.val());}
  async load(refresh=false) {
    if(!this.ready)return;
    const company=this.company.get_value(), currency=this.currency.get_value();
    const choices=this.currencyChoices;
    if(!currency || !choices?.includes(currency)) return;
    const month=this.cutoff.get_value();
    if(!/^\d{4}-\d{2}$/.test(month)||month>this.options.default_cutoff.slice(0,7)){
      ++this.sequence;
      this.rememberNotes();this.data=null;this.disableExport(true);this.disposeCharts();
      this.$root.html('<div class="mfi-eeff-error">Selecciona un mes anterior al mes actual.</div>');return;
    }
    this.rememberNotes();const seq=++this.sequence;this.data=null;this.disableExport(true);this.disposeCharts();
    this.$root.html('<div class="mfi-eeff-loading" role="status">Consultando los 13 meses y sus comparativos…</div>');
    try {
      const data=await this.call('get_dashboard',{company,currency,cutoff:month+'-01'});
      if(seq!==this.sequence)return;
      this.data=data;this.render();this.disableExport(!data.months.some(month=>month.available));
    } catch(e){if(seq===this.sequence)this.error(e);}
  }
  error(e) {
    this.data=null;this.disposeCharts();this.disableExport(true);
    this.$root.empty().append($('<div class="mfi-eeff-error" role="alert">').text(e?.message || 'No se pudo consultar la balanza EEFF. Pulsa Actualizar para volver a intentar.'));
    console.error('Tablero financiero:',e?.message||'Error de consulta');
  }
  disposeCharts() {this.observer?.disconnect();this.charts.forEach(c=>c.dispose());this.charts=[];}
  render() {
    if(!this.data)return;this.rememberNotes();this.disposeCharts();const d=this.data,s=d.series;
    const c=(k,title=null,ytd=false)=>{
      const val=ytd?d.ytd.net:s[k]?.[12];
      const diff=ytd?(d.ytd.net!==null&&d.prior_ytd.net!==null?d.ytd.net-d.prior_ytd.net:null):d.comparisons[k]?.mom.amount;
      const ratio=k==='margin';
      return `<article class="mfi-eeff-kpi"><div class="mfi-eeff-kpi-label">${this.escape(title||d.labels[k])}</div><div class="mfi-eeff-kpi-value">${this.number(val,ratio)}</div><div class="mfi-eeff-kpi-change">${diff===null||diff===undefined?'Comparación no disponible':`${diff>=0?'+':''}${ratio?this.number(diff,true).replace(/%$/,''):this.number(diff)}${ratio?' puntos porcentuales':''}`}<span>${ytd?'vs. acumulado del año anterior':'vs. mes anterior'}</span></div></article>`;
    };
    const cutoffPeriod=d.months[12];
    const rateLabel=cutoffPeriod.exchange_rate && cutoffPeriod.source_currency!==d.meta.currency
      ? ` · 1 ${this.escape(d.meta.currency)} = ${this.escape(cutoffPeriod.exchange_rate)} ${this.escape(cutoffPeriod.source_currency)}` : '';
    this.$root.html(`<header class="mfi-eeff-heading"><img src="/assets/mfi_tools/images/mfi-tools.svg" alt="MFI Tools"><div><p class="mfi-eeff-eyebrow">TABLERO FINANCIERO</p><h2>${this.escape(d.months[12].label)}</h2><p>${this.escape(d.months[0].label)} – ${this.escape(d.months[12].label)} · 13 meses · ${this.escape(d.meta.scope)}</p></div><span class="mfi-eeff-unit">${this.unit()}</span></header>
      <div class="mfi-eeff-status">Corte: ${this.escape(d.meta.cutoff)} · Balanza EEFF · ${this.escape(d.meta.company)}${rateLabel} · Consultado: ${this.escape(d.meta.generated_at.slice(0,16))}</div>
      ${d.warnings.length?`<details class="mfi-eeff-warnings" open><summary>${d.warnings.length} observación${d.warnings.length===1?'':'es'} para revisión</summary><ul>${d.warnings.map(x=>`<li>${this.escape(x)}</li>`).join('')}</ul></details>`:''}
      <section class="mfi-eeff-kpis" aria-label="Indicadores principales">${c('net')}${c('net','Resultado acumulado del año',true)}${c('gross_portfolio')}${c('cash')}${c('equity')}${c('margin')}</section>
      <nav class="mfi-eeff-section-links" aria-label="Secciones del tablero"><a href="#mfi-eeff-results">Resultados</a><a href="#mfi-eeff-balance">Balance y cartera</a><a href="#mfi-eeff-branches">Sucursales</a><a href="#mfi-eeff-cashflow">Liquidez</a><a href="#mfi-eeff-discussion">Puntos para discusión</a></nav>
      <section id="mfi-eeff-results"><h3>Resultados de los últimos 13 meses</h3><div class="mfi-eeff-chart-grid">${this.panel('results','Ingresos, gastos y resultado neto',true)}${this.panel('income','Composición de ingresos')}${this.panel('expenses','Composición de gastos')}</div></section>
      <section id="mfi-eeff-balance"><h3>Situación financiera y cartera</h3><div class="mfi-eeff-chart-grid">${this.panel('balance','Activos, pasivos y patrimonio',true)}${this.panel('portfolio','Cartera bruta y neta')}${this.panel('growth','Variación mensual de cartera')}</div>
      <details class="mfi-eeff-detail"><summary>Balance resumido y comparativos</summary>${this.balanceTable()}</details></section>
      <section id="mfi-eeff-branches"><h3>Resultados por sucursal</h3><div class="mfi-eeff-chart-grid">${d.branches.length?this.panel('branches','Resultado neto mensual por sucursal',true):'<p>Las balanzas disponibles solo presentan el consolidado.</p>'}</div>${this.branchTable()}</section>
      <section id="mfi-eeff-cashflow"><h3>Liquidez</h3><p class="mfi-eeff-footnote">Saldo de efectivo al cierre de cada mes · 13 meses · ${this.unit()}</p><div class="mfi-eeff-chart-grid">${this.panel('cash','Efectivo disponible al cierre',true)}</div><p class="mfi-eeff-footnote">${this.escape(this.cashBalanceChange())}</p></section>
      <section id="mfi-eeff-discussion" class="mfi-eeff-discussion"><h3>Puntos para discusión</h3><ul>${d.findings.map(t=>`<li>${this.escape(t)}</li>`).join('')}</ul><label for="mfi-eeff-comments">Comentarios de Gerencia para esta presentación</label><textarea id="mfi-eeff-comments" class="mfi-eeff-comments" rows="4" maxlength="5000" placeholder="Explicaciones de variaciones, acuerdos o asuntos para la Junta Directiva…"></textarea><p class="mfi-eeff-footnote">Se incluirán al generar el PowerPoint.</p></section>
      <details class="mfi-eeff-detail"><summary>Definiciones y fuentes</summary><ul>${d.definitions.map(t=>`<li>${this.escape(t)}</li>`).join('')}</ul><p>Fuente: Balanzas de comprobación EEFF de ${this.escape(d.meta.company)}.</p></details>
      <footer class="mfi-eeff-footer"><button class="btn btn-primary mfi-eeff-export">Generar PowerPoint</button><span>Presentación editable · mismo corte y cifras de esta vista</span></footer>`);
    this.$root.find('.mfi-eeff-comments').val(this.notes.get(this.noteKey())||'');
    this.$root.find('.mfi-eeff-export').prop('disabled',!d.months.some(month=>month.available)).on('click',()=>this.export());
    this.$root.find('[data-table]').on('click',e=>this.tableDialog(e.currentTarget.dataset.table));
    this.$root.find('[data-report]').on('click',e=>this.openReport(e.currentTarget.dataset.report));
    this.$root.find('.mfi-eeff-section-links a').on('click',e=>{e.preventDefault();this.$root.find(e.currentTarget.getAttribute('href'))[0]?.scrollIntoView({behavior:'smooth',block:'start'});});
    this.drawCharts();
  }
  panel(id,title,wide=false) {
    return `<article class="mfi-eeff-panel ${wide?'mfi-eeff-wide':''}"><div class="mfi-eeff-panel-heading"><h4>${title}</h4><div><button class="mfi-eeff-text-button" data-table="${id}" aria-label="Ver datos: ${title}">Ver datos</button><button class="mfi-eeff-text-button" data-report="${id}" aria-label="Abrir reporte: ${title}">Abrir reporte</button></div></div><div class="mfi-eeff-chart-scroll" tabindex="0" aria-label="Gráfico desplazable: ${title}"><div class="mfi-eeff-chart" data-chart="${id}" role="img" aria-label="${title}, últimos trece meses"></div></div></article>`;
  }
  cashBalanceChange() {
    const cash=this.data.series.cash,month=this.data.months[12].label;
    if(cash?.[12]==null||cash?.[11]==null)return 'Variación del saldo de efectivo: sin datos verificables.';
    const change=Math.round((cash[12]-cash[11])*100)/100;
    return change===0?`En ${month}, el saldo de efectivo no varió respecto al mes anterior.`:
      `En ${month}, el efectivo ${change<0?'disminuyó':'aumentó'} ${this.number(Math.abs(change))} ${this.unit()} respecto al mes anterior.`;
  }
  chartSpecs() {return {
    results:[['revenue','bar'],['expenses','bar'],['net','line']],
    income:[['portfolio_income','bar','income'],['other_income','bar','income'],['revenue','line']],
    expenses:[['personnel','bar','expenses'],['financial_expenses','bar','expenses'],['general','bar','expenses'],['provisions','bar','expenses'],['depreciation','bar','expenses'],['tax','bar','expenses'],['expenses','line']],
    balance:[['assets','bar'],['liabilities','bar','funding'],['equity','bar','funding']],
    portfolio:[['gross_portfolio','line'],['net_portfolio','line']],growth:[['portfolio_change','bar']],
    cash:[['cash','line']]
  };}
  drawCharts() {
    const d=this.data;const colors=['#0070c0','#c0504d','#00b050','#8064a2','#a5a5a5','#f79646'];
    const palettes={income:['#0070c0','#a5a5a5','#00b050'],expenses:['#a5a5a5','#0070c0','#ffc000','#b44443','#f79646','#8064a2','#c0504d'],
      portfolio:['#0070c0','#00b050'],cash:['#00b050']};
    const contrast=color=>{const rgb=color.slice(1).match(/../g).map(hex=>parseInt(hex,16));return (rgb[0]*299+rgb[1]*587+rgb[2]*114)/1000>150?'#19324e':'#fff';};
    const specs=this.chartSpecs();
    this.$root.find('[data-chart]').each((_,el)=>{
      const id=el.dataset.chart;const chart=echarts.init(el,null,{renderer:'svg'});this.charts.push(chart);
      const palette=palettes[id]||colors;
      let descriptors=id==='branches'?d.branches.map((b,i)=>['branch_'+i,'line']):specs[id];
      const names=Object.fromEntries(descriptors.map(([k])=>[k,k.startsWith('branch_')?d.branches[Number(k.slice(7))].label:d.labels[k]]));
      const values=Object.fromEntries(descriptors.map(([k])=>[k,k.startsWith('branch_')?d.branches[Number(k.slice(7))].series:d.series[k]]));
      const source=d.months.map((m,i)=>Object.assign({month:m.label},Object.fromEntries(descriptors.map(([k])=>[k,values[k][i]===null?null:values[k][i]/this.scale]))));
      const labelNumber=new Intl.NumberFormat('es-NI',{useGrouping:true,maximumFractionDigits:this.scale===1000000?2:0});
      // Tiny stacked segments keep their exact values in the tooltip and data table.
      const stackMax=Math.max(1,...source.map(row=>descriptors.reduce((sum,[key,,stack])=>sum+(stack?Math.abs(row[key]||0):0),0)));
      chart.setOption({animation:false,color:palette,aria:{enabled:true},dataset:{dimensions:['month',...descriptors.map(x=>x[0])],source},
        tooltip:{trigger:'axis',confine:true,valueFormatter:v=>v===null?'Sin datos':new Intl.NumberFormat('es-NI',{maximumFractionDigits:2}).format(v)+' '+this.unit()},
        legend:{bottom:0,type:'scroll',textStyle:{fontSize:12,color:'#44566d'}},
        grid:{top:44,right:32,left:68,bottom:id==='expenses'?90:75},
        xAxis:{type:'category',axisLabel:{fontSize:11,interval:0,rotate:35,formatter:v=>v.replace(' 20',' ')},axisTick:{alignWithLabel:true}},
        yAxis:{type:'value',name:this.unit(),nameTextStyle:{fontSize:11},axisLabel:{fontSize:11},splitLine:{lineStyle:{color:'#edf1f6'}}},
        series:descriptors.map(([key,type,stack],i)=>({name:names[key],type,stack,encode:{x:'month',y:key},connectNulls:false,
          symbol:'circle',symbolSize:5,z:type==='line'?5:2,barCategoryGap:'18%',barGap:'8%',lineStyle:{width:3},emphasis:{focus:'series',label:{show:true}},
          label:{show:true,position:stack?'inside':type==='line'&&i%2?'bottom':'top',distance:6,fontSize:stack||id==='balance'?10:11,
            color:stack?contrast(palette[i%palette.length]):'#19324e',fontWeight:600,textBorderColor:stack?'transparent':'#fff',textBorderWidth:stack?0:3,
            ...(type==='line'&&['results','income','expenses'].includes(id)?{fontWeight:700,textBorderWidth:0,backgroundColor:'#fff',borderColor:palette[i%palette.length],borderWidth:1,padding:[2,4]}:{}),
            formatter:p=>{const value=p.value[key];return value==null||value===0||(stack&&Math.abs(value)<stackMax*.035)?'':labelNumber.format(value);}},
          labelLayout:p=>({hideOverlap:true,...(type==='bar'&&!stack&&source[p.dataIndex]?.[key]<0?
            {y:p.rect.y+p.rect.height+6,verticalAlign:'top'}:{})}),
          ...(id==='growth'?{itemStyle:{color:p=>(p.value[key]??0)<0?'#c0504d':'#0070c0'}}:{})}))});
    });
    this.observer=new ResizeObserver(()=>this.charts.forEach(c=>c.resize()));this.observer.observe(this.$root[0]);
  }
  table(headers,rows) {return `<div class="mfi-eeff-table-wrap" tabindex="0"><table class="mfi-eeff-table"><thead><tr>${headers.map(h=>`<th scope="col">${this.escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((v,i)=>i?`<td>${this.escape(v)}</td>`:`<th scope="row">${this.escape(v)}</th>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
  balanceTable() {
    const d=this.data,b=d.balance_summary;
    if(!b)return this.table(['Concepto',...d.balance_dates],d.balance_table.map(r=>[r.label,...r.values.map(v=>this.number(v))]));
    return `<p class="mfi-eeff-footnote">Variación respecto a diciembre de ${this.escape(b.base_date.slice(0,4))}.</p>`+
      this.table(['Concepto',...b.dates,'Var. '+this.unit(),'Var. %'],b.rows.map(r=>[r.label,...r.values.map(v=>this.number(v)),this.number(r.variation.amount),this.number(r.variation.percent,true)]));
  }
  branchTable() {
    const d=this.data;

    const consolidated={label:'Consolidado',monthly:Object.fromEntries(Object.entries(d.series).map(([key,values])=>[key,values[12]])),ytd:d.ytd};
    const columns=[...d.branches,consolidated],count=columns.length;
    const cellClass=n=>[n<count*2-1?'mfi-eeff-branch-divider':'',n===count-1?'mfi-eeff-period-divider':'',n%count===count-1?'mfi-eeff-consolidated':''].filter(Boolean).join(' ');
    const definitions=[['','Ingresos','section'],['portfolio_income','Por cartera de crédito'],['other_income','Otros ingresos'],
      ['revenue','Total ingresos','income'],['','Gastos','section'],['financial_expenses','Financieros y cambiarios'],
      ['personnel','Personal'],['general','Generales'],['before_provision','Gastos antes de provisión*','subtotal'],
      ['operating','Resultado operativo*','result'],['provisions','Provisiones y saneamientos'],['depreciation','Depreciación y amortización'],
      ['tax','Impuesto a la renta'],['expenses','Total gastos','expense'],['net','Resultado neto','result']];
    const rows=definitions.map(([key,label,kind])=>{
      const values=['monthly','ytd'].flatMap(period=>columns.map(b=>{
        const parts=(key==='before_provision'?['financial_expenses','personnel','general']:[key]).map(k=>b[period]?.[k]??null);
        return parts.some(v=>v==null)?null:Math.round(parts.reduce((sum,v)=>sum+v,0)*100)/100;
      }));
      return `<tr data-kind="${kind||'detail'}" data-result-key="${key}"><th scope="row">${this.escape(label)}</th>${
        values.map((v,n)=>`<td class="${kind==='result'&&v<0?'mfi-eeff-negative ':''}${cellClass(n)}">${kind==='section'?'':this.number(v)}</td>`).join('')}</tr>`;
    }).join('');
    return `<p class="mfi-eeff-footnote">Mes: ${this.escape(d.months[12].label)} · Acumulado: enero al mes de corte de ${this.escape(d.meta.cutoff.slice(0,4))} · ${this.unit()}</p>
      <div class="mfi-eeff-table-wrap" tabindex="0"><table class="mfi-eeff-table mfi-eeff-branch-results"><thead><tr><th scope="col" rowspan="2">Concepto</th>${
        ['Del mes actual','Acumulado'].map((label,n)=>`<th scope="colgroup" colspan="${count}" class="${n===0?'mfi-eeff-period-divider':''}">${label}</th>`).join('')}</tr><tr>${
        [...columns,...columns].map((b,n)=>`<th scope="col" class="${cellClass(n)}">${this.escape(b.label)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
      <p class="mfi-eeff-footnote">* Antes de provisiones, depreciación e IR. El consolidado corresponde al ámbito seleccionado. «Sin datos» indica que no hay información verificable para el período.</p>`;
  }
  tableDialog(id) {
    const d=this.data;let rows;
    if(id==='branches')rows=d.branches.map(b=>[b.label,...b.series.map(v=>this.number(v))]);
    else rows=this.chartSpecs()[id].map(([key])=>[d.labels[key],...d.series[key].map(v=>this.number(v))]);
    const dialog=new frappe.ui.Dialog({title:'Datos de los 13 meses · '+this.unit(),size:'extra-large',fields:[{fieldtype:'HTML',fieldname:'data'}]});
    dialog.fields_dict.data.$wrapper.html(this.table(['Concepto',...d.months.map(m=>m.label)],rows));dialog.show();
  }
  openReport() {
    const source=this.data.months[12].source;
    if(source) return frappe.set_route('Form','Balanza Comprobacion EEFF',source);
    frappe.route_options={company:this.data.meta.company};
    frappe.set_route('List','Balanza Comprobacion EEFF');
  }
  async export() {
    if(!this.data||this.exporting)return;this.exporting=true;this.disableExport(true);this.$root.find('.mfi-eeff-export').prop('disabled',true).text('Generando…');
    this.rememberNotes();const data=this.data;
    try {
      const r=await this.call('generate_powerpoint',{company:data.meta.company,currency:data.meta.currency,cutoff:data.meta.cutoff,snapshot_id:data.snapshot_id,comments:this.notes.get(this.noteKey())||'',scale:String(this.scale)});
      const bytes=Uint8Array.from(atob(r.content),char=>char.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.presentationml.presentation'}));
      const a=document.createElement('a');a.href=url;a.download=`Informe-financiero-${frappe.scrub(data.meta.company)}-${data.meta.cutoff.slice(0,7)}-${data.meta.currency}.pptx`;
      document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
      frappe.show_alert({message:'Presentación generada con el corte '+r.cutoff,indicator:'green'},8);
    } catch (error) {
      frappe.show_alert({message:'No se pudo generar la presentación. Revisa el mensaje del servidor.',indicator:'red'},8);
    } finally {this.exporting=false;this.disableExport(!this.data);this.$root.find('.mfi-eeff-export').prop('disabled',false).text('Generar PowerPoint');}
  }
  async fullscreen() {
    if(document.fullscreenElement)await document.exitFullscreen();else await this.page.wrapper[0].requestFullscreen();
    this.charts.forEach(c=>c.resize());
  }
}
