import { useSnapshot, formatUptime, formatNumber } from '../hooks/useObservatory';
import type { StabilityStatus } from '../types/observatory';

function StatusBadge({ status }: { status: StabilityStatus }) {
  return <span className={`status-badge status-${status.toLowerCase()}`}>{status}</span>;
}

export default function Dashboard() {
  const { data: snapshot, isLoading, error } = useSnapshot();

  if (isLoading) return <div className="loading">Loading dashboard...</div>;
  if (error) return <div className="error">Error: {String(error)}</div>;
  if (!snapshot) return <div className="loading">No data</div>;

  return (
    <div>
      <div className="page-header"><h2>Dashboard</h2><p>System overview</p></div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">System Status</span>
          <StatusBadge status={snapshot.stability.status} />
        </div>
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-label">Status</div><div className="stat-value">{snapshot.health.status}</div></div>
          <div className="stat-card"><div className="stat-label">Uptime</div><div className="stat-value">{formatUptime(snapshot.health.uptime_seconds)}</div></div>
          <div className="stat-card"><div className="stat-label">Memory</div><div className="stat-value">{formatNumber(snapshot.health.memory_mb, 0)} MB</div></div>
          <div className="stat-card"><div className="stat-label">Cycles</div><div className="stat-value">{snapshot.health.cycles_completed.toLocaleString()}</div></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Mandates (24h)</span></div>
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-label">Total</div><div className="stat-value">{snapshot.mandate_counts.total}</div></div>
          <div className="stat-card"><div className="stat-label">Entry</div><div className="stat-value" style={{color:'var(--accent-green)'}}>{snapshot.mandate_counts.entry}</div></div>
          <div className="stat-card"><div className="stat-label">Exit</div><div className="stat-value" style={{color:'var(--accent-blue)'}}>{snapshot.mandate_counts.exit}</div></div>
          <div className="stat-card"><div className="stat-label">Block</div><div className="stat-value" style={{color:'var(--accent-red)'}}>{snapshot.mandate_counts.block}</div></div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">Activity</span></div>
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-label">Active Zones</div><div className="stat-value">{snapshot.active_zones_count}</div></div>
          <div className="stat-card"><div className="stat-label">Liquidations</div><div className="stat-value">{snapshot.recent_liquidations_count}</div></div>
          <div className="stat-card"><div className="stat-label">Issues</div><div className="stat-value" style={{color: snapshot.stability.issues_total > 0 ? 'var(--accent-yellow)' : 'inherit'}}>{snapshot.stability.issues_total}</div></div>
          <div className="stat-card"><div className="stat-label">Actions</div><div className="stat-value">{snapshot.stability.total_actions}</div></div>
        </div>
      </div>
    </div>
  );
}
