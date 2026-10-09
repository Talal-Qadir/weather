import {useEffect,useRef,useState} from 'react';
import {LoaderCircle,MapPin,RotateCw,Search} from 'lucide-react';
import {searchPlaces} from '../services/api';
import type {Place} from '../types';

type Props={id:string;label:string;placeholder:string;value:Place|null;onSelect:(place:Place|null)=>void};
type SearchState='idle'|'loading'|'ready'|'empty'|'error';

export default function LocationAutocomplete({id,label,placeholder,value,onSelect}:Props){
 const [query,setQuery]=useState(value?.label||'');
 const [results,setResults]=useState<Place[]>([]);
 const [status,setStatus]=useState<SearchState>('idle');
 const [active,setActive]=useState(-1);
 const [retry,setRetry]=useState(0);
 const input=useRef<HTMLInputElement>(null);
 const request=useRef<AbortController|null>(null);
 useEffect(()=>{if(value?.label&&value.label!==query)setQuery(value.label)},[value?.label]);
 useEffect(()=>{
  if(query.trim().length<3||value?.label===query){setResults([]);setStatus('idle');return}
  const controller=new AbortController();request.current?.abort();request.current=controller;
  const timer=window.setTimeout(async()=>{
   setStatus('loading');setActive(-1);
   try{const response=await searchPlaces(query.trim(),controller.signal);setResults(response.results);setStatus(response.results.length?'ready':'empty')}
   catch(error){if(!controller.signal.aborted){setResults([]);setStatus('error')}}
  },350);
  return()=>{window.clearTimeout(timer);controller.abort()};
 },[query,retry,value?.label]);
 function choose(place:Place){setQuery(place.label);setResults([]);setStatus('idle');onSelect(place)}
 function keyDown(event:React.KeyboardEvent<HTMLInputElement>){
  if(event.key==='ArrowDown'&&results.length){event.preventDefault();setActive(i=>Math.min(i+1,results.length-1))}
  else if(event.key==='ArrowUp'&&results.length){event.preventDefault();setActive(i=>Math.max(i-1,0))}
  else if(event.key==='Enter'){if(active>=0&&results[active]){event.preventDefault();choose(results[active])}else if(status==='ready'||status==='loading'){event.preventDefault()}}
  else if(event.key==='Escape'){setResults([]);setStatus('idle')}
 }
 return <div className="location-field">
  <label htmlFor={id}>{label}</label>
  <div className="location-input-wrap">
   <MapPin size={17} aria-hidden="true"/>
   <input ref={input} id={id} autoComplete="off" value={query} placeholder={placeholder} aria-autocomplete="list" aria-controls={`${id}-suggestions`} aria-expanded={status==='ready'} aria-activedescendant={active>=0?`${id}-option-${active}`:undefined} onKeyDown={keyDown} onChange={event=>{setQuery(event.target.value);setResults([]);setStatus('idle');setActive(-1);onSelect(null)}} />
   {status==='loading'?<LoaderCircle className="spin" size={16} aria-label="Searching locations"/>:<Search size={16} aria-hidden="true"/>}
  </div>
  {status==='loading'&&<p className="field-hint" role="status">Searching international place results…</p>}
  {status==='ready'&&<div className="location-suggestions" id={`${id}-suggestions`} role="listbox" aria-label={`${label} suggestions`}>
   {results.map((place,index)=>{const context=[place.locality,place.region,place.country,place.postalcode].filter(Boolean).join(' · ');return <button id={`${id}-option-${index}`} role="option" aria-selected={active===index} type="button" key={`${place.lat}:${place.lon}:${place.label}`} onMouseEnter={()=>setActive(index)} onMouseDown={event=>event.preventDefault()} onClick={()=>choose(place)}><span>{place.label}</span>{context&&<small>{context}</small>}<small className="coordinates">{place.lat.toFixed(4)}, {place.lon.toFixed(4)}</small></button>})}
  </div>}
  {status==='empty'&&<p className="field-message" role="status">No matching places. Try a street, locality, postal code, or add a region.</p>}
  {status==='error'&&<div className="field-message error-inline" role="alert"><span>Location search failed. Check your connection and retry.</span><button type="button" onClick={()=>setRetry(value=>value+1)}><RotateCw size={14}/> Retry</button></div>}
  {value&&<p className="selected-place" role="status">Selected: {value.label}</p>}
 </div>
}
