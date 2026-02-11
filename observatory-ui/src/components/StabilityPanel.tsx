import { useStability } from '../hooks/useObservatory';
import type { StabilityStatus } from '../types/observatory';

function StatusBadge({ status }: { status: StabilityStatus }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}>{status}</span>;
}

export default function StabilityPanel() {
  const { data: stability, isLoading, error } = useStability();

  if (isLoading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {String(error)}</div>;
  if (!stability) return <div className="loading">No data</div>;

  return (
    <div>
      <div className="page-header"><h2>Stability</h2><p>Stability observer status</p></div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Current Status</span>
          <StatusBadge status={stability.status} />
        </div>
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-label">Total Mandates</div><div className="stat-value">{stability.total_mandates.toLocaleString()}</div></div>
          <div className="stat-card"><div className="stat-label">Total Actions</div><div className="stat-value">{stability.total_actions.toLocaleString()}</div></div>
          <div className="stat-card"><div className="stat-label">Issues</div><div className="stat-value" style={{color: stability.issues_total > 0 ? 'var(--accent-yellow)' : 'var(--accent-green)'}}>{stability.issues_total}</div></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Detection Thresholds</span></div>
        <div style={{fontSize:'0.875rem',color:'var(--text-secondary)'}}>
          <div style={{marginBottom:'0.5rem'}}><strong>Storm:</strong> More than 50 mandates in 60 seconds</div>
          <div style={{marginBottom:'0.5rem'}}><strong>Oscillation:</strong> More than 3 ENTRY/EXIT cycles in 30 seconds</div>
          <div style={{marginBottom:'0.5rem'}}><strong>Direction Flip:</strong> More than 3 LONG/SHORT reversals</div>
          <div><strong>Deadlock:</strong> No mandates for 300 seconds</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Recent Issues</span>
          <span style={{color:'var(--text-muted)',fontSize:'0.875rem'}}>Last 10</span>
        </div>
        {stability.recent_issues.length === 0 ? (
          <div style={{padding:'1rem',color:'var(--text-muted)',textAlign:'center'}}>No issues detected</div>
        ) : (
          <div>
            {stability.recent_issues.map((issue, idx) => (
              <div key={idx} style={{padding:'0.75rem',borderBottom:'1px solid var(--border-color)',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                <div>
                  <div style={{fontWeight:500,marginBottom:'0.25rem'}}>{issue.issue}</div>
                  <div style={{fontSize:'0.875rem',color:'var(--text-secondary)'}}>Symbol: <strong>{issue.symbol}</strong></div>
                </div>
                <span style={{color: issue.severity === 'CRITICAL' ? 'var(--accent-red)' : issue.severity === 'WARNING' ? 'var(--accent-yellow)' : 'var(--text-muted)', fontSize:'0.75rem',fontWeight:500,textTransform:'uppercase'}}>{issue.severity}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{backgroundColor:'var(--bg-tertiary)'}}>
        <div className="card-header"><span className="card-title">Constitutional Constraint</span></div>
        <p style={{fontSize:'0.875rem',color:'var(--text-secondary)'}}>
          The Stability Observer is <strong>read-only</strong>. It cannot block mandates, halt execution, or influence the trading system. Even CRITICAL status has no effect on operation. This is by design - observation without influence.
        </p>
      </div>
    </div>
  );
}
