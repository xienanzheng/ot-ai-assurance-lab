"""Minute-resolution exercise evidence, independent of operator acknowledgement."""
from collections import deque
from copy import deepcopy
from uuid import uuid4


class ExerciseRecorder:
    def __init__(self, domain, scenario, seed=None):
        self.run_id = str(uuid4())
        self.domain, self.scenario, self.seed = domain, scenario, seed
        self.samples = deque(maxlen=1441)
        self.events = deque(maxlen=2000)
        self.active = {}
        self.count = 0
        self.total_samples = 0
        self.critical_minutes = 0
        self.integrals = {}
        self.last_minute = None

    def event(self, minute, kind, message, **details):
        self.count += 1
        item = dict(id=self.count, minute=minute, kind=kind, message=message, **details)
        self.events.append(item)
        return item

    def capture(self, snapshot, minute):
        data = snapshot.model_dump(mode="json")
        self.sensor_units = {key: item["unit"] for key, item in data["sensors"].items()}
        self.tuning = data.get("tuning", {})
        alarms = data.get("active_alarms", data.get("alarms", []))
        current = {a["code"]: a for a in alarms}
        for code in sorted(self.active.keys() - current.keys()):
            self.event(minute, "cleared", self.active[code]["message"], code=code)
            del self.active[code]
        for code, alarm in current.items():
            if code not in self.active:
                event = self.event(minute, "alarm", alarm["message"], code=code, severity=alarm["severity"])
                self.active[code] = dict(alarm, occurrence=event["id"], first_minute=minute, acknowledged=False)
        if minute == self.last_minute:
            return
        values = {key: item["value"] for key, item in data["sensors"].items()}
        qualities = {key: item.get("quality", "good") for key, item in data["sensors"].items()}
        if self.last_minute is not None:
            dt = minute - self.last_minute
            if any(a["severity"] == "critical" for a in alarms):
                self.critical_minutes += dt
            for tag, metric in [("energy_kw", "energy_kwh"), ("electric_output_mwe", "electric_energy_mwh"),
                                ("unserved_load_mw", "unserved_energy_mwh"), ("unserved_water_m3h", "unserved_water_m3"),
                                ("clearwell_overflow_m3h", "overflow_m3")]:
                if tag in values:
                    self.integrals[metric] = self.integrals.get(metric, 0.0) + values[tag] * dt / 60
        self.last_minute = minute
        self.total_samples += 1
        self.samples.append(dict(minute=minute, simulation_time=data["simulation_time"], values=values,
                                 quality=qualities, controls=data.get("controls", data.get("actuators", {})),
                                 mode=data.get("controller_mode"), alarms=list(current),
                                 auxiliary_controls={d["tag"]: {k:d[k] for k in ("mode", "setpoint_pct", "feedback_pct")} for d in data.get("operations", {}).get("devices", [])},
                                 incident=data.get("operations", {}).get("incident"),
                                 community_impact=data.get("operations", {}).get("impact", {})))

    def acknowledge(self, occurrence, minute):
        alarm = next((a for a in self.active.values() if a["occurrence"] == occurrence), None)
        if alarm is None:
            raise ValueError("Alarm occurrence is no longer active; refresh the exercise")
        if not alarm["acknowledged"]:
            alarm["acknowledged"] = True
            self.event(minute, "acknowledged", alarm["message"], code=alarm["code"], occurrence=occurrence)

    def report(self, include_samples=False):
        result = dict(run_id=self.run_id, domain=self.domain, scenario=self.scenario, seed=self.seed,
                      sensor_units=getattr(self, "sensor_units", {}), tuning=getattr(self, "tuning", {}),
                      elapsed_minutes=self.last_minute or 0, sample_count=self.total_samples,
                      retained_samples=len(self.samples), dropped_samples=self.total_samples - len(self.samples),
                      dropped_events=max(0, self.count - len(self.events)),
                      critical_minutes=self.critical_minutes,
                      metrics={k: round(v, 4) for k, v in self.integrals.items()},
                      alarms=list(self.active.values()), events=list(reversed(self.events))[:100],
                      recent_samples=list(self.samples)[-120:],
                      retention="In memory: latest 1441 minute samples and 2000 events. Export before reset or service restart.")
        if include_samples:
            result.update(samples=list(self.samples), events=list(self.events))
        return deepcopy(result)
