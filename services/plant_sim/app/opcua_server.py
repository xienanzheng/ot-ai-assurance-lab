from __future__ import annotations

from asyncua import Server, ua

from shared.opcua_nodes import ACTUATOR_NODES, NAMESPACE_URI, SENSOR_NODES


class WaterOpcUaServer:
    def __init__(self, simulator) -> None:
        self.simulator = simulator
        self.server = Server()
        self.index = 0
        self.sensor_nodes = {}
        self.quality_nodes = {}
        self.actuator_nodes = {}
        self.system_nodes = {}

    async def start(self) -> None:
        await self.server.init()
        self.server.set_endpoint("opc.tcp://0.0.0.0:4840/waterlab/server/")
        self.server.set_server_name("WaterLab OT Simulator")
        self.index = await self.server.register_namespace(NAMESPACE_URI)
        root = await self.server.nodes.objects.add_object(self.index, "WaterLab")
        sensors = await root.add_object(self.index, "Sensors")
        actuators = await root.add_object(self.index, "Actuators")
        system = await root.add_object(self.index, "System")

        snapshot = self.simulator.snapshot()
        for name in SENSOR_NODES:
            value = snapshot.sensors[name].value
            self.sensor_nodes[name] = await sensors.add_variable(ua.NodeId(f"Sensors.{name}", self.index), name, value)
            self.quality_nodes[name] = await sensors.add_variable(ua.NodeId(f"Sensors.{name}.quality", self.index), f"{name}_quality", snapshot.sensors[name].quality)
        for name in ACTUATOR_NODES:
            value = snapshot.actuators[name]
            node = await actuators.add_variable(ua.NodeId(f"Actuators.{name}", self.index), name, value)
            await node.set_writable()
            self.actuator_nodes[name] = node
        defaults = {
            "simulation_time": snapshot.simulation_time.isoformat(),
            "elapsed_minutes": snapshot.elapsed_minutes,
            "simulation_speed": snapshot.simulation_speed,
            "controller_mode": snapshot.controller_mode.value,
            "active_scenario": snapshot.scenario,
            "alarm_state": snapshot.safety_state,
            "emergency_stop": snapshot.emergency_stop,
        }
        for name, value in defaults.items():
            self.system_nodes[name] = await system.add_variable(ua.NodeId(f"System.{name}", self.index), name, value)
        await self.server.start()

    async def sync(self) -> None:
        snapshot = self.simulator.snapshot()
        changes = {}
        for name, node in self.actuator_nodes.items():
            changes[name] = await node.read_value()
        self.simulator.set_actuators(changes)
        for name, node in self.sensor_nodes.items():
            await node.write_value(snapshot.sensors[name].value)
            await self.quality_nodes[name].write_value(snapshot.sensors[name].quality)
        await self.system_nodes["simulation_time"].write_value(snapshot.simulation_time.isoformat())
        await self.system_nodes["elapsed_minutes"].write_value(snapshot.elapsed_minutes)
        await self.system_nodes["simulation_speed"].write_value(snapshot.simulation_speed)
        await self.system_nodes["controller_mode"].write_value(snapshot.controller_mode.value)
        await self.system_nodes["active_scenario"].write_value(snapshot.scenario)
        await self.system_nodes["alarm_state"].write_value(snapshot.safety_state)
        await self.system_nodes["emergency_stop"].write_value(snapshot.emergency_stop)

    async def push_actuators(self) -> None:
        """Publish simulator defaults after a reset so stale OPC commands do not return."""
        snapshot = self.simulator.snapshot()
        for name, node in self.actuator_nodes.items():
            await node.write_value(snapshot.actuators[name])

    async def stop(self) -> None:
        await self.server.stop()
