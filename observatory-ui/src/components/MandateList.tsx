import { useState } from 'react';
import { useMandates, formatTimestamp } from '../hooks/useObservatory';

const SYMBOLS = ['', 'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'LINK', 'HYPE', 'ADA', 'NEAR'];
const TYPES = ['', 'ENTRY', 'EXIT', 'BLOCK'];

export default function MandateList() {
  const [symbol, setSymbol] = useState('');
  const [type, setType] = useState('');
  const { data: mandates, isLoading, error } = useMandates({ symbol: symbol || undefined, mandateType: type || undefined, limit: 500 });

  if (error) return <div className="error">Error: {String(error)}</div>;

  return (
    <div>
      <div className="page-header"><h2>Mandates</h2><p>Policy mandate history</p></div>
      <div className="filters">
        <select className="filter-select" value={symbol} onChange={e => setSymbol(e.target.value)}>
          <option value="">All Symbols</option>
          {SYMBOLS.filter(s => s).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={type} onChange={e => setType(e.target.value)}>
          <option value="">All Types</option>
          {TYPES.filter(t => t).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="card">
        {isLoading ? <div className="loading">Loading...</div> : (
          <div className="table-container">
            <table>
              <thead><tr><th>Time</th><th>Symbol</th><th>Type</th><th>Direction</th><th>Source</th><th>Confidence</th></tr></thead>
              <tbody>
                {mandates?.length === 0 ? <tr><td colSpan={6} style={{textAlign:'center',color:'var(--text-muted)'}}>No mandates</td></tr> :
                  mandates?.map(m => (
                    <tr key={m.id}>
                      <td><span className="timestamp">{formatTimestamp(m.timestamp)}</span></td>
                      <td><strong>{m.symbol}</strong></td>
                      <td><span className={`mandate-type mandate-${m.mandate_type.toLowerCase()}`}>{m.mandate_type}</span></td>
                      <td><span className={m.direction === 'LONG' ? 'direction-long' : m.direction === 'SHORT' ? 'direction-short' : ''}>{m.direction || '-'}</span></td>
                      <td>{m.source || '-'}</td>
                      <td>{m.confidence != null ? `${(m.confidence * 100).toFixed(0)}%` : '-'}</td>
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
