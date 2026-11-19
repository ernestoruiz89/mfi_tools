/* Editable board presentation. Input comes exclusively from a server-side snapshot. */
const fs=require('node:fs');
const PptxGenJS=require('pptxgenjs');
const JSZip=require('jszip');

const monthLabel=key=>/^\d{4}-\d{2}$/.test(key||'')?`${['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][Number(key.slice(5))-1]}-${key.slice(2,4)}`:String(key||'');
const difference=(current,previous)=>current==null||previous==null?{amount:null,percent:null}:
  {amount:Math.round((current-previous)*100)/100,percent:previous>0?(current-previous)/previous*100:null};
const RESULT_ROWS=[
  ['', 'Ingresos','section'],['portfolio_income','Por cartera de crédito'],['other_income','Otros ingresos'],
  ['revenue','Total ingresos','income'],['','Gastos','section'],
  ['financial_expenses','Financieros y cambiarios'],['personnel','Personal'],['general','Generales'],
  ['before_provision','Gastos antes de provisión*','subtotal'],['operating','Resultado operativo*','result'],
  ['provisions','Provisiones y saneamientos'],['depreciation','Depreciación y amortización'],['tax','Impuesto a la renta'],
  ['expenses','Total gastos','expense'],['net','Resultado neto','result']];
function branchResults(data,branches=data.branches) {
  const consolidated={monthly:Object.fromEntries(Object.entries(data.series).map(([key,values])=>[key,values[12]])),ytd:data.ytd};
  const columns=[...branches,consolidated];
  return RESULT_ROWS.map(([key,label,style])=>({key,label,style,values:!key?[]:['monthly','ytd'].flatMap(period=>columns.map(branch=>{
    const components=key==='before_provision'?['financial_expenses','personnel','general']:[key];
    const values=components.map(k=>branch[period]?.[k]??null);
    return values.some(v=>v==null)?null:Math.round(values.reduce((sum,v)=>sum+v,0)*100)/100;
  }))}));
}
function resultsSummary(data) {
  const year=Number(data.meta.cutoff.slice(0,4)),month=data.meta.cutoff.slice(5,7);
  const dates=[`${year-1}-${month}`,`${year-1}-12`,data.months[11].key,data.months[12].key];
  const at=(key,date)=>data.series[key]?.[data.months.findIndex(m=>m.key===date)]??null;
  const sum=(values)=>values.some(v=>v==null)?null:Math.round(values.reduce((n,v)=>n+v,0)*100)/100;
  const rows=RESULT_ROWS.map(([key,label,style])=>{
    if(!key)return {label,style,values:[]};
    const components=key==='before_provision'?['financial_expenses','personnel','general']:[key];
    const periods=dates.map(date=>sum(components.map(k=>at(k,date))));
    const change=difference(periods[3],periods[2]);
    const income=['portfolio_income','other_income','revenue','operating','net'].includes(key);
    return {key,label,style,change,favorable:change.amount==null||change.amount===0?null:income?change.amount>0:change.amount<0,
      values:[...periods,change.amount,change.percent,
        sum(components.map(k=>data.prior_ytd[k]??null)),sum(components.map(k=>data.ytd[k]??null))]};
  });
  return {dates,rows};
}
async function build(data,output) {
  if(data.version!==1||data.months?.length!==13)throw new Error('Expected 13 monthly periods');
  const ppt=new PptxGenJS();ppt.layout='LAYOUT_WIDE';ppt.author=data.meta.company;ppt.subject='Informe financiero';
  ppt.title=`Informe financiero ${data.meta.cutoff}`;ppt.company=data.meta.company; ppt.lang='es-NI';
  ppt.theme={headFontFace:'Arial',bodyFontFace:'Arial',lang:'es-NI'};
  const C={ink:'19324E',blue:'0070C0',orange:'F79646',green:'00B050',gray:'A5A5A5',red:'C0504D',purple:'8064A2',yellow:'FFC000'};
  const metricColors={revenue:C.blue,expenses:C.red,net:C.green,assets:C.blue,liabilities:C.red,equity:C.green,
    cf_operating:C.blue,cf_investing:C.gray,cf_financing:C.yellow,cash:C.green};
  const scale=data.scale||1000;const currency=data.meta.currency==='NIO'?'C$':data.meta.currency;
  const unit=(scale===1?'':scale===1000?'Miles de ':'Millones de ')+currency;
  const fmt=(v,percent=false)=>v==null?'Sin datos':new Intl.NumberFormat('es-NI',{minimumFractionDigits:percent?1:2,maximumFractionDigits:percent?1:2}).format(v/(percent?1:scale))+(percent?'%':'');
  const labels=data.months.map(m=>m.label.replace(' 20',' '));
  const meta=`${data.meta.company} · Balanza de comprobación EEFF · Corte ${data.meta.cutoff} · ${unit}`;
  const watermark=data.warnings?.length?'Incluye observaciones de conciliación':'Datos contabilizados';
  function text(s,value,options={}) {s.addText(String(value),{fontFace:'Arial',fontSize:17,color:C.ink,margin:0,breakLine:false,...options});}
  let slideCount=0;
  function slide(title,subtitle='') {
    const s=ppt.addSlide();s.background={color:'FFFFFF'};
    text(s,title,{x:.45,y:.32,w:11.7,h:.48,fontSize:27,bold:true});
    if(subtitle)text(s,subtitle,{x:.45,y:.9,w:12.2,h:.35,fontSize:12,color:'52657B'});
    text(s,meta,{x:.45,y:7.02,w:11.7,h:.18,fontSize:9,color:'52657B'});
    text(s,String(++slideCount),{x:12.25,y:7.02,w:.5,h:.18,fontSize:9,align:'right',color:'52657B'});
    s.addNotes(`Fuente: Balanza Comprobacion EEFF de ${data.meta.company}. ${data.months.map(month=>month.source || month.label+' (sin datos)').join(', ')}.\n${data.definitions.join('\n')}`);
    return s;
  }
  function table(s,headers,rows,options={}) {
    s.addTable([headers.map(x=>({text:String(x),options:{bold:true,color:'FFFFFF',fill:C.blue}})),
      ...rows.map(r=>r.map((x,i)=>({text:String(x),options:{align:i?'right':'left'}})))],
      {x:.48,y:1.45,w:12.35,h:4.85,fontFace:'Arial',fontSize:14,color:C.ink,border:{type:'solid',color:'DCE4ED',pt:.5},
       margin:[.065,.09,.065,.09],rowH:.38,fill:'FFFFFF',autoPage:false, ...options});
  }
  const compact=(value,percent=false)=>{
    if(value==null)return 'N/D';
    const digits=percent?1:scale===1000000?2:0;
    const n=value/(percent?1:scale);
    const amount=new Intl.NumberFormat('es-NI',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(Math.abs(n));
    if(percent)return (n<0&&Number(amount.replace(/,/g,''))!==0?'-':'')+amount+'%';
    return n<0&&Number(amount.replace(/,/g,''))!==0?`(${amount})`:amount;
  };
  function financialTable(s,headers,rows,{balance=false}={}) {
    const fills={section:'F0F2F5',income:'DAE8BC',subtotal:'FAD7AE',result:'D8EDF3',expense:'F0D8D8'};
    const variationFills={section:'E1E5EB',income:'C3D79F',subtotal:'EEC397',result:'BCDDE6',expense:'E1BBBB'};
    const body=rows.map(r=>[r.label,...r.values.map((v,i)=>compact(v,i===(balance?r.values.length-1:5)))].map((value,i)=>{
      const isVariation=!balance&&(i===5||i===6);
      const isChange=isVariation&&r.favorable!==undefined&&r.favorable!==null;
      const fill=balance&&r.section?'365F91':isVariation?(variationFills[r.style]||'F1F1F1'):(fills[r.style]||'FFFFFF');
      return {text:String(value),options:{align:i?'right':'left',bold:balance||Boolean(r.style),fill,
        color:balance&&r.section?'FFFFFF':isChange?(r.favorable?'146347':'A12A32'):'182C42',
        ...(i===0&&!r.style&&!r.section?{margin:[.04,.06,.04,.19]}:{})}};
    }));
    // Section rows span the same grid without inventing zero amounts.
    for(const row of body)while(row.length<headers.length)row.push({text:'',options:{fill:!balance&&(row.length===5||row.length===6)?variationFills.section:fills.section}});
    const widths=balance?[4.6,...Array(headers.length-1).fill((12.35-4.6)/(headers.length-1))]:[2.85,1.1,1.1,1.1,1.1,1.15,.95,1.5,1.5];
    const tableRows=[headers.map((value,i)=>({text:value,options:{bold:true,align:i?'center':'left',fill:!balance&&i===8?'F4AD52':!balance&&(i===5||i===6)?'FFD052':'FFF45C',color:'122A40'}})),...body];
    if(!balance){
      const border={type:'solid',color:'CAD3DC',pt:.4},divider={type:'solid',color:'808080',pt:1.8};
      for(const row of tableRows){
        row[4].options.border=[border,divider,border,border];
        row[5].options.border=[border,border,border,divider];
        row[6].options.border=[border,divider,border,border];
        row[7].options.border=[border,border,border,divider];
      }
    }
    s.addTable(tableRows,
      {x:.48,y:1.43,w:12.35,colW:widths,fontFace:'Arial',fontSize:balance?13:11.5,color:'182C42',
        rowH:balance?.30:.31,margin:[.045,.055,.045,.055],border:{type:'solid',color:balance?'FFFFFF':'CAD3DC',pt:.4},
        autoPage:false,fill:'FFFFFF',valign:'middle'});
  }
  function chart(s,specs,options={}) {
    const fallback=[C.blue,C.red,C.green,C.purple,C.gray,C.orange];
    const colors=options.chartColors||specs.map(([key],i)=>metricColors[key]||fallback[i%fallback.length]);
    const charts=specs.map(([key,type='bar',stack],i)=>({type,data:[{name:data.labels[key],labels,values:data.series[key].map(v=>v==null?null:v/scale)}],
      options:{chartColors:[colors[i]],...(type==='line'?{secondaryValAxis:true,secondaryCatAxis:true,lineSize:2.5,showMarker:true,markerSize:4}:{}),...(stack?{barGrouping:'stacked'}:{})}}));
    const values=specs.flatMap(([k])=>data.series[k].filter(v=>v!=null).map(v=>v/scale));
    const sumMax=Math.max(1,...data.months.map((_,i)=>specs.reduce((n,[k,type])=>n+(type==='line'?0:Math.max(0,(data.series[k][i]||0)/scale)),0)));
    const sumMin=Math.min(0,...data.months.map((_,i)=>specs.reduce((n,[k,type])=>n+(type==='line'?0:Math.min(0,(data.series[k][i]||0)/scale)),0)));
    const max=Math.max(...values,1);const min=Math.min(...values,0);
    const ceiling=(options.stacked?Math.max(sumMax,max):max)*1.15;
    const step=10**Math.floor(Math.log10(Math.max(ceiling-min,1)))/2;
    const bottom=options.stacked?Math.min(sumMin,min):min;
    const axis={valAxisMinVal:bottom<0?Math.floor(bottom*1.12/step)*step:0,valAxisMaxVal:Math.ceil(ceiling/step)*step,
      valAxisMajorUnit:step,valAxisLabelFormatCode:scale===1000000?'0.00':'#,##0'};
    const numberFormat=scale===1000000?'#,##0.00':'#,##0';
    const labelFormat=options.stacked?`[>=${(sumMax*.035).toFixed(6)}]${numberFormat};[<=-${(sumMax*.035).toFixed(6)}](${numberFormat});""`:`${numberFormat};(${numberFormat});""`;
    const config={x:.48,y:1.43,w:12.28,h:5.2,catAxisLabelFontSize:11,catAxisLabelRotate:35,valAxisLabelFontSize:11,
      showTitle:false,showLegend:true,legendPos:'b',legendFontSize:12,showValue:true,showBorder:false,
      showCatName:false,showShadow:false,barGapWidthPct:35,barOverlapPct:-8,chartColors:colors,
      valAxisTitle:unit,showLine:true,dataLabelPosition:options.stacked?'ctr':specs[0][1]==='line'?'t':'outEnd',
      dataLabelFontSize:10,dataLabelColor:options.stacked?'FFFFFF':C.ink,dataLabelFormatCode:labelFormat,
      catAxisLineColor:'B9C8D8',valAxisLineColor:'B9C8D8',valGridLine:{color:'E8EEF4',width:.6},
      chartArea:{fill:{color:'FFFFFF'},border:{color:'FFFFFF',pt:0}},
      showMarker:false,...axis,
      valAxes:[{...axis,valAxisTitle:unit},{...axis,valAxisLabelColor:'FFFFFF',valAxisLineColor:'FFFFFF',showValAxisTitle:false}],
      catAxes:[{catAxisLabelFontSize:11,catAxisLabelRotate:35},{catAxisHidden:true}],
      ...options};delete config.stacked;
    const types=new Set(specs.map(x=>x[1]||'bar'));
    if(types.size===1){
      delete config.valAxes;delete config.catAxes;
      config.barGrouping=options.stacked?'stacked':'clustered';
      s.addChart([...types][0],charts.flatMap(x=>x.data),config);
    }else {
      // One plot per type keeps grouped columns side by side instead of overlapping.
      const grouped=[...types].map(type=>({type,data:charts.filter(c=>c.type===type).flatMap(c=>c.data),
        options:{...charts.find(c=>c.type===type).options,
          chartColors:specs.map((spec,i)=>[spec,i]).filter(([spec])=>(spec[1]||'bar')===type).map(([,i])=>colors[i]),
          showValue:true,dataLabelPosition:type==='line'?'t':options.stacked?'ctr':'outEnd',dataLabelFontSize:options.dataLabelFontSize??(type==='bar'?9:11),
          dataLabelColor:type==='bar'&&options.stacked?'FFFFFF':C.ink,
          dataLabelFormatCode:options.stacked?(type==='line'?`${numberFormat};(${numberFormat});""`:labelFormat):labelFormat,
          ...(type==='bar'?{barGrouping:options.stacked?'stacked':'clustered',barGapWidthPct:35,barOverlapPct:options.stacked?100:-8}:{})}}));
      s.addChart(grouped,config);
    }
  }
  function balanceStructureChart(s) {
    // Two populated slots and one blank slot keep each month visually separate.
    const groupedLabels=[Array(39).fill(''),labels.flatMap(label=>[label,'',''])];
    const series=['assets','liabilities','equity'].map((key,i)=>({name:data.labels[key],labels:groupedLabels,
      values:data.series[key].flatMap(value=>{
        const amount=value==null?null:value/scale;
        return i===0?[amount,null,null]:[null,amount,null];
      })}));
    const upper=Math.max(1,...data.months.flatMap((_,i)=>[Math.max(0,data.series.assets[i]??0)/scale,
      (Math.max(0,data.series.liabilities[i]??0)+Math.max(0,data.series.equity[i]??0))/scale]));
    const lower=Math.min(0,...data.months.flatMap((_,i)=>[Math.min(0,data.series.assets[i]??0)/scale,
      (Math.min(0,data.series.liabilities[i]??0)+Math.min(0,data.series.equity[i]??0))/scale]));
    const magnitude=10**Math.floor(Math.log10((upper-lower)/6));
    const step=Math.ceil((upper-lower)/6/magnitude)*magnitude;
    const format=scale===1000000?'#,##0.00;(#,##0.00);""':'#,##0;(#,##0);""';
    s.addChart([
      {type:'bar',data:series,options:{barGrouping:'stacked',barGapWidthPct:0,barOverlapPct:100,
        chartColors:[C.blue,C.red,C.green],showValue:true,dataLabelPosition:'ctr',dataLabelColor:'FFFFFF',dataLabelFontSize:9}},
      // A label-only line puts the asset totals above the columns. Its value
      // reference is linked to the asset cells below, so edits stay in sync.
      {type:'line',data:[{...series[0],name:'__CE_ASSET_LABELS__'}],options:{showValue:true,
        dataLabelPosition:'t',dataLabelColor:C.ink,dataLabelFontSize:9,lineSize:0,showMarker:false}}
    ],{x:.48,y:1.43,w:12.28,h:5.2,barDir:'col',barGrouping:'stacked',barGapWidthPct:0,barOverlapPct:100,
      chartColors:[C.blue,C.red,C.green],showLegend:true,legendPos:'b',legendFontSize:12,
      showValue:true,dataLabelPosition:'ctr',dataLabelColor:'FFFFFF',dataLabelFontSize:9,dataLabelFontFace:'Arial Narrow',dataLabelFormatCode:format,
      catAxisMultiLevelLabels:true,catAxisLabelFrequency:'1',catAxisLabelFontSize:11,catAxisLabelRotate:35,catAxisLineColor:'B9C8D8',
      valAxisLabelFontSize:11,valAxisLabelFormatCode:scale===1000000?'#,##0.00':'#,##0',valAxisMinVal:Math.floor(lower*1.04/step)*step,
      valAxisMaxVal:Math.ceil(upper*1.04/step)*step,valAxisMajorUnit:step,valAxisLineColor:'B9C8D8',
      valGridLine:{color:'E8EEF4',width:.6},showTitle:false,showShadow:false,showBorder:false,
      chartArea:{fill:{color:'FFFFFF'},border:{color:'FFFFFF',pt:0}}});
  }
  let s=slide('Informe financiero');
  text(s,data.meta.company,{x:.65,y:1.6,w:2.4,h:1.25,fontSize:22,bold:true});
  text(s,data.months[12].label,{x:3.3,y:2.0,w:8.8,h:.75,fontSize:38,bold:true});
  text(s,`${data.months[0].label} a ${data.months[12].label}`,{x:3.3,y:2.95,w:8.7,h:.5,fontSize:22,color:'52657B'});
  text(s,data.meta.scope,{x:3.3,y:3.7,w:8.5,h:.45,fontSize:20});
  text(s,watermark,{x:3.3,y:4.4,w:8.7,h:.45,fontSize:15,color:data.warnings.length?'885E14':'52657B'});

  s=slide('Resumen ejecutivo',`${data.months[12].label} · Resultado del mes, acumulado anual y posición al cierre · ${unit}`);
  const executiveAmount=v=>v==null?'Sin datos':v<0?`(${fmt(Math.abs(v))})`:fmt(v);
  const signed=(v,percent=false)=>v==null?'N/D':`${v>0?'+':v<0?'−':''}${fmt(Math.abs(v),percent)}`;
  const changeText=change=>change.amount==null?'Comparación no disponible':
    `${signed(change.amount)}${change.percent==null?' (N/D %)':` (${signed(change.percent,true)})`}`;
  const changeColor=(key,amount)=>amount==null||amount===0?C.ink:
    ['net','revenue'].includes(key)?amount>0?C.green:C.red:
    key==='expenses'?amount<0?C.green:C.red:C.ink;
  const netChange=difference(data.series.net[12],data.series.net[11]);
  const annualChange=difference(data.ytd.net,data.prior_ytd.net);
  const year=data.meta.cutoff.slice(0,4),priorYear=String(Number(year)-1);
  const monthName=monthLabel(data.meta.cutoff.slice(0,7)).split('-')[0];
  [
    {x:.5,title:'RESULTADO NETO DEL MES',value:data.series.net[12],change:netChange,
      context:`Respecto a ${monthLabel(data.months[11].key)}`,
      prior:`${monthLabel(data.months[0].key)}: ${executiveAmount(data.series.net[0])}`},
    {x:7.0,title:`RESULTADO ACUMULADO ENE–${monthName.toUpperCase()} ${year}`,value:data.ytd.net,change:annualChange,
      context:`Respecto a Ene–${monthName} ${priorYear}`,
      prior:`Ene–${monthName} ${priorYear}: ${executiveAmount(data.prior_ytd.net)}`}
  ].forEach(item=>{
    text(s,item.title,{x:item.x,y:1.48,w:5.8,h:.26,fontSize:13,bold:true,color:'52657B'});
    const value=executiveAmount(item.value);
    text(s,value,{x:item.x,y:1.88,w:5.8,h:.62,fontSize:value.length>16?29:38,bold:true,color:item.value<0?C.red:C.ink});
    text(s,changeText(item.change),{x:item.x,y:2.63,w:5.8,h:.32,fontSize:17,bold:true,color:changeColor('net',item.change.amount)});
    text(s,item.context,{x:item.x,y:3.0,w:5.8,h:.22,fontSize:11,color:'52657B'});
    text(s,item.prior,{x:item.x,y:3.3,w:5.8,h:.25,fontSize:13,color:'52657B'});
  });
  const executiveHeaders=['Indicador',monthLabel(data.months[12].key),`Cambio vs. ${monthLabel(data.months[11].key)}`,monthLabel(data.months[0].key)];
  const executiveRows=['revenue','expenses','gross_portfolio','cash','equity'].map(key=>{
    const change=difference(data.series[key][12],data.series[key][11]);
    return [data.labels[key],executiveAmount(data.series[key][12]),changeText(change),executiveAmount(data.series[key][0])]
      .map((value,i)=>({text:value,options:{align:i?'right':'left',bold:i===1,color:i===2?changeColor(key,change.amount):C.ink,
        fill:i===1?'EDF4FA':'FFFFFF'}}));
  });
  s.addTable([executiveHeaders.map((value,i)=>({text:value,options:{bold:true,color:'FFFFFF',fill:'365F91',align:i?'right':'left'}})),...executiveRows],
    {x:.5,y:3.86,w:12.3,colW:[3.65,2.2,4.25,2.2],fontFace:'Arial',fontSize:15,rowH:.41,margin:[.075,.1,.075,.1],
      color:C.ink,border:{type:'solid',color:'DEE6EF',pt:.5},autoPage:false,valign:'middle'});
  const reconciliation=data.reconciliation?.equity_difference;
  const executiveNote=reconciliation!=null&&Math.abs(reconciliation)>.01?
    `Conciliación pendiente: diferencia entre resultado patrimonial y ER acumulado de ${executiveAmount(reconciliation)} ${unit}.`:
    data.warnings?.length?'Hay observaciones para revisión en «Puntos para discusión».':
    'N/D: variación porcentual no comparable sobre una base nula o negativa.';
  text(s,executiveNote,{x:.5,y:6.55,w:12.25,h:.3,fontSize:11,color:data.warnings?.length?'885E14':'52657B'});

  s=slide('Balance general (resumen)',`Saldos al cierre${data.balance_summary?' · Variación frente a '+monthLabel(data.balance_summary.base_date):''} · ${unit}`);
  if(data.balance_summary){
    const b=data.balance_summary;
    financialTable(s,['Balance general',...b.dates.map(monthLabel),'Var. '+currency,'Var. %'],
      b.rows.map(r=>({...r,values:[...r.values,r.variation.amount,r.variation.percent]})),{balance:true});
    text(s,'Otros activos incluye inversiones y bienes adjudicados. N/D: porcentaje no comparable sobre base nula o negativa.',{x:.5,y:6.62,w:12.2,h:.25,fontSize:10,color:'52657B'});
  }else {
    // Older saved snapshots remain exportable during the transition.
    table(s,['Concepto',...data.balance_dates],data.balance_table.map(r=>[r.label,...r.values.map(v=>fmt(v))]),{colW:[4.15,...data.balance_dates.map(()=>8.2/data.balance_dates.length)],fontSize:14});
  }

  s=slide('Evolución de la situación financiera','Activos, pasivos y patrimonio · 13 meses');
  chart(s,[['assets','line'],['liabilities','line'],['equity','line']],{showMarker:true,lineSize:2.5});

  s=slide('Activos, pasivos y patrimonio',`Activos frente a pasivos y patrimonio · 13 meses · ${unit}`);
  balanceStructureChart(s);

  s=slide('Variación mensual de la cartera','Cambio del principal de cartera frente al cierre anterior');
  chart(s,[['portfolio_change','bar']],{showLegend:false,chartColors:[C.blue],invertedColors:[C.red],showValue:true,dataLabelPosition:'outEnd',dataLabelFormatCode:'#,##0;(#,##0)',dataLabelColor:C.ink,dataLabelFontSize:12});

  const summary=resultsSummary(data);
  s=slide('Estado de resultados (resumen)',`Variación: ${monthLabel(summary.dates[3])} frente a ${monthLabel(summary.dates[2])} · Acumulados de enero al mes de corte · ${unit}`);
  financialTable(s,['Concepto',...summary.dates.map(monthLabel),'Var. '+currency,'Var. %',`Acumulado\n${monthLabel(summary.dates[0])}`,`Acumulado\n${monthLabel(summary.dates[3])}`],summary.rows);
  text(s,'* Antes de provisiones, depreciación e IR. Verde: variación favorable; rojo: desfavorable. Cifras redondeadas; N/D: no comparable.',{x:.5,y:6.62,w:12.2,h:.25,fontSize:10,color:'52657B'});

  const branchSubtitle=`Mes: ${data.months[12].label} · Acumulado: Ene–${monthName} ${year} · ${unit}`;
  if(data.branches.length) s=slide('Resultados por sucursal',branchSubtitle);
  const chunks=[];for(let i=0;i<data.branches.length;i+=3)chunks.push(data.branches.slice(i,i+3));

  chunks.forEach((chunk,i)=>{
    if(i)s=slide('Resultados por sucursal (continuación)',branchSubtitle);
    if(!chunk.length){text(s,'No hay movimientos por sucursal para este corte.',{x:.5,y:1.5,w:12.2,h:.5});return;}
    const fills={section:'F0F2F5',income:'DAE8BC',subtotal:'FAD7AE',result:'D8EDF3',expense:'F0D8D8'};
    const baseBorder={type:'solid',color:'CAD3DC',pt:.4};
    const count=chunk.length+1;
    const divider=n=>[baseBorder,{type:'solid',color:'808080',pt:n===count-1?2.2:1.2},baseBorder,baseBorder];
    const periodHeaders=[{text:'Concepto',options:{rowspan:2,bold:true,fill:'FFF45C'}},
      ...['Del mes actual','Acumulado'].map((label,n)=>({text:label,options:{colspan:count,align:'center',bold:true,fill:'FFF45C',...(n===0?{border:divider(count-1)}:{})}}))];
    const labels=[...chunk.map(b=>b.label),'Consolidado'];
    const branchHeaders=[...labels,...labels].map((label,n)=>({text:label,options:{align:'center',bold:true,fill:'FFF45C',
      ...(n<count*2-1?{border:divider(n)}:{})}}));
    const rows=branchResults(data,chunk).map(row=>[
      {text:row.label,options:{bold:Boolean(row.style),fill:fills[row.style]||'FFFFFF',margin:[.045,.055,.045,row.style?.055:.19]}},
      ...Array.from({length:count*2},(_,n)=>({text:row.style==='section'?'':compact(row.values[n]),
        options:{align:'right',bold:Boolean(row.style)||n%count===count-1,fill:fills[row.style]||(n%count===count-1?'F2F2F2':'FFFFFF'),
          color:row.style==='result'&&row.values[n]<0?C.red:C.ink,
          ...(n<count*2-1?{border:divider(n)}:{})}}))]);
    s.addTable([periodHeaders,branchHeaders,...rows],{x:.48,y:1.43,w:12.35,colW:[2.85,...Array(count*2).fill(9.5/(count*2))],
      fontFace:'Arial',fontSize:count>3?11.5:12.5,color:C.ink,rowH:.29,margin:[.045,.055,.045,.055],
      border:{type:'solid',color:'CAD3DC',pt:.4},autoPage:false,fill:'FFFFFF',valign:'middle'});
    text(s,'* Antes de provisiones, depreciación e IR. Consolidado del ámbito seleccionado. Cifras redondeadas; N/D: sin datos.',{x:.5,y:6.62,w:12.2,h:.25,fontSize:10,color:'52657B'});
  });

  s=slide('Evolución de ingresos, gastos y resultados','13 meses · importes mensuales');
  chart(s,[['revenue','bar'],['expenses','bar'],['net','line']],{dataLabelFontSize:10});
  s=slide('Composición de los ingresos','Ingresos de cartera y otros ingresos · 13 meses');
  chart(s,[['portfolio_income','bar'],['other_income','bar'],['revenue','line']],{stacked:true,chartColors:[C.blue,C.gray,C.green]});
  s=slide('Composición de los gastos','13 meses · clasificación por naturaleza');
  chart(s,[['personnel','bar'],['financial_expenses','bar'],['general','bar'],['provisions','bar'],['depreciation','bar'],['tax','bar'],['expenses','line']],{stacked:true,legendFontSize:11,chartColors:[C.gray,C.blue,C.yellow,'B44443',C.orange,C.purple,C.red]});

  const cashDifference=difference(data.series.cash?.[12]??null,data.series.cash?.[11]??null).amount;
  s=slide('Efectivo disponible al cierre',`Saldo al cierre de cada mes · 13 meses · ${unit}`);
  chart(s,[['cash','line']],{chartColors:[C.green],showLegend:false,showMarker:true,lineSize:3,dataLabelFontSize:10});
  const cashChange=cashDifference==null?'Variación del saldo de efectivo: sin datos verificables.':
    cashDifference===0?`En ${data.months[12].label}, el saldo de efectivo no varió respecto al mes anterior.`:
    `En ${data.months[12].label}, el efectivo ${cashDifference<0?'disminuyó':'aumentó'} ${fmt(Math.abs(cashDifference))} ${unit} respecto al mes anterior.`;
  text(s,cashChange,{x:.5,y:6.62,w:12.2,h:.25,fontSize:11,color:C.ink});

  const notes=[...data.findings,...data.warnings.map(w=>'Observación: '+w)];
  if(data.comments)notes.push(...data.comments.split(/\n+/).filter(Boolean).map(x=>'Gerencia: '+x));
  // Split long paragraphs as well as lists; preserve every comment without shrinking fonts.
  const paragraphs=[];
  for(const n of notes){let rest=n;while(rest.length>480){let at=rest.lastIndexOf(' ',480);if(at<120)at=480;paragraphs.push(rest.slice(0,at));rest=rest.slice(at).trimStart();}if(rest)paragraphs.push(rest);}
  let page=[],used=0,pages=[];
  for(const n of paragraphs){const lines=Math.ceil(n.length/100);if(used+lines>16&&page.length){pages.push(page);page=[];used=0;}page.push(n);used+=lines+1;}
  if(page.length||!pages.length)pages.push(page);
  pages.forEach((items,i)=>{
    s=slide(i?'Puntos para discusión (continuación)':'Puntos para discusión',watermark);
    let y=1.5;for(const note of items){const h=Math.ceil(note.length/100)*.26+.18;text(s,note,{x:.55,y,w:12.1,h,fontSize:16,breakLine:false,paraSpaceAfterPt:8});y+=h+.14;}
  });
  // PptxGenJS exposes one label color for an entire plot. Set native per-series
  // contrast for stacked labels so gray/yellow use dark text and blue/red white.
  const archive=await JSZip.loadAsync(await ppt.write({outputType:'nodebuffer',compression:true}));
  const boxedLineLabels=[['net',C.green],['revenue',C.green],['expenses',C.red]].map(([key,color])=>({
    title:String(data.labels[key]).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c])),color}));
  for(const name of Object.keys(archive.files).filter(n=>/^ppt\/charts\/chart\d+\.xml$/.test(n))){
    let xml=await archive.file(name).async('string');
    xml=xml.replace(/<c:barChart>[\s\S]*?<\/c:barChart>/g,plot=>{
      if(!plot.includes('<c:grouping val="stacked"'))return plot;
      return plot.replace(/<c:ser>[\s\S]*?<\/c:ser>/g,series=>{
        const fill=series.match(/<c:spPr>\s*<a:solidFill><a:srgbClr val="([0-9A-Fa-f]{6})"/);
        if(!fill)return series;
        const rgb=fill[1].match(/../g).map(hex=>parseInt(hex,16));
        const labelColor=(rgb[0]*299+rgb[1]*587+rgb[2]*114)/1000>150?C.ink:'FFFFFF';
        return series.replace(/<c:dLbls>[\s\S]*?<\/c:dLbls>/g,labels=>labels.replace(/<a:srgbClr val="[0-9A-Fa-f]{6}"/g,`<a:srgbClr val="${labelColor}"`));
      });
    });
    if(xml.includes('<c:v>__CE_ASSET_LABELS__</c:v>')){
      const asset=xml.match(/<c:barChart>[\s\S]*?<c:ser>([\s\S]*?)<\/c:ser>/)[1];
      const assetValues=asset.match(/<c:val>[\s\S]*?<\/c:val>/)[0];
      const assetTitle=asset.match(/<c:tx>[\s\S]*?<\/c:tx>/)[0];
      let seriesIndex=0;
      xml=xml.replace(/<c:ser>[\s\S]*?<\/c:ser>/g,series=>{
        const i=seriesIndex++;
        if(i===3)series=series.replace(/<c:val>[\s\S]*?<\/c:val>/,assetValues)
          .replace(/<c:tx>[\s\S]*?<\/c:tx>/,assetTitle)
          .replace(/<c:marker>[\s\S]*?<\/c:marker>/,'<c:marker><c:symbol val="none"/></c:marker>');
        return series.replace(/<c:dLbls>[\s\S]*?<\/c:dLbls>/g,labels=>i===0?
          labels.replace('<c:showVal val="1"/>','<c:showVal val="0"/>'):
          labels.replace(/<a:defRPr b="0"/g,'<a:defRPr b="1"'));
      });
      xml=xml.replace(/(<c:legend>\s*<c:legendPos[^>]*\/>)/,'$1<c:legendEntry><c:idx val="3"/><c:delete val="1"/></c:legendEntry>');
    }
    // Native label boxes keep net and composition totals legible and editable.
    xml=xml.replace(/<c:lineChart>[\s\S]*?<\/c:lineChart>/g,plot=>plot.replace(/<c:ser>[\s\S]*?<\/c:ser>/g,series=>{
      const title=series.match(/<c:tx>[\s\S]*?<\/c:tx>/)?.[0];
      const labelStyle=boxedLineLabels.find(label=>title?.includes(`<c:v>${label.title}</c:v>`));
      if(!labelStyle)return series;
      return series.replace(/<c:dLbls>[\s\S]*?<\/c:dLbls>/g,labels=>{
        const box=`<c:spPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:ln w="9525"><a:solidFill><a:srgbClr val="${labelStyle.color}"/></a:solidFill><a:prstDash val="solid"/></a:ln></c:spPr>`;
        return labels.replace('<c:txPr>',box+'<c:txPr>').replace(/<a:defRPr\b([^>]*)>/g,(_,attributes)=>
          `<a:defRPr${attributes.replace(/b="\d"/,'b="1"')}>`);
      });
    }));
    archive.file(name,xml);
  }
  fs.writeFileSync(output,await archive.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));
  return {slides:slideCount};
}
if(require.main===module){const [source,out]=process.argv.slice(2);build(JSON.parse(fs.readFileSync(source,'utf8')),out).catch(e=>{console.error(e.stack||e.message);process.exit(1);});}
module.exports={build,resultsSummary,branchResults};
