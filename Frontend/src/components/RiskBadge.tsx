import type {RiskLevel} from '../types';
const riskClasses:Record<string,string>={Low:'low',Moderate:'moderate',High:'high',Severe:'severe','No Travel':'no-travel',Unavailable:'unavailable'};
export default function RiskBadge({level}:{level:RiskLevel|string|null}){const value=level||'Unavailable';return <span className={`risk-badge risk-${riskClasses[value]||'unavailable'}`}><span aria-hidden="true">{value==='Low'?'✓':value==='No Travel'?'!':'•'}</span>{value}</span>}
