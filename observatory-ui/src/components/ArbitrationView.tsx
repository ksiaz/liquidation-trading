import { useState } from 'react';
import { useArbitration, formatTimestamp } from '../hooks/useObservatory';

const SYMBOLS = ['', 'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'LINK', 'HYPE', 'ADA', 'NEAR'];

export default function ArbitrationView() {
  const [symbol, setSymbol] = useState('');
  const { data: rounds, isLoading, error } = useArbitration({ symbol: symbol || undefined, limit: 500 });

  if (error) return <div className="error">Error: {String(error)}</div>;

  return (
    <div>
      <div className="page-header"><h2>Arbitration</h2><p>Mandate resolution history</p></div>
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
              <thead><tr><th>Time</th><th>Symbol</th><th>Mandates</th><th>Action</th><th>Theorem</th><th>Winner ID</th></tr></thead>
              <tbody>
                {rounds?.length === 0 ? <tr><td colSpan={6} style={{textAlign:'center',color:'var(--text-muted)'}}>No arbitration rounds</td></tr> :
                  rounds?.map(r => (
                    <tr key={r.id}>
                      <td><span className="timestamp">{r.timestamp ? formatTimestamp(r.timestamp) : '-'}</span></td>
                      <td><strong>{r.symbol}</strong></td>
                      <td>{r.mandate_count ?? '-'}</td>
                      <td style={{fontWeight:500}}>{r.action_taken || '-'}</td>
                      <td style={{color:'var(--accent-blue)'}}>{r.theorem_applied || '-'}</td>
                      <td><span className="timestamp">{r.winning_mandate_id ?? '-'}</span></td>
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
