import FleetAgentChat from "./FleetAgentChat";
import FleetAlerts from "./FleetAlerts";
import FleetGlobe from "./FleetGlobe";
import FleetThermalIr from "./FleetThermalIr";

export default function FleetView() {
  return (
    <div className="fleet">
      <FleetGlobe />
      <FleetAlerts />
      <FleetAgentChat />
      <FleetThermalIr />
    </div>
  );
}
