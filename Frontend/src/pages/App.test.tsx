// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import App from './App';
import {analyzeTrip,searchPlaces} from '../services/api';
import type {Analysis,Place,Route} from '../types';

vi.mock('../services/api',()=>({analyzeTrip:vi.fn(),searchPlaces:vi.fn()}));
vi.mock('react-leaflet',()=>({MapContainer:()=>null,TileLayer:()=>null,Polyline:()=>null,CircleMarker:()=>null,Popup:()=>null,useMap:()=>({fitBounds:vi.fn()})}));

const origin:Place={label:'Boston, Massachusetts, United States',lat:42.36,lon:-71.06,locality:'Boston',region:'Massachusetts',country:'United States'};
const destination:Place={label:'Albany, New York, United States',lat:42.65,lon:-73.75,locality:'Albany',region:'New York',country:'United States'};
const checkpoint=(id:string,level:'Low'|'No Travel')=>({id,lat:42.36,lon:-71.06,distance_miles:0,eta:'2030-06-15T13:00:00.000Z',weather:{available:true,forecast_time:'2030-06-15T13:00:00Z',forecast_issued_at:'2030-06-15T10:00:00Z',wind_mph:level==='No Travel'?56:18,rain_in_hr:0,snow_in_hr:0,temperature_f:65,visibility_miles:10},risk:{wind_risk:level,rain_risk:'Low' as const,snow_risk:'Low' as const,load_risk:null,overall_risk:level,no_travel:level==='No Travel',explanation:level==='No Travel'?'Wind 56 mph: no travel risk':'Weather conditions are low risk.'}});
const makeRoute=(id:string,rank:number,level:'Low'|'No Travel',recommended:boolean):Route=>({id,name:`Route ${id}`,geometry:[[42.36,-71.06],[42.5,-71.2]],distance_miles:120,duration_seconds:7200,arrival:'2030-06-15T15:00:00.000Z',rank,recommended,summary:{checkpoint_count:1,no_travel_miles:level==='No Travel'?25:0,severe_miles:0,high_miles:0,moderate_miles:0,low_miles:level==='Low'?120:0,no_travel_locations:level==='No Travel'?[{lat:42.36,lon:-71.06,distance_miles:0,eta:'2030-06-15T13:00:00Z'}]:[],average_risk_score:level==='Low'?0:4,weather_available:1,forecast_timezone:'UTC',forecast_start:'2030-06-15T13:00:00Z',forecast_end:'2030-06-15T13:00:00Z',overall_risk:level},checkpoints:[checkpoint(`${id}-cp`,level)]});
const result:Analysis={routes:[makeRoute('safe',1,'Low',true),makeRoute('avoid',2,'No Travel',false)],recommended_route_id:'safe',route_count:2,alternatives_note:'The provider returned 2 route options.',safety_note:'Weather-aware planning support only.',trip:{origin:{label:origin.label,lat:origin.lat,lon:origin.lon},destination:{label:destination.label,lat:destination.lat,lon:destination.lon},departure:'2030-06-15T12:00:00.000Z',load_lb:40000,interval_miles:25}};
async function choosePlace(field:string,place:Place){
 fireEvent.change(screen.getByLabelText(field),{target:{value:place.label.split(',')[0]}});
 const option=await screen.findByRole('option',{name:new RegExp(place.locality||place.label.split(',')[0])});
 fireEvent.click(option);
}
async function fillJourney(){
 vi.mocked(searchPlaces).mockImplementation(async query=>({results:[query.toLowerCase().includes('alb')?destination:origin]}));
 await choosePlace('Origin',origin);await choosePlace('Destination',destination);
 fireEvent.change(screen.getByLabelText('Cargo weight'),{target:{value:'40000'}});
}
afterEach(()=>{cleanup();vi.resetAllMocks()});

describe('RouteWise dashboard',()=>{
 it('shows the empty state, prevents duplicate submissions, and preserves form input on errors',async()=>{
  render(<App/>);expect(screen.getByText('Build a weather-aware trip briefing')).toBeTruthy();
  await fillJourney();let finish!:(value:Analysis)=>void;vi.mocked(analyzeTrip).mockReturnValue(new Promise(resolve=>{finish=resolve}));
  fireEvent.click(screen.getByRole('button',{name:/Analyze route/}));expect(screen.getByRole('button',{name:/Analyzing route/}).hasAttribute('disabled')).toBe(true);
  finish(result);await screen.findByText('Your route analysis');
  cleanup();render(<App/>);await fillJourney();vi.mocked(analyzeTrip).mockRejectedValue(new Error('Routing service is temporarily unavailable.'));
  fireEvent.click(screen.getByRole('button',{name:/Analyze route/}));expect((await screen.findByRole('alert')).textContent).toContain('Routing service is temporarily unavailable.');
  expect((screen.getByLabelText('Origin') as HTMLInputElement).value).toContain('Boston');
 });
 it('renders real route summaries, checkpoint forecast details, risk warnings, selection, and timeline controls',async()=>{
  vi.mocked(analyzeTrip).mockResolvedValue(result);render(<App/>);await fillJourney();
  fireEvent.click(screen.getByRole('button',{name:/Analyze route/}));await screen.findByText('Your route analysis');
  expect(screen.getAllByText('120 mi').length).toBeGreaterThan(0);expect(screen.getByText('65 °F')).toBeTruthy();
  expect(screen.getByText(/Forecast conditions at each route checkpoint arrival/)).toBeTruthy();
  const other=screen.getByRole('button',{name:/Route avoid/});fireEvent.click(other);expect(other.getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('alert').textContent).toContain('route');
  fireEvent.change(screen.getByLabelText('Hours after departure'),{target:{value:'12'}});expect(screen.getByText('+12 hours')).toBeTruthy();
 });
 it('uses the selected suggestion coordinates in the route request',async()=>{
  vi.mocked(analyzeTrip).mockResolvedValue(result);render(<App/>);await fillJourney();
  fireEvent.click(screen.getByRole('button',{name:/Analyze route/}));await screen.findByText('Your route analysis');
  expect(vi.mocked(analyzeTrip).mock.calls[0][0]).toMatchObject({origin_place:origin,destination_place:destination,origin:origin.label,destination:destination.label});
 });
 it('shows three generated routes without the obsolete distance warning or a count notice',async()=>{
  const threeRoutes:Analysis={...result,routes:[makeRoute('one',1,'Low',true),makeRoute('two',2,'Low',false),makeRoute('three',3,'Low',false)],recommended_route_id:'one',route_count:3,alternatives_note:null};
  vi.mocked(analyzeTrip).mockResolvedValue(threeRoutes);render(<App/>);await fillJourney();
  fireEvent.click(screen.getByRole('button',{name:/Analyze route/}));await screen.findByText('Your route analysis');
  const routeSection=screen.getByText('Available routes').closest('section');
  expect(routeSection?.querySelectorAll('.route-choice')).toHaveLength(3);
  expect(document.body.textContent).not.toContain('Alternative routes are supported only for journeys up to 100 km');
  expect(routeSection?.textContent).not.toContain('fewer than three');
 });
 it('supports keyboard navigation and selection in location suggestions',async()=>{
  const second:Place={label:'Boston Village, Another Region, Canada',lat:45,lon:-70,locality:'Boston Village',region:'Another Region',country:'Canada'};
  vi.mocked(searchPlaces).mockResolvedValue({results:[origin,second]});render(<App/>);
  const input=screen.getByLabelText('Origin');fireEvent.change(input,{target:{value:'Boston'}});
  await screen.findByRole('option',{name:/Boston, Massachusetts/});fireEvent.keyDown(input,{key:'ArrowDown'});fireEvent.keyDown(input,{key:'Enter'});
  expect((input as HTMLInputElement).value).toBe(origin.label);
 });
});
