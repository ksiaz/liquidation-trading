import { useState } from 'react';
import { useLiquidations, formatTimestamp, formatUSD, formatNumber } from '../hooks/useObservatory';

const SYMBOLS = ['', 'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'LINK', 'HYPE', 'ADA', 'NEAR'];
const SIDES = ['', 'LONG', 'SHORT'];

export default function LiquidationFeed() {
  const [symbol, setSymbol] = useState('');
  const [side, setSide] = useState('');
  const { data: liquidations, isLoading, error } = useLiquidations({ symbol: symbol || undefined, side: side || undefined, limit: 500 });

  if (error) return <div className="error">Error: {String(error)}</div>;

  const totalSize = liquidations?.reduce((sum, l) => sum + (l.size || 0), 0) || 0;
  const longCount = liquidations?.filter(l => l.side === 'LONG').length || 0;
  const shortCount = liquidations?.filter(l => l.side === 'SHORT').length || 0;

  return (
    <div>
      <div className="page-header"><h2>Liquidations</h2><p>Liquidation event feed</p></div>
      <div className="stats-grid" style={{marginBottom:'1rem'}}>
        <div className="stat-card"><div className="stat-label">Total Events</div><div className="stat-value">{liquidations?.length || 0}</div></div>
        <div className="stat-card"><div className="stat-label">Total Volume</div><div className="stat-value">{formatUSD(totalSize)}</div></div>
        <div className="stat-card"><div className="stat-label">Long Liqs</div><div className="stat-value" style={{color:'var(--accent-green)'}}>{longCount}</div></div>
        <div className="stat-card"><div className="stat-label">Short Liqs</div><div className="stat-value" style={{color:'var(--accent-red)'}}>{shortCount}</div></div>
      </div>
      <div className="filters">
        <select className="filter-select" value={symbol} onChange={e => setSymbol(e.target.value)}>
          <option value="">All Symbols</option>
          {SYMBOLS.filter(s => s).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={side} onChange={e => setSide(e.target.value)}>
          <option value="">All Sides</option>
          {SIDES.filter(s => s).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="card">
        {isLoading ? <div className="loading">Loading...</div> : (
          <div className="table-container">
            <table>
              <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Size (USD)</th><th>Price</th></tr></thead>
              <tbody>
                {liquidations?.length === 0 ? <tr><td colSpan={5} style={{textAlign:'center',color:'var(--text-muted)'}}>No liquidations</td></tr> :
                  liquidations?.map(l => (
                    <tr key={l.id}>
                      <td><span className="timestamp">{formatTimestamp(l.timestamp)}</span></td>
                      <td><strong>{l.symbol}</strong></td>
                      <td><span className={l.side === 'LONG' ? 'direction-long' : l.side === 'SHORT' ? 'direction-short' : ''}>{l.side || '-'}</span></td>
                      <td>{formatUSD(l.size)}</td>
                      <td>{formatNumber(l.price)}</td>
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
