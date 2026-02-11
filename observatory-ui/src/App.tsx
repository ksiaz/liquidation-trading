import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import MandateList from './components/MandateList';
import ArbitrationView from './components/ArbitrationView';
import ZoneTable from './components/ZoneTable';
import LiquidationFeed from './components/LiquidationFeed';
import StabilityPanel from './components/StabilityPanel';

function App() {
  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Observatory</h1>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
          Read-only observation
        </p>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/mandates">Mandates</NavLink>
          <NavLink to="/arbitration">Arbitration</NavLink>
          <NavLink to="/zones">Zones</NavLink>
          <NavLink to="/liquidations">Liquidations</NavLink>
          <NavLink to="/stability">Stability</NavLink>
        </nav>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/mandates" element={<MandateList />} />
          <Route path="/arbitration" element={<ArbitrationView />} />
          <Route path="/zones" element={<ZoneTable />} />
          <Route path="/liquidations" element={<LiquidationFeed />} />
          <Route path="/stability" element={<StabilityPanel />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
