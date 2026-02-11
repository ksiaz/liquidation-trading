import { useState } from 'react';
import { useZones, formatTimestamp, formatNumber } from '../hooks/useObservatory';

const SYMBOLS = ['', 'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'LINK', 'HYPE', 'ADA', 'NEAR'];

export default function ZoneTable() {
  const [symbol, setSymbol] = useState('');
  const { data: zones, isLoading, error } = useZones(symbol || undefined);

  if (error) return <div className="error">Error: {String(error)}</div>;

  const demandCount = zones?.filter(z => z.zone_type === 'demand').length || 0;
  const supplyCount = zones?.filter(z => z.zone_type === 'supply').length || 0;

  return (
    <div>
      <div className="page-header"><h2>Zones</h2><p>Active M2 supply/demand zones</p></div>
      <div className="stats-grid" style={{marginBottom:'1rem'}}>
        <div className="stat-card"><div className="stat-label">Total Active</div><div className="stat-value">{zones?.length || 0}</div></div>
        <div className="stat-card"><div className="stat-label">Demand</div><div className="stat-value" style={{color:'var(--accent-green)'}}>{demandCount}</div></div>
        <div className="stat-card"><div className="stat-label">Supply</div><div className="stat-value" style={{color:'var(--accent-red)'}}>{supplyCount}</div></div>
      </div>
      <div className="filters">
        <select className="filter-select" value={symbol} onChange={e => setSymbol(e.target.value)}>
          <option value="">All Symbols</option>
          {SYMBOLS.filter(s => s).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="card">
        {isLoading ? <div className="loading">Loading...</div> : (
          <div className="table-container">
            <table>
              <thead><tr><th>Symbol</th><th>Type</th><th>Price Low</th><th>Price High</th><th>Strength</th><th>Created</th></tr></thead>
              <tbody>
                {zones?.length === 0 ? <tr><td colSpan={6} style={{textAlign:'center',color:'var(--text-muted)'}}>No active zones</td></tr> :
                  zones?.map(z => (
                    <tr key={z.id}>
                      <td><strong>{z.symbol}</strong></td>
                      <td style={{color: z.zone_type === 'demand' ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight:500, textTransform:'capitalize'}}>{z.zone_type}</td>
                      <td>{formatNumber(z.price_low)}</td>
                      <td>{formatNumber(z.price_high)}</td>
                      <td style={{color: (z.strength || 0) > 0.7 ? 'var(--accent-green)' : (z.strength || 0) > 0.4 ? 'var(--accent-yellow)' : 'var(--text-muted)'}}>{z.strength != null ? `${(z.strength * 100).toFixed(0)}%` : '-'}</td>
                      <td><span className="timestamp">{z.created_at ? formatTimestamp(z.created_at) : '-'}</span></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
