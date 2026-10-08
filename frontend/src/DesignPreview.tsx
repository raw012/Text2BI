import { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { ArrowRight, Check, Database, FileSpreadsheet, LayoutDashboard, MessageSquareText, RefreshCw, Send, UploadCloud } from 'lucide-react';
import './design-preview.css';

const labels = ['Import','Describe','Generate','Explore','Refine','Refresh'];
const prompt = 'Build a sales performance dashboard. Compare regions and show monthly revenue.';
const revision = 'Compare revenue by region, with the largest region first.';
export default function DesignPreview() {
  const params=new URLSearchParams(location.search);
  const embed=params.has('embed');
  const [step,setStep]=useState(Math.max(0,Math.min(5,Number(params.get('stage'))||0)));
  const [text,setText]=useState(''); const [updated,setUpdated]=useState(false);
  const [asked,setAsked]=useState(false); const [question,setQuestion]=useState('');
  const [progress,setProgress]=useState(0); const [replay,setReplay]=useState(0);
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  useEffect(()=>{
    setUpdated(false);setText('');setAsked(false);setProgress(0);
    const target=step===1?prompt:step===4?revision:'';
    let count=0;
    if(reduced){setText(target);setProgress(100);if(step===4||step===5)setUpdated(true);return;}
    const timer=setInterval(()=>{count++;setText(target.slice(0,count*2));setProgress(Math.min(100,count*4));if(count>=target.length/2&&target)clearInterval(timer);},36);
    const done=setTimeout(()=>{if(step===4||step===5)setUpdated(true);},2600);
    return()=>{clearInterval(timer);clearTimeout(done)};
  },[step,replay,reduced]);
  const refreshed=step===5&&updated;
  const chart={animationDuration:700,color:['#6875e8','#26a9a1','#f3b34c','#e57582'],tooltip:{trigger:'axis'},grid:{top:30,bottom:30,left:55,right:20},xAxis:{type:'category',data:step===4&&updated?['West','East','North','South']:['Apr','May','Jun','Jul','Aug','Sep'],axisLine:{show:false},axisTick:{show:false},axisLabel:{color:'#64748b',fontSize:13}},yAxis:{type:'value',splitLine:{lineStyle:{color:'#e8edf4'}},axisLabel:{color:'#64748b',formatter:'{value}k'}},series:[{name:'Revenue',type:step===4&&updated?'bar':'line',smooth:true,symbolSize:8,barWidth:'38%',data:step===4&&updated?[53.94,35.96,23.12,15.41]:refreshed?[14,18,22,23,28,37.68]:[12.8,16.9,18.5,21.2,25.13,33.9],lineStyle:{width:4},areaStyle:{opacity:.1},itemStyle:{borderRadius:[6,6,0,0]}}]};
  const donut={color:['#6875e8','#26a9a1','#f3b34c','#e57582'],tooltip:{trigger:'item'},series:[{type:'pie',radius:['60%','83%'],center:['50%','46%'],label:{show:false},data:[{name:'West',value:42},{name:'East',value:28},{name:'North',value:18},{name:'South',value:12}]}]};
  return <div className={`dp-shell ${embed?'dp-embed':''}`}>
    {!embed&&<aside className="dp-sidebar"><strong>Text2BI<span>ANALYTICS WORKSPACE</span></strong><nav>{labels.map((label,i)=><button key={label} onClick={()=>setStep(i)} className={i===step?'is-active':''}><span>{String(i+1).padStart(2,'0')}</span>{label}</button>)}</nav><small>DESIGN PREVIEW<br/>Sample data · No server calls</small></aside>}
    <main className="dp-main"><header className="dp-topbar"><span><LayoutDashboard size={17}/> Sales workspace <b>/ {labels[step]}</b></span><button onClick={()=>setReplay(x=>x+1)} title="Replay this demonstration"><RefreshCw size={15}/> Replay</button></header>
    <div className="dp-content" key={`${step}-${replay}`}>
      <div className="dp-heading"><div><span className="dp-eyebrow">{step<3?'YOUR NEXT INSIGHT STARTS HERE':'SALES INTELLIGENCE'} · SAMPLE DATA</span><h1>{['Bring your data into focus.','What would you like to see?','Turning your question into clarity.','Your business, at a glance.','A better view. In your words.','Fresh data. Same great view.'][step]}</h1></div>{step>=3&&<span className="dp-badge"><Check size={14}/>{updated?'Updated just now':'Report ready'}</span>}</div>
      {step===0&&<section className="dp-import"><div className="dp-upload"><UploadCloud size={42}/><h2>One file. A new perspective.</h2><p>Start with the sample sales dataset.<br/>No account or upload needed for this preview.</p><button className="dp-primary" onClick={()=>setStep(1)}>Use sales_2026.csv <ArrowRight size={18}/></button><span>CSV & Excel in the full product</span></div><div className="dp-source"><div><FileSpreadsheet size={25}/><strong>sales_2026.csv<small>1,842 rows · 4 fields</small></strong><Check size={20}/></div><table><thead><tr><th>Month</th><th>Region</th><th>Revenue</th></tr></thead><tbody>{[['July','West','$28,400'],['August','East','$32,600'],['September','West','$41,500']].map(row=><tr key={row[0]}>{row.map(cell=><td key={cell}>{cell}</td>)}</tr>)}</tbody></table><p><Database size={14}/> Preview your source before you build.</p></div></section>}
      {step===1&&<section className="dp-prompt"><span className="dp-badge"><FileSpreadsheet size={16}/> sales_2026.csv · Connected</span><h2>Describe the report.<br/><span>Leave the charts to us.</span></h2><label htmlFor="request">Your request</label><textarea id="request" value={text} onChange={e=>setText(e.target.value)} placeholder="What would you like to understand?"/><div className="dp-prompt-foot"><span>Monthly trends · Regional comparisons</span><button className="dp-primary" disabled={!text.trim()} onClick={()=>setStep(2)}>Generate report <ArrowRight size={18}/></button></div></section>}
      {step===2&&<section className="dp-building"><div className="dp-build-count">{progress}<span>%</span></div><h2>{progress<100?'Building your sales report':'Your report is ready.'}</h2><div className="dp-progress"><i style={{width:`${progress}%`}}/></div><div className="dp-build-steps">{['Understand the data','Calculate the metrics','Design your report'].map((label,i)=><div className={progress>(i+1)*30?'done':''} key={label}><Check size={18}/><span>{label}</span></div>)}</div><button className="dp-primary" disabled={progress<100} onClick={()=>setStep(3)}>Explore report <ArrowRight size={18}/></button><small>Demonstration sequence, not a live AI run.</small></section>}
      {step>=3&&<>
        <div className="dp-kpis">{[['Total revenue',refreshed?'$142,680':'$128,430','Revenue'],['Orders',refreshed?'2,014':'1,842','Orders'],['Average order',refreshed?'$70.84':'$69.72','Average']].map(([label,value,tag],i)=><article key={label} data-tone={i}><span>{label}</span><strong key={value}>{value}</strong><small>{tag} · sample sales data</small></article>)}</div>
        <div className={`dp-report ${step===4?'dp-refining':''}`}><section className="dp-chart"><h2>{step===4&&updated?'Revenue by region':'Revenue over time'}<span>{step===4&&updated?'Largest first':'Apr — Sep 2026'}</span></h2><ReactECharts option={chart} notMerge style={{height:embed?205:265}}/></section>{step!==4&&<section className="dp-chart dp-mix"><h2>Regional mix</h2><ReactECharts option={donut} style={{height:embed?145:205}}/><div className="dp-legend">{['West','East','North','South'].map((v,i)=><span key={v}><i style={{background:donut.color[i]}}/>{v}</span>)}</div></section>}
        {step===4&&<section className="dp-copilot"><span className="dp-eyebrow"><MessageSquareText size={16}/> DASHBOARD COPILOT</span><h2>Make it your own.</h2><label htmlFor="refinement">Describe a change</label><textarea id="refinement" value={text} onChange={e=>{setText(e.target.value);setUpdated(false)}}/><button className="dp-primary" onClick={()=>setUpdated(true)} disabled={!text.trim()}>Apply example change <Send size={16}/></button>{updated&&<p className="dp-response"><Check size={17}/> Regional revenue, sorted from largest to smallest. Your source data is unchanged.</p>}</section>}</div>
        {step===3&&<form className="dp-ask" onSubmit={e=>{e.preventDefault();if(question.trim())setAsked(true)}}><MessageSquareText size={20}/><input aria-label="Ask your data" placeholder="Try: Which region leads?" value={question} onChange={e=>setQuestion(e.target.value)}/><button aria-label="Ask example question" disabled={!question.trim()}><Send size={19}/></button>{asked&&<p>Example answer: West leads with 42% of revenue in this sample.</p>}</form>}
        {step===5&&<div className="dp-update"><FileSpreadsheet size={23}/><div><strong>{updated?'sales_2026_updated.csv':'sales_2026.csv'}</strong><span>{updated?'New rows included. Report layout preserved.':'Loading the next version of your sample data…'}</span></div><button onClick={()=>setUpdated(v=>!v)}><RefreshCw size={17}/>{updated?'Compare previous':'Refresh sample'}</button></div>}
      </>}
      {!embed&&<footer className="dp-footer"><span>Interactive UI concept · Example data only</span><button onClick={()=>setStep((step+1)%6)}>Next: {labels[(step+1)%6]} <ArrowRight size={16}/></button></footer>}
    </div></main>
  </div>;
}

