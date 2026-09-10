/* Dashboard presentation only. All values come from the aggregated API. */
window.GymCultureDashboard = ({api, money, escapeHtml, labels, rows, fail, reducedMotion}) => {
  const palette = {sales:'#8B5CF6', orders:'#3B82F6', city:'#06B6D4', product:'#8B5CF6', PENDING:'#F59E0B', CONFIRMED:'#06B6D4', PREPARING:'#8B5CF6', SHIPPED:'#3B82F6', DELIVERED:'#22C55E', CANCELLED:'#EF4444'};
  const charts = new Map();
  const number = value => new Intl.NumberFormat('es-PY').format(value);
  const compactMoney = value => `₲ ${new Intl.NumberFormat('es-PY', {notation:'compact', maximumFractionDigits:1}).format(value)}`;
  const metrics = document.querySelector('#bo-metrics');
  const selector = document.querySelector('#dashboard-period');
  const hosts = [...document.querySelectorAll('.bo-chart, #dashboard-stock, #bo-recent, #bo-period-summary')];
  let sequence = 0;
  let controller;
  const skeleton = '<div class="bo-loading-placeholder" aria-hidden="true"><i></i><i></i><i></i></div>';
  const tooltip = {
    backgroundColor:'#111722', titleColor:'#fff', bodyColor:'#edf1f7', borderColor:'#354052', borderWidth:1,
    padding:12, cornerRadius:8, boxPadding:5, titleMarginBottom:8, usePointStyle:true,
    callbacks:{label: context => `${context.dataset.label}: ${context.dataset.yAxisID === 'sales' ? money(context.raw) : number(context.raw)}`},
  };
  const axis = (currency = false) => ({beginAtZero:true, border:{display:false}, grid:{color:'#ffffff09'},
    ticks:{color:'#a6b0c0', font:{size:11}, maxTicksLimit:5, precision:0, callback: currency ? compactMoney : value => number(value)}});
  const categoryAxis = {border:{display:false}, grid:{display:false}, ticks:{color:'#c5ccda', font:{size:11}, autoSkip:true, maxTicksLimit:7, maxRotation:0, minRotation:0}};
  const bar = (label, data, color) => ({label,data,backgroundColor:color, borderRadius:4, borderSkipped:false, maxBarThickness:12, categoryPercentage:.65, barPercentage:.55});
  const draw = (id, type, chartLabels, datasets, extra = {}) => {
    const host = document.getElementById(id);
    host.querySelector('.bo-loading-placeholder')?.remove();
    if (!datasets.some(set => set.data.some(value => Number(value) > 0))) {
      charts.get(id)?.destroy(); charts.delete(id);
      host.innerHTML = '<div class="bo-empty">No hay datos para este período.</div>';
      return;
    }
    const summary = chartLabels.map((label,i) => `${label}: ${datasets.map(set => `${set.label} ${set.yAxisID === 'sales' ? money(set.data[i]) : number(set.data[i])}`).join(', ')}`).join('; ');
    if (!window.Chart) {host.textContent=summary; return;}
    const options = {responsive:true, maintainAspectRatio:false, animation:reducedMotion ? false : {duration:320},
      layout:{padding:{top:8,right:8,bottom:4}},
      plugins:{legend:{display:false},tooltip}, scales:{x:categoryAxis,y:axis()}, ...extra};
    let chart = charts.get(id);
    if (chart && chart.config.type === type) {
      chart.data.labels = chartLabels; chart.data.datasets = datasets; chart.options = options;
      chart.canvas.setAttribute('aria-label',summary); chart.update();
    } else {
      chart?.destroy();
      host.innerHTML='<canvas role="img"></canvas>';
      const canvas=host.querySelector('canvas'); canvas.setAttribute('aria-label',summary);
      charts.set(id,new Chart(canvas,{type,data:{labels:chartLabels,datasets},options}));
    }
  };
  const render = data => {
    const k=data.kpis;
    const values=[
      ['Ventas totales',k.total_sales,'Pagados · histórico','sales','money'],
      ['Pedidos totales',k.total_orders,'Todo el historial','orders'],
      ['Ticket promedio',k.average_ticket,'Por pedido pagado','sales','money'],
      ['Clientes',k.customers,'Cuentas activas','city'],
      ['En producción',k.production_orders,'Pedidos activos','PREPARING'],
      ['Pendientes de stock',k.awaiting_stock,'Esperando reposición','PENDING'],
      ['Pedidos pendientes',k.pending_orders,'Por confirmar','PENDING'],
      ['Stock crítico',k.low_stock_variants,'Variantes bajas o con faltantes','CANCELLED'],
    ];
    metrics.innerHTML=values.map(([title,value,context,color,format])=>`<article style="--metric-color:${palette[color]}"><span>${title}</span><strong>${format==='money'?money(value):number(value)}</strong><small>${context}</small></article>`).join('');
    if (!reducedMotion) {
      const nodes=[...metrics.querySelectorAll('strong')], start=performance.now(), renderSequence=sequence;
      const animate=now=>{if(renderSequence!==sequence)return;const progress=Math.min((now-start)/320,1);
        nodes.forEach((node,i)=>{const value=Math.round(Number(values[i][1])*(1-(1-progress)**3));node.textContent=values[i][4]==='money'?money(value):number(value);});
        if(progress<1)requestAnimationFrame(animate);
      };requestAnimationFrame(animate);
    }
    document.querySelector('#bo-activity').innerHTML=`<span>Ventas últimos 30 días <strong>${money(k.sales_30_days)}</strong></span><span>Pedidos hoy <strong>${number(k.orders_today)}</strong></span><span>Esta semana <strong>${number(k.orders_this_week)}</strong></span>`;
    document.querySelector('#bo-period-summary').innerHTML=`<div><span class="bo-key" style="--key-color:${palette.orders}">Pedidos</span><strong>${number(data.period_summary.orders)}</strong></div><div><span class="bo-key bo-key-line" style="--key-color:${palette.sales}">Ventas</span><strong>${money(data.period_summary.sales)}</strong></div>`;
    const series = data.period === '90' ? data.sales_over_time.reduce((groups,row,index) => {
      if (index % 7 === 0) groups.push({date:row.date,end:row.date,orders:0,sales:0});
      const group=groups[groups.length-1];group.orders+=row.orders;group.sales+=Number(row.sales);group.end=row.date;return groups;
    },[]) : data.sales_over_time;
    document.querySelector('#period-granularity').textContent=data.period==='90'?'Agrupado en intervalos de 7 días. El último puede ser parcial.':data.period==='12m'?'Totales por mes.':'Totales por día.';
    const shortDate=value=>new Intl.DateTimeFormat('es-PY',data.period==='12m'?{month:'short',year:'2-digit',timeZone:'UTC'}:{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(`${value}T12:00:00Z`));
    const dates=series.map(row=>shortDate(row.date));
    draw('chart-period','bar',dates,[
      {...bar('Pedidos',series.map(row=>row.orders),palette.orders),yAxisID:'orders',order:2},
      {label:'Ventas',data:series.map(row=>Number(row.sales)),type:'line',yAxisID:'sales',order:1,borderColor:palette.sales,backgroundColor:palette.sales,borderWidth:2.5,pointRadius:data.period==='7'?3:0,pointHoverRadius:5,pointHitRadius:12,tension:.15,fill:false},
    ], {
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{...tooltip,callbacks:{...tooltip.callbacks,title:items=>{
          const row=series[items[0].dataIndex];
          return row.end?`${shortDate(row.date)} – ${shortDate(row.end)}`:shortDate(row.date);
        }}},
      },
      scales:{
        x:categoryAxis,
        orders:{...axis(),position:'left',title:{display:true,text:'Pedidos',color:'#93baff',font:{size:11}}},
        sales:{...axis(true),position:'right',grid:{drawOnChartArea:false},title:{display:true,text:'Ventas · ₲',color:'#c4b5fd',font:{size:11}}},
      },
    });
    const cities=[...data.orders_by_city].sort((a,b)=>b.orders-a.orders);
    document.querySelector('#chart-city').style.height=`${Math.max(260,cities.length*38)}px`;
    draw('chart-city','bar',cities.map(row=>row.city),[bar('Pedidos',cities.map(row=>row.orders),palette.city)],{indexAxis:'y',scales:{x:axis(),y:{...categoryAxis,ticks:{...categoryAxis.ticks,autoSkip:false}}}});
    const products=[...data.top_products].sort((a,b)=>b.quantity-a.quantity);
    document.querySelector('#chart-products').style.height=`${Math.max(260,products.length*38)}px`;
    draw('chart-products','bar',products.map(row=>row.product__name),[bar('Unidades',products.map(row=>row.quantity),palette.product)],{indexAxis:'y',scales:{x:axis(),y:{...categoryAxis,ticks:{...categoryAxis.ticks,autoSkip:false}}}});
    const statuses=data.orders_by_status, total=statuses.reduce((sum,row)=>sum+row.orders,0);
    draw('chart-status','doughnut',statuses.map(row=>labels[row.status]),[{label:'Pedidos',data:statuses.map(row=>row.orders),backgroundColor:statuses.map(row=>palette[row.status]),borderColor:'#141923',borderWidth:3,hoverOffset:4}],{
      cutout:'74%',scales:{},plugins:{legend:{display:false},tooltip:{...tooltip,callbacks:{label:ctx=>`${ctx.label}: ${number(ctx.raw)} (${new Intl.NumberFormat('es-PY',{maximumFractionDigits:1}).format(total?ctx.raw/total*100:0)}%)`}}},
    });
    document.querySelector('#status-legend').innerHTML=total?statuses.map(row=>`<li><span class="bo-key" style="--key-color:${palette[row.status]}">${escapeHtml(labels[row.status])}</span><strong>${number(row.orders)}</strong></li>`).join(''):'';
    document.querySelector('#dashboard-stock').innerHTML=data.low_stock.length?`<ul class="bo-critical-list">${data.low_stock.map(item=>`<li><div><a href="/backoffice/stock/?variant=${item.id}">${escapeHtml(item.product_name)}</a><small>${escapeHtml(item.color)} / ${escapeHtml(item.size)}</small></div><div><span class="bo-status ${item.stock===0?'status-cancelled':item.stock_status==='LOW'?'status-pending':'status-available'}">${item.stock===0?'Sin stock':`${number(item.stock)} en stock`}</span><small>${item.pending_demand?`Faltan ${number(item.pending_demand)} · ${number(item.pending_orders)} pedidos`:'Sin pedidos pendientes'}</small></div></li>`).join('')}</ul>`:'<div class="bo-empty">No hay variantes con stock crítico.</div>';
    document.querySelector('#bo-recent').innerHTML=rows(data.recent_orders);
  };
  const load=async()=>{
    const requestId=++sequence;
    controller?.abort(); controller=new AbortController();
    const feedback=document.querySelector('#bo-feedback');feedback.classList.remove('is-error');feedback.textContent='Actualizando indicadores…';
    metrics.setAttribute('aria-busy','true');
    if(!metrics.children.length)metrics.innerHTML=Array.from({length:8},()=>`<article>${skeleton}</article>`).join('');
    hosts.forEach(host=>{host.setAttribute('aria-busy','true');if(!host.children.length)host.innerHTML=skeleton;});
    try {
      const data=await api(`/api/backoffice/dashboard/?period=${selector.value}`,{signal:controller.signal});
      if(requestId!==sequence)return;
      render(data);feedback.textContent='';
    } catch(error) {
      if(requestId!==sequence)return;
      hosts.forEach(host=>{if(host.querySelector('.bo-loading-placeholder'))host.innerHTML='<div class="bo-empty">No se pudo cargar la información.</div>';});
      metrics.querySelectorAll('.bo-loading-placeholder').forEach(node=>{node.textContent='Sin información';});
      fail(error);
    } finally {
      if(requestId===sequence){metrics.setAttribute('aria-busy','false');hosts.forEach(host=>host.setAttribute('aria-busy','false'));}
    }
  };
  selector.addEventListener('change',load);
  document.querySelector('#dashboard-retry').addEventListener('click',load);
  load();
};
