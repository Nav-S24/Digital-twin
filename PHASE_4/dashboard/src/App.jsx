// src/App.jsx
import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import Sidebar         from './components/Sidebar'
import VehicleSelector from './components/VehicleSelector'
import Overview        from './pages/Overview'
import Components      from './pages/Components'
import FailureRisk     from './pages/FailureRisk'
import Simulation      from './pages/Simulation'
import History         from './pages/History'
import TwinVisualizer  from './pages/TwinVisualizer'
import Fleet           from './pages/Fleet'
import './styles/global.css'

const DEFAULT_VEHICLE = 'Vehicle_0001'

function AppLayout() {
  const [vehicleId, setVehicleId] = useState(DEFAULT_VEHICLE)
  const navigate = useNavigate()

  // When a vehicle is selected from the Fleet page, switch to it and go to overview
  const handleFleetSelect = (vid) => {
    setVehicleId(vid)
    navigate('/')
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar vehicleId={vehicleId} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Top bar */}
        <header style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0.875rem 1.5rem',
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
          position: 'sticky', top: 0, zIndex: 50,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: 'var(--health-good)',
              boxShadow: '0 0 6px var(--health-good)',
            }} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Twin Online · Phase 4</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Active Vehicle</span>
            <VehicleSelector value={vehicleId} onChange={setVehicleId} />
          </div>
        </header>

        {/* Main content */}
        <main style={{
          flex: 1,
          padding: '1.5rem',
          maxWidth: 1200,
          width: '100%',
          margin: '0 auto',
          boxSizing: 'border-box',
        }}>
          <Routes>
            <Route path="/"           element={<Overview       vehicleId={vehicleId} />} />
            <Route path="/components" element={<Components     vehicleId={vehicleId} />} />
            <Route path="/failure"    element={<FailureRisk    vehicleId={vehicleId} />} />
            <Route path="/simulation" element={<Simulation     vehicleId={vehicleId} />} />
            <Route path="/history"    element={<History        vehicleId={vehicleId} />} />
            <Route path="/twin"       element={<TwinVisualizer vehicleId={vehicleId} />} />
            <Route path="/fleet"      element={<Fleet          onSelectVehicle={handleFleetSelect} />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer style={{
          padding: '0.65rem 1.5rem',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex', justifyContent: 'space-between',
          fontSize: 11, color: 'var(--text-muted)',
        }}>
          <span>Vehicle Digital Twin Platform · Phase 4</span>
          <span>Tata Motors iRA / TETHER · 2000 vehicles · FastAPI + React</span>
        </footer>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}
