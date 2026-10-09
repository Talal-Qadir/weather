import {useEffect,useMemo,useState} from 'react';
import type {ReactNode} from 'react';
import {MapContainer,TileLayer,Polyline,CircleMarker,Popup,useMap} from 'react-leaflet';
import {Activity,AlertTriangle,ArrowRight,Check,Clock3,CloudSun,Compass,Info,MapPin,Navigation,Route as RouteIcon,Settings,ShieldAlert,ShieldCheck,Truck,Weight,Wind} from 'lucide-react';
import LocationAutocomplete from '../components/LocationAutocomplete';
import ForecastTimeline from '../components/ForecastTimeline';
import RiskBadge from '../components/RiskBadge';
import {analyzeTrip} from '../services/api';
import type {Analysis,Checkpoint,Place,Route,RiskLevel} from '../types';

const riskColors:Record<string,string>={Low:'#23744f',Moderate:'#936400',High:'#a84d13',Severe:'#b23a35','No Travel':'#8d2530',Unavailable:'#59697a'};
const localInput=(date:Date)=>new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
const localTime=(value:string)=>new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
const duration=(seconds:number)=>{const hours=Math.floor(seconds/3600);const minutes=Math.round((seconds%3600)/60);return hours?`${hours} hr ${minutes} min`:`${minutes} min`};
const miles=(value:number)=>`${value.toFixed(value<10?1:0)} mi`;

function FitRoute({route}:{route:Route}){const map=useMap();useEffect(()=>{const fit=()=>{if(route.geometry.length)map.fitBounds(route.geometry,{padding:[32,32],maxZoom:9})};fit();window.addEventListener('route-fit',fit);return()=>window.removeEventListener('route-fit',fit)},[map,route]);return null}
function CheckpointPopup({checkpoint}:{checkpoint:Checkpoint}){const wx=checkpoint.weather;return <div className="map-popup"><strong>{checkpoint.distance_miles===0?'Origin':`${checkpoint.distance_miles.toFixed(0)} mi checkpoint`}</strong><span>{localTime(checkpoint.eta)}</span><RiskBadge level={checkpoint.risk.overall_risk}/>{wx.available?<><span>Wind {wx.wind_mph==null?'—':`${wx.wind_mph.toFixed(0)} mph`} · Rain {wx.rain_in_hr==null?'—':`${wx.rain_in_hr.toFixed(2)} in/hr`}</span><small>{checkpoint.risk.explanation}</small></>:<small>{wx.reason||'Forecast unavailable at this ETA.'}</small>}</div>}
function MapTiles(){return <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>}

export default function App(){
 const [origin,setOrigin]=useState<Place|null>(null);const [destination,setDestination]=useState<Place|null>(null);
 const [load,setLoad]=useState('40000');const [interval,setInterval]=useState('25');
 const [departure,setDeparture]=useState(()=>localInput(new Date(Date.now()+3600000)));
 const [analysis,setAnalysis]=useState<Analysis|null>(null);const [selectedRoute,setSelectedRoute]=useState('');
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [forecastHour,setForecastHour]=useState(0);
 const route=analysis?.routes.find(item=>item.id===selectedRoute)||analysis?.routes.find(item=>item.id===analysis.recommended_route_id)||null;
 const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone;
 const noTravelRoutes=analysis?.routes.filter(item=>item.summary.no_travel_miles>0)||[];
 const significantRoutes=analysis?.routes.filter(item=>item.summary.no_travel_miles>0||item.summary.severe_miles>0||item.summary.high_miles>0)||[];
 const riskMiles=useMemo(()=>route?([
  {label:'No Travel',value:route.summary.no_travel_miles},
  {label:'Severe',value:route.summary.severe_miles},
  {label:'High',value:route.summary.high_miles},
  {label:'Moderate',value:route.summary.moderate_miles},
  {label:'Low',value:route.summary.low_miles},
 ]):[],[route]);
 const comparison=useMemo(()=>{
  if(!analysis||!route)return null;
  const fastest=analysis.routes.filter(item=>item.id!==route.id).sort((a,b)=>a.duration_seconds-b.duration_seconds)[0];
  if(!fastest)return null;
  const savedNoTravel=fastest.summary.no_travel_miles-route.summary.no_travel_miles;
  const savedSevere=fastest.summary.severe_miles-route.summary.severe_miles;
  const extraMinutes=Math.round((route.duration_seconds-fastest.duration_seconds)/60);
  return {fastest,savedNoTravel,savedSevere,extraMinutes};
 },[analysis,route]);
 async function submit(event:React.FormEvent<HTMLFormElement>){
  event.preventDefault();setError('');
  if(!origin||!destination){setError('Choose both the origin and destination from the location suggestions.');return}
  if(Math.abs(origin.lat-destination.lat)<1e-6&&Math.abs(origin.lon-destination.lon)<1e-6){setError('Choose two different locations for this journey.');return}
  const departureDate=new Date(departure);
  if(Number.isNaN(departureDate.getTime())||localInput(departureDate)!==departure){setError('That local date and time does not exist because of a timezone clock change. Choose another time.');return}
  if(departureDate.getTime()<=Date.now()){setError('Choose a departure time in the future.');return}
  if(!Number.isFinite(Number(load))||Number(load)<1||Number(load)>200000){setError('Enter a cargo weight between 1 and 200,000 lb.');return}
  setBusy(true);
  try{
   const result=await analyzeTrip({origin:origin.label,destination:destination.label,origin_place:origin,destination_place:destination,departure:departureDate.toISOString(),load_lb:Number(load),interval_miles:Number(interval)});
   setAnalysis(result);setSelectedRoute(result.recommended_route_id);setForecastHour(48);
   const results=document.getElementById('analysis');if(results&&typeof results.scrollIntoView==='function')results.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(requestError){setError(requestError instanceof Error?requestError.message:'Route analysis could not be completed. Please try again.')}
  finally{setBusy(false)}
 }
 return <div className="app-shell">
  <aside className="sidebar" aria-label="Main navigation">
   <a className="brand" href="#overview"><span className="brand-mark"><RouteIcon size={22}/></span><span><strong>RouteWise</strong><small>WEATHER-AWARE ROUTING</small></span></a>
   <div className="nav-caption">WORKSPACE</div>
   <nav className="primary-nav"><a className="nav-item" href="#overview"><Activity size={17}/>Overview</a><a className="nav-item nav-current" href="#planner"><Navigation size={17}/>Plan a route</a><a className="nav-item" href="#analysis"><CloudSun size={17}/>Weather analysis</a><a className="nav-item" href="#settings"><Settings size={17}/>Settings</a></nav>
   <div className="sidebar-bottom"><div className="provider-indicator"><strong>DATA SOURCES</strong><span>HeiGIT · Open-Meteo</span></div><p>International locations from HeiGIT Pelias autocomplete.</p><div className="trust-mini"><ShieldCheck size={16}/><span>Planning support<br/>not a safety guarantee</span></div></div>
  </aside>
  <main className="main-content" id="overview">
   <header className="topbar"><div className="mobile-brand"><span className="brand-mark"><RouteIcon size={20}/></span><strong>RouteWise</strong></div><div className="topbar-context"><span>Fleet planning workspace</span><small>{new Intl.DateTimeFormat(undefined,{dateStyle:'full'}).format(new Date())}</small></div><div className="timezone-pill"><Clock3 size={15}/><span>{timezone}</span></div></header>
   <div className="page-content">
    <section className="welcome-row"><div><span className="eyebrow">ROUTE PLANNING</span><h1>Plan with the forecast in mind.</h1><p>Compare real route options using the weather your driver may meet at each checkpoint.</p></div><div className="trust-card"><ShieldCheck size={19}/><span><strong>Decision support for drivers</strong><small>Always review official road and weather advisories.</small></span></div></section>
    <form className="planner panel" id="planner" onSubmit={submit} noValidate>
     <div className="planner-heading"><div className="section-icon"><Compass size={19}/></div><div><h2>Plan a route</h2><p>Choose precise locations and a departure time to build your weather briefing.</p></div></div>
     <div className="location-grid"><LocationAutocomplete id="origin" label="Origin" placeholder="Search city, village, address, postal code…" value={origin} onSelect={setOrigin}/><div className="direction-arrow" aria-hidden="true"><ArrowRight size={18}/></div><LocationAutocomplete id="destination" label="Destination" placeholder="Search where the driver is headed…" value={destination} onSelect={setDestination}/></div>
     <div className="journey-options">
      <div className="form-field"><label htmlFor="departure">Departure date and time</label><div className="control-with-icon"><Clock3 size={16}/><input id="departure" type="datetime-local" required value={departure} min={localInput(new Date())} onChange={event=>setDeparture(event.target.value)}/></div><small>Shown in your local timezone: {timezone}</small></div>
      <div className="form-field"><label htmlFor="load">Cargo weight</label><div className="control-with-icon"><Weight size={16}/><input id="load" type="number" min="1" max="200000" step="1" required value={load} onChange={event=>setLoad(event.target.value)}/><span className="input-unit">lb</span></div><small>Used by the existing load-aware risk rules.</small></div>
      <div className="form-field"><label htmlFor="checkpoint-spacing">Forecast checkpoint spacing</label><select id="checkpoint-spacing" value={interval} onChange={event=>setInterval(event.target.value)}><option value="10">Every 10 miles</option><option value="25">Every 25 miles</option><option value="50">Every 50 miles</option></select><small>Route ETAs are converted from local time to UTC for weather lookup.</small></div>
      <button className="primary-button" type="submit" disabled={busy}>{busy?<><span className="spinner"/>Analyzing route and forecasts…</>:<><Navigation size={17}/>Analyze route</>}</button>
     </div>
     <p className="forecast-window-note"><Info size={15}/>Forecast availability depends on the provider horizon at each estimated checkpoint arrival. Values outside it are marked unavailable.</p>
     {busy&&<div className="progress-status" role="status" aria-live="polite"><span className="spinner"/>Requesting real routes and ETA-based weather data. This can take a little while.</div>}
     {error&&<div className="error-message" role="alert"><AlertTriangle size={17}/><span>{error}</span></div>}
    </form>

    {analysis&&route?<section id="analysis" className="analysis-section" aria-labelledby="analysis-title">
     <div className="analysis-heading"><div><span className="eyebrow">TRIP WEATHER BRIEFING</span><h2 id="analysis-title">Your route analysis</h2></div><span className="route-total"><RouteIcon size={15}/>{analysis.route_count} real route{analysis.route_count===1?'':'s'} analyzed</span></div>
     {analysis.alternatives_note&&<div className="notice" role="status"><Info size={17}/>{analysis.alternatives_note}</div>}
     {(noTravelRoutes.length>0||route.summary.severe_miles>0||route.summary.high_miles>0||significantRoutes.length===analysis.routes.length)&&<div className={`risk-alert ${route.summary.no_travel_miles>0||route.summary.severe_miles>0?'risk-alert-danger':'risk-alert-warning'}`} role="alert"><ShieldAlert size={21}/><div><strong>{route.summary.no_travel_miles>0?`Selected route includes ${miles(route.summary.no_travel_miles)} of No Travel exposure.`:route.summary.severe_miles>0?`Selected route includes ${miles(route.summary.severe_miles)} of Severe exposure.`:route.summary.high_miles>0?`Selected route includes ${miles(route.summary.high_miles)} of High exposure.`:noTravelRoutes.length?`${noTravelRoutes.length} other route${noTravelRoutes.length===1?'':'s'} include a No Travel weather condition.`:'Every available route has High, Severe, or No Travel exposure.'}</strong><span>{route.summary.no_travel_miles>0?'RouteWise does not mark this route safe. Review the forecast and official road/weather advisories before dispatch.':route.summary.severe_miles>0?'Severe risk remains on the selected route. The ranking is comparative and does not certify the journey as safe.':route.summary.high_miles>0?'Elevated weather exposure remains on the selected route. Review conditions and official advisories.':noTravelRoutes.length?`The selected route has no No Travel miles in the assessment, but that is not a safety guarantee. Review the forecast and official advisories.`:'The recommended route is the best match among the returned options, but it still carries meaningful weather risk.'}</span></div></div>}
     <div className="overview-grid">
      <article className="metric-card primary-metric"><span className="metric-label">{route.recommended?'RECOMMENDED ROUTE':'SELECTED ALTERNATIVE'}</span><div className="metric-main"><strong>{route.name}</strong><RiskBadge level={route.summary.overall_risk}/></div><span className="metric-sub">{route.summary.no_travel_miles>0?'Has No Travel exposure · review before dispatch':route.recommended?'Top ranked by the current risk criteria':'Selected for comparison'}</span></article>
      <Metric label="Distance" value={miles(route.distance_miles)} detail="Provider route distance" icon={<RouteIcon size={17}/>}/>
      <Metric label="Estimated drive" value={duration(route.duration_seconds)} detail="Provider route duration" icon={<Clock3 size={17}/>}/>
      <Metric label="Departure" value={localTime(analysis.trip.departure)} detail={timezone} icon={<Navigation size={17}/>}/>
      <Metric label="Estimated arrival" value={localTime(route.arrival)} detail="Based on route duration" icon={<Clock3 size={17}/>}/>
     </div>
     <div className="risk-mile-panel panel"><div className="risk-mile-head"><div><h3>Risk miles on selected route</h3><p>Checkpoint categories and segment miles from the backend assessment.</p></div><RiskBadge level={route.summary.overall_risk}/></div><div className="risk-mile-grid">{riskMiles.map(item=><div className="risk-mile" key={item.label}><span className="risk-swatch" style={{background:riskColors[item.label]}}/><span>{item.label}</span><strong>{miles(item.value)}</strong></div>)}</div><div className="risk-legend" aria-label="Weather risk category legend">{(['Low','Moderate','High','Severe','No Travel'] as RiskLevel[]).map(level=><span key={level}><RiskBadge level={level}/><small>{riskDescription[level]}</small></span>)}</div></div>
     <div className="analysis-grid">
      <section className="panel route-panel" aria-labelledby="routes-title"><div className="panel-heading"><div><span className="eyebrow">COMPARE</span><h2 id="routes-title">Available routes</h2><p>Ranked by Severe miles, High miles, average risk, then drive time. No Travel exposure is always flagged separately.</p></div></div>
       <div className="route-list">{analysis.routes.map(candidate=><button type="button" key={candidate.id} className={`route-choice ${route.id===candidate.id?'route-choice-active':''}`} aria-pressed={route.id===candidate.id} onClick={()=>setSelectedRoute(candidate.id)}><span className="route-choice-heading"><span className="route-rank">{String(candidate.rank).padStart(2,'0')}</span><strong>{candidate.name}</strong>{candidate.recommended&&<span className="recommended-label"><Check size={13}/>{candidate.summary.no_travel_miles?'Top ranked · risk present':'Recommended'}</span>}</span><span className="route-choice-stats"><span>{miles(candidate.distance_miles)}</span><span>{duration(candidate.duration_seconds)}</span><RiskBadge level={candidate.summary.overall_risk}/></span><span className="route-exposure">{miles(candidate.summary.no_travel_miles)} No Travel <i/> {miles(candidate.summary.severe_miles)} Severe <i/> {miles(candidate.summary.high_miles)} High</span></button>)}</div>
       <div className="recommendation-explainer"><ShieldCheck size={18}/><div><strong>{route.recommended?'Why this route ranks first':'Selected route comparison'}</strong><p>The backend compares Severe miles, High miles, average risk, and drive time. This route has {miles(route.summary.no_travel_miles)} No Travel, {miles(route.summary.severe_miles)} Severe, and {miles(route.summary.high_miles)} High exposure, with an average risk score of {route.summary.average_risk_score==null?'unavailable':`${route.summary.average_risk_score.toFixed(1)} / 4`}.{comparison&&<> Compared with the fastest alternative, it {comparison.savedNoTravel>0?`avoids ${miles(comparison.savedNoTravel)} of No Travel exposure`:comparison.savedNoTravel<0?`has ${miles(-comparison.savedNoTravel)} more No Travel exposure`:'has the same No Travel mileage'} and {comparison.savedSevere>0?`avoids ${miles(comparison.savedSevere)} of Severe exposure`:comparison.savedSevere<0?`has ${miles(-comparison.savedSevere)} more Severe exposure`:'has the same Severe mileage'}; it takes {comparison.extraMinutes>0?`${comparison.extraMinutes} more minutes`:comparison.extraMinutes<0?`${Math.abs(comparison.extraMinutes)} fewer minutes`:'about the same time'}.</>}</p></div></div>
      </section>
      <section className="panel map-panel" aria-labelledby="map-title"><div className="panel-heading map-heading"><div><span className="eyebrow">ROUTE MAP</span><h2 id="map-title">Weather along the route</h2><p>Selected route and ETA checkpoint risk markers.</p></div><button className="secondary-button fit-button" type="button" onClick={()=>window.dispatchEvent(new Event('route-fit'))}><MapPin size={15}/>Fit route</button></div>
       <div className="map-frame"><MapContainer center={route.geometry[0]} zoom={6} scrollWheelZoom className="map"><MapTiles/><FitRoute route={route}/>{analysis.routes.map(candidate=><Polyline key={candidate.id} positions={candidate.geometry} pathOptions={{color:candidate.id===route.id?'#145e86':'#64768b',weight:candidate.id===route.id?5:3,opacity:candidate.id===route.id?0.96:0.5,dashArray:candidate.id===route.id?undefined:'7 8'}} eventHandlers={{click:()=>setSelectedRoute(candidate.id)}}/>)}{route.checkpoints.map(checkpoint=><CircleMarker key={checkpoint.id} center={[checkpoint.lat,checkpoint.lon]} radius={checkpoint.risk.no_travel?8:6} pathOptions={{color:'#fff',weight:2,fillColor:riskColors[checkpoint.risk.overall_risk],fillOpacity:1}}><Popup><CheckpointPopup checkpoint={checkpoint}/></Popup></CircleMarker>)}</MapContainer></div>
       <div className="map-legend"><span><i className="legend-line legend-selected"/>Selected route</span><span><i className="legend-line legend-alt"/>Alternatives</span><span><i className="legend-point"/>Checkpoint risk markers</span></div>
      </section>
     </div>
     <div className="analysis-grid forecast-grid"><ForecastTimeline route={route} departure={analysis.trip.departure} hour={forecastHour} onHour={setForecastHour}/><aside className="panel trip-details"><div className="panel-heading"><div><span className="eyebrow">TRIP DETAILS</span><h2>Checkpoint summary</h2><p>{route.checkpoints.length} route checkpoints · {analysis.trip.interval_miles} mile spacing</p></div></div><div className="trip-location"><span className="location-dot"/><div><small>ORIGIN</small><strong>{analysis.trip.origin.label}</strong></div></div><div className="trip-connector"/><div className="trip-location"><span className="location-dot location-end"/><div><small>DESTINATION</small><strong>{analysis.trip.destination.label}</strong></div></div><div className="trip-facts"><span><Weight size={15}/>{analysis.trip.load_lb.toLocaleString()} lb cargo</span><span><Clock3 size={15}/>ETA weather in {timezone}</span><span><Wind size={15}/>Hourly precipitation is a proxy</span></div><p className="safety-copy">{analysis.safety_note}</p></aside></div>
    </section>:<section id="analysis" className="empty-dashboard"><div className="empty-illustration"><Truck size={29}/></div><span className="eyebrow">READY WHEN YOU ARE</span><h2>Build a weather-aware trip briefing</h2><p>Search for a street, village, district, city, or postal code, then compare provider routes with checkpoint forecasts at expected arrival times.</p><a href="#planner" className="secondary-button"><Navigation size={16}/>Plan a route</a><div className="empty-benefits"><span><RouteIcon size={16}/>Real provider routes</span><span><CloudSun size={16}/>ETA-based forecast</span><span><ShieldCheck size={16}/>Existing load-aware risk rules</span></div></section>}
    <section className="settings-panel panel" id="settings"><div className="settings-icon"><Settings size={18}/></div><div><span className="eyebrow">PLANNING PREFERENCES</span><h2>Units and forecast time</h2><p>Route distances use miles, cargo uses pounds, wind uses mph, and precipitation uses inches per hour as an hourly accumulation proxy. Checkpoint timestamps are shown in your browser timezone ({timezone}); the API uses UTC instants.</p></div><span className="settings-provider">HeiGIT · Open-Meteo</span></section>
    <footer className="page-footer"><span>RouteWise · Weather-aware journey planning</span><span>Decision support only. Confirm truck restrictions and official advisories before travel.</span></footer>
   </div>
  </main>
 </div>
}
function Metric({label,value,detail,icon}:{label:string;value:string;detail:string;icon:ReactNode}){return <article className="metric-card"><span className="metric-icon">{icon}</span><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><span className="metric-sub">{detail}</span></article>}
const riskDescription:Record<string,string>={Low:'Lower threshold range',Moderate:'Caution conditions',High:'Elevated exposure',Severe:'Significant hazard', 'No Travel':'Assessment stop threshold'};
