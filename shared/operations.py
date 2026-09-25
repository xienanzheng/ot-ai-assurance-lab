"""Fictional auxiliary equipment and external-event resilience exercises.

No site models, fault targeting, protection bypasses or offsite health predictions.
"""
from copy import deepcopy
from math import isfinite


def device(tag, name, system, rated, unit, default=100, effect=""):
    return dict(tag=tag, name=name, system=system, rated=rated, unit=unit,
                default=default, effect=effect)


EQUIPMENT = {
    "water": [
        device("SC-101", "Intake screening train", "Intake", 420, "m³/h", effect="Limits raw-water intake capacity."),
        device("MX-111", "Rapid mixer", "Coagulation", 15, "kW", effect="Changes coagulation removal efficiency."),
        device("MX-121", "Flocculator drive", "Flocculation", 8, "kW", effect="Changes floc formation and settled turbidity."),
        device("FT-151A", "Filter train A", "Filtration", 165, "m³/h", effect="Half of available filtration capacity."),
        device("FT-151B", "Filter train B", "Filtration", 165, "m³/h", effect="Half of available filtration capacity."),
        device("P-161", "Sludge withdrawal pump", "Residuals", 12, "m³/h", 55, "Removes simulated clarifier sludge inventory."),
        device("P-171", "Washwater pump", "Backwash", 90, "m³/h", 0, "Automatically follows the PLC backwash request."),
        device("BL-172", "Air-scour blower", "Backwash", 450, "m³/h air", 0, "Supports recovery of filter differential pressure."),
        device("DG-901", "Standby generator", "Electrical", 300, "kW", 0, "Restores part of station capacity during the storm exercise."),
    ],
    "nuclear": [
        device("CP-201A", "Condensate pump A", "Condensate", 800, "kg/s", effect="Supports the main feedwater path."),
        device("CP-201B", "Standby condensate pump B", "Condensate", 800, "kg/s", 0, "Automatically takes duty when A is stopped."),
        device("CW-301A", "Circulating-water pump A", "Heat rejection", 50, "% capacity", effect="Provides half of condenser cooling capacity."),
        device("CW-301B", "Circulating-water pump B", "Heat rejection", 50, "% capacity", effect="Provides half of condenser cooling capacity."),
        device("CT-310", "Cooling-tower fan bank", "Heat rejection", 100, "% assist", effect="Improves condenser heat rejection."),
        device("VP-321", "Condenser vacuum pump", "Condenser", 100, "% capacity", effect="Removes an illustrative condenser pressure penalty."),
        device("LP-401", "Turbine lube-oil pump", "Turbine auxiliaries", 100, "% flow", effect="Loss of flow removes the turbine operating permissive."),
        device("HX-501", "Industrial heat circulation pump", "Heat dispatch", 720, "kg/s", effect="Limits non-safety industrial heat dispatch."),
    ],
    "grid": [
        device("GT-301", "Peaking reserve generator", "Generation reserves", 150, "MW", 0, "Adds dispatchable output at Central bus B2."),
        device("HY-302", "Hydro reserve allocation", "Generation reserves", 50, "MW", 0, "Adds bounded reserve output at Central bus B2."),
        device("TF-401", "North transformer cooling", "Transformer auxiliaries", 100, "% cooling", effect="Changes adjacent line thermal ratings, not power flow."),
        device("TF-402", "Central transformer cooling", "Transformer auxiliaries", 100, "% cooling", effect="Changes adjacent line thermal ratings, not power flow."),
        device("SC-501", "Synchronous condenser", "Voltage support", 80, "MVAr", 0, "Adds support to the illustrative voltage model."),
        device("CB-502", "South capacitor stage", "Voltage support", 40, "MVAr", 0, "Adds bounded reactive support."),
        device("DR-601", "Commercial demand-response block", "Demand management", 60, "MW", 0, "Reduces requested Metro demand; tracked separately from outages."),
        device("DR-602", "Industrial demand-response block", "Demand management", 50, "MW", 0, "Reduces requested Industrial demand; tracked separately from outages."),
    ],
}

INCIDENTS = {
    "water": [
        dict(id="storm_supply", name="Severe storm · water-service emergency", description="An external storm reduces station power and intake availability. Observe storage, demand coverage and standby-power recovery."),
        dict(id="storm_water_quality", name="Storm runoff · treatment stress", description="A simulated raw-water turbidity surge challenges mixing and filtration. Monitor process quality and service continuity."),
    ],
    "nuclear": [
        dict(id="regional_grid_disturbance", name="Regional grid disturbance · protective shutdown", description="The fictional grid connection is lost. Independent protection shuts down generation; monitor residual heat and auxiliary-system response."),
        dict(id="hot_weather", name="Extreme heat · condenser limitation", description="Hot ambient conditions reduce condenser performance. Observe output limits and deterministic protection."),
    ],
    "grid": [
        dict(id="regional_supply_shortfall", name="Regional supply emergency", description="An external regional event reduces available generation. Observe unmet demand, reserves, battery response and community service loss."),
        dict(id="extreme_demand", name="Extreme heat · demand emergency", description="A fictional heatwave sharply increases demand and reduces thermal equipment ratings. Deploy reserves and demand response."),
    ],
}


class OperationsModel:
    def __init__(self, domain):
        self.domain = domain
        self.devices = {d["tag"]: dict(d, mode="auto", setpoint_pct=d["default"],
            feedback_pct=float(d["default"]), runtime_min=0, starts=0) for d in EQUIPMENT[domain]}
        self.incident = None
        self.minute = 0
        self.sludge_inventory_pct = 35.0
        self.shortfall_minutes = 0.0
        self.last_observed = 0

    def fraction(self, tag):
        return self.devices[tag]["feedback_pct"] / 100.0

    def active(self, name):
        return self.incident is not None and self.incident["id"] == name

    def command(self, changes):
        if not changes:
            raise ValueError("Select at least one equipment change")
        proposed = deepcopy(self.devices)
        for tag, request in changes.items():
            if tag not in proposed:
                raise ValueError("Unknown auxiliary equipment tag")
            if not isinstance(request, dict) or set(request) - {"mode", "setpoint_pct"}:
                raise ValueError("Only operating mode and bounded setpoint are supported")
            mode = request.get("mode", proposed[tag]["mode"])
            pct = request.get("setpoint_pct", proposed[tag]["setpoint_pct"])
            if mode not in {"auto", "run", "off"} or isinstance(pct, bool) or not isinstance(pct, (float, int)) or not isfinite(pct) or not 0 <= pct <= 100:
                raise ValueError("Select Auto, Run or Off, with a finite 0–100% setpoint")
            proposed[tag].update(mode=mode, setpoint_pct=float(pct))
        # Operator changes cannot intentionally remove every treatment/cooling path.
        groups = {"water": [("FT-151A", "FT-151B")], "nuclear": [("CW-301A", "CW-301B"), ("CP-201A", "CP-201B")], "grid": []}
        for group in groups[self.domain]:
            if all(proposed[tag]["mode"] == "off" or (proposed[tag]["mode"] == "run" and proposed[tag]["setpoint_pct"] < 25) for tag in group):
                raise ValueError("Permissive requires one available train in this equipment group")
        self.devices = proposed

    def start_incident(self, name, minute, duration):
        definition = next((s for s in INCIDENTS[self.domain] if s["id"] == name), None)
        if definition is None:
            raise ValueError("Unknown predefined incident for this domain")
        if self.incident:
            raise ValueError("End the current incident before starting another")
        self.incident = dict(definition, started_minute=minute, ends_minute=minute+duration)

    def tick(self, minute, journal, backwash=False, emergency=False):
        self.minute = minute
        if self.incident and minute >= self.incident["ends_minute"]:
            journal.event(minute, "incident_ended", self.incident["name"])
            self.incident = None
        for tag, d in self.devices.items():
            target = d["setpoint_pct"] if d["mode"] == "run" else d["default"] if d["mode"] == "auto" else 0.0
            if d["mode"] == "auto":
                if tag in {"P-171", "BL-172"}: target = 100.0 if backwash else 0.0
                if tag == "DG-901": target = 100.0 if self.active("storm_supply") else 0.0
                if tag == "CP-201B": target = 100.0 if (self.devices["CP-201A"]["mode"] == "off" or (self.devices["CP-201A"]["mode"] == "run" and self.devices["CP-201A"]["setpoint_pct"] < 25)) else 0.0
            if emergency and self.domain == "water": target = 0.0
            previous = d["feedback_pct"]
            # Off/permissive removal is immediate; commanded starts ramp over minutes.
            d["feedback_pct"] = 0.0 if target == 0 else previous + max(-25.0, min(25.0, target-previous))
            if previous == 0 and d["feedback_pct"] > 0: d["starts"] += 1
            if d["feedback_pct"] > 0: d["runtime_min"] += 1

    def coverage(self, sim):
        if self.domain == "water":
            demand, served = sum(sim.zone_demands), sum(sim.zone_served)
        elif self.domain == "grid":
            demand, served = sim.demand_mw, sim.served_load_mw
        else:
            demand, served = 1000.0, sim.electric_output_mwe
        return min(1.0, max(0.0, served/max(demand, 0.001)))

    def observe(self, sim):
        if sim.minute > self.last_observed:
            self.shortfall_minutes += (1-self.coverage(sim)) * (sim.minute-self.last_observed)
            self.last_observed = sim.minute

    def alarms(self):
        alarms = []
        if self.incident:
            alarms.append(dict(code="EXTERNAL_INCIDENT_ACTIVE", message=self.incident["name"], severity="warning"))
        if self.domain == "nuclear" and self.fraction("LP-401") < .25:
            alarms.append(dict(code="TURBINE_AUX_PERMISSIVE", message="Turbine auxiliary oil-flow permissive is not satisfied", severity="critical"))
        return alarms

    def snapshot(self, sim):
        fraction = self.coverage(sim)
        if self.domain == "water":
            districts = [dict(name=f"Water district {i+1}", coverage_pct=round(100*served/max(demand,.001),2))
                         for i,(served,demand) in enumerate(zip(sim.zone_served,sim.zone_demands))]
        elif self.domain == "grid":
            districts = [dict(name=f"Bus B{i+1} service area", coverage_pct=round(100*served/max(demand,.001),2))
                         for i,(served,demand) in enumerate(zip(sim.served_by_bus,sim.loads))]
        else:
            districts = []
        accounts = 18000 if self.domain == "water" else 120000 if self.domain == "grid" else None
        devices = []
        for d in self.devices.values():
            item = dict(d)
            item.update(output=round(d["rated"]*d["feedback_pct"]/100,2), feedback_pct=round(d["feedback_pct"],1),
                        status="running" if d["feedback_pct"]>0 else "standby" if d["mode"]=="auto" else "stopped")
            devices.append(item)
        return dict(devices=devices, incident=deepcopy(self.incident), incident_definitions=INCIDENTS[self.domain],
            impact=dict(coverage_pct=round(fraction*100,2), severity="severe" if fraction<.5 else "disrupted" if fraction<.9 else "stable",
                label="Station generation available" if self.domain=="nuclear" else "Demand served",
                equivalent_accounts_affected=round(accounts*(1-fraction)) if accounts else None,
                assumed_accounts=accounts, equivalent_full_loss_minutes=round(self.shortfall_minutes,3), districts=districts,
                note="Fictional service-equivalent accounts, proportional to unmet demand; not population or casualty estimates." if accounts else "Lost station generation is not a city outage estimate. No offsite radiation, release or casualty model."),
            sludge_inventory_pct=round(self.sludge_inventory_pct,2) if self.domain=="water" else None)
