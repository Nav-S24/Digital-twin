import ChatPanel from "./components/ChatPanel";

export default function App() {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        background: "#0f1117"
      }}
    >
      <ChatPanel
        vehicleId="Vehicle_0001"
        apiBaseUrl="http://localhost:8000"
      />
    </div>
  );
}