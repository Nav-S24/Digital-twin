import { createContext, useContext, useState } from "react";

const VehicleContext = createContext(null);

// Phase 4/7/8's reference fleet uses this ID scheme (Vehicle_0001 ...
// Vehicle_2000); default to the same vehicle used throughout this
// project's own test suites, so every page has real data to show
// immediately.
const DEFAULT_VEHICLE_ID = "Vehicle_0001";

export function VehicleProvider({ children }) {
  const [vehicleId, setVehicleId] = useState(DEFAULT_VEHICLE_ID);
  return (
    <VehicleContext.Provider value={{ vehicleId, setVehicleId }}>
      {children}
    </VehicleContext.Provider>
  );
}

export function useVehicle() {
  const ctx = useContext(VehicleContext);
  if (!ctx) throw new Error("useVehicle must be used within VehicleProvider");
  return ctx;
}
