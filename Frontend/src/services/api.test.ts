import {afterEach,describe,expect,it,vi} from 'vitest';
import {analyzeTrip,searchPlaces} from './api';

afterEach(()=>vi.unstubAllGlobals());
describe('frontend API service',()=>{
  it('sends the journey payload to Django and returns its routes',async()=>{
    const response={routes:[{id:'r1'}],recommended_route_id:'r1'};
    const fetchMock=vi.fn().mockResolvedValue(new Response(JSON.stringify(response),{status:200}));
    vi.stubGlobal('fetch',fetchMock);
    const payload={origin:'Boston',destination:'Albany',origin_place:{label:'Boston',lat:42.36,lon:-71.06},destination_place:{label:'Albany',lat:42.65,lon:-73.75},departure:'2030-06-15T12:00:00.000Z',load_lb:40000,interval_miles:25};
    await expect(analyzeTrip(payload)).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/routes/analyze/'),expect.objectContaining({method:'POST',body:JSON.stringify(payload)}));
  });
  it('surfaces structured backend errors',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{message:'Routing is not configured.'}}),{status:503})));
    await expect(searchPlaces('Boston')).rejects.toThrow('Routing is not configured.');
  });
});
