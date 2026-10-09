import {CloudRain,CloudSnow,Eye,Wind,Thermometer} from 'lucide-react';
import type {Checkpoint,Route} from '../types';
import RiskBadge from './RiskBadge';

const localTime=(value:string,options:Intl.DateTimeFormatOptions={weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})=>new Intl.DateTimeFormat(undefined,{...options,timeZone:Intl.DateTimeFormat().resolvedOptions().timeZone}).format(new Date(value));
type Props={route:Route;departure:string;hour:number;onHour:(hour:number)=>void};
export default function ForecastTimeline({route,departure,hour,onHour}:Props){
 const due=route.checkpoints.filter(checkpoint=>(new Date(checkpoint.eta).getTime()-new Date(departure).getTime())/3600000<=hour+0.01);
 const available=due.filter(checkpoint=>checkpoint.weather.available);
 const unavailable=due.filter(checkpoint=>!checkpoint.weather.available);
 const issueTimes=available.map(checkpoint=>checkpoint.weather.forecast_issued_at).filter((value):value is string=>Boolean(value)).sort();
 const issued=issueTimes[issueTimes.length-1];
 const selectedAt=new Date(new Date(departure).getTime()+hour*3600000).toISOString();
 return <section className="panel forecast-panel" aria-labelledby="forecast-title">
  <div className="panel-heading"><div><span className="eyebrow">ETA-BASED FORECAST</span><h2 id="forecast-title">Weather timeline</h2><p>Forecast conditions at each route checkpoint arrival.</p></div><span className="forecast-chip">{Intl.DateTimeFormat().resolvedOptions().timeZone}</span></div>
  <div className="forecast-control"><div><span className="muted-label">Viewing checkpoints due by</span><strong>{hour===0?'Departure':`+${hour} hours`}</strong><span>{localTime(selectedAt)}</span></div><span className="weather-source">Forecast · Open-Meteo</span></div>
  <label className="sr-only" htmlFor="forecast-hour">Hours after departure</label>
  <input id="forecast-hour" className="forecast-slider" type="range" min="0" max="48" step="1" value={hour} onChange={event=>onHour(Number(event.target.value))} aria-valuetext={hour===0?'Departure':`${hour} hours after departure`}/>
  <div className="slider-ticks">{[0,6,12,24,48].map(value=><button key={value} type="button" className={hour===value?'tick-active':''} aria-pressed={hour===value} onClick={()=>onHour(value)}>{value===0?'Depart':`+${value}h`}</button>)}</div>
  <p className="forecast-context">This is estimated weather along the selected truck route, not a current observation.{issued&&<> Forecast data retrieved {localTime(issued,{hour:'numeric',minute:'2-digit'})}.</>}</p>
  <div className="timeline-list">
   {due.length===0&&<div className="empty-timeline">No checkpoint ETA falls within this time selection.</div>}
   {due.map(checkpoint=><CheckpointCard checkpoint={checkpoint} index={route.checkpoints.indexOf(checkpoint)} total={route.checkpoints.length} key={checkpoint.id}/>)}
  </div>
  {unavailable.length>0&&<div className="forecast-unavailable" role="status">Forecast unavailable for {unavailable.length} checkpoint{unavailable.length===1?'':'s'} at the selected ETA. The provider forecast horizon has limits; no weather values are estimated.</div>}
  {due.length>0&&available.length===0&&<div className="forecast-unavailable" role="status">No forecast data is available for the checkpoints due by this time.</div>}
 </section>
}
function CheckpointCard({checkpoint,index,total}:{checkpoint:Checkpoint;index:number;total:number}){
 const cp=checkpoint;const wx=cp.weather;
 return <article className={`timeline-card ${cp.risk.no_travel?'timeline-danger':''}`}>
  <div className="timeline-marker" aria-hidden="true"><span/></div>
  <div className="timeline-body">
   <div className="timeline-top"><div><strong>{index===0?'Origin':index===total-1?'Destination':`Checkpoint ${index}`}</strong><span>{cp.distance_miles.toFixed(0)} mi from origin · {localTime(cp.eta)}</span></div><RiskBadge level={cp.risk.overall_risk}/></div>
   {wx.available?<><div className="weather-values"><span><Wind size={15}/>{wx.wind_mph==null?'—':`${wx.wind_mph.toFixed(0)} mph`}</span><span><CloudRain size={15}/>{wx.rain_in_hr==null?'—':`${wx.rain_in_hr.toFixed(2)} in/hr`}</span><span><CloudSnow size={15}/>{wx.snow_in_hr==null?'—':`${wx.snow_in_hr.toFixed(2)} in/hr`}</span>{wx.temperature_f!=null&&<span><Thermometer size={15}/>{wx.temperature_f.toFixed(0)} °F</span>}{wx.visibility_miles!=null&&<span><Eye size={15}/>{wx.visibility_miles.toFixed(1)} mi visibility</span>}</div><p className="risk-explanation">{cp.risk.explanation}</p>{wx.forecast_time&&<small className="forecast-timestamp">Forecast valid {localTime(wx.forecast_time)}{wx.precipitation_note&&` · ${wx.precipitation_note}`}</small>}</>:<p className="risk-explanation unavailable-copy">{wx.reason||'Forecast unavailable for this ETA.'}</p>}
  </div>
 </article>
}
