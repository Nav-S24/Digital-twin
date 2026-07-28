import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { VehicleProvider } from "./context/VehicleContext";

import Overview from "./pages/Overview";
import HealthScore from "./pages/HealthScore";
import PredictiveMaintenance from "./pages/PredictiveMaintenance";
import DigitalTwin from "./pages/DigitalTwin";
import OBDDiagnostics from "./pages/OBDDiagnostics";
import KnowledgeBase from "./pages/KnowledgeBase";
import TripPlanner from "./pages/TripPlanner";
import DriverBehavior from "./pages/DriverBehavior";

export default function App() {
  return (
    <VehicleProvider>
      <BrowserRouter>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <TopBar />
            <main className="flex-1 overflow-y-auto p-4 md:p-6 min-h-0">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/health" element={<HealthScore />} />
                <Route path="/maintenance" element={<PredictiveMaintenance />} />
                <Route path="/twin" element={<DigitalTwin />} />
                <Route path="/obd" element={<OBDDiagnostics />} />
                <Route path="/knowledge" element={<KnowledgeBase />} />
                <Route path="/trip" element={<TripPlanner />} />
                <Route path="/driver" element={<DriverBehavior />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </VehicleProvider>
  );
}
