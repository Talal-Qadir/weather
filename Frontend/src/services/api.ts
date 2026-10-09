import type {Analysis,Place} from '../types';
const base=(import.meta.env.VITE_API_BASE_URL||'http://localhost:8000/api').replace(/\/$/,'');
async function request<T>(url:string,init?:RequestInit):Promise<T>{const res=await fetch(`${base}${url}`,init);const body=await res.json();if(!res.ok)throw new Error(body?.error?.message||'The service could not complete this request.');return body as T}
export const searchPlaces=(q:string,signal?:AbortSignal)=>request<{results:Place[]}>(`/geocode/?q=${encodeURIComponent(q)}`,{signal});
export const analyzeTrip=(payload:{origin:string;destination:string;origin_place:Place;destination_place:Place;departure:string;load_lb:number;interval_miles:number})=>request<Analysis>('/routes/analyze/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
