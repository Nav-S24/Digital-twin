import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, HeartPulse, Wrench, Boxes, ScanLine,
  BookOpen, Map, Gauge as GaugeIcon,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/health", label: "Health Score", icon: HeartPulse, phase: "02" },
  { to: "/maintenance", label: "Predictive Maintenance", icon: Wrench, phase: "03" },
  { to: "/twin", label: "Digital Twin", icon: Boxes, phase: "04" },
  { to: "/obd", label: "OBD Diagnostics", icon: ScanLine, phase: "05" },
  { to: "/knowledge", label: "Knowledge Base", icon: BookOpen, phase: "06" },
  { to: "/trip", label: "Trip Planner", icon: Map, phase: "08" },
  { to: "/driver", label: "Driver Behaviour", icon: GaugeIcon, phase: "09" },
];

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 h-full bg-brand border-r border-brand-dark flex flex-col text-white">
      <div className="px-5 py-5 border-b border-white/15">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-white/15 flex items-center justify-center">
            <GaugeIcon size={16} className="text-white" strokeWidth={2.25} />
          </div>
          <div>
            <span className="font-display font-semibold text-sm tracking-wide block leading-tight">VEHICLE BRAIN</span>
            <p className="text-[10px] text-white/60 mt-0.5">Digital twin platform</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV.map(({ to, label, icon: Icon, end, phase }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm mb-0.5 transition-colors ${
                isActive
                  ? "bg-white text-brand font-medium shadow-sm"
                  : "text-white/80 hover:text-white hover:bg-white/10"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={16} strokeWidth={2} />
                <span className="flex-1">{label}</span>
                {phase && (
                  <span className={`text-[10px] font-mono ${isActive ? "text-brand/60" : "text-white/45"}`}>
                    P{phase}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-white/15">
        <p className="text-[10px] text-white/50 leading-relaxed">
          Personalized Vehicle Brain &amp;<br />Health Digital Twin
        </p>
      </div>
    </aside>
  );
}
