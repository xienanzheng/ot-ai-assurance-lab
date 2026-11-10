"""Simulation-only OPC UA envelope; external vendors require an explicit tag adapter."""
import asyncio
from contextlib import asynccontextmanager, suppress
import time
from uuid import uuid4
from asyncua import Client, Server, ua
from .contracts import Snapshot

NAMESPACE='urn:ot-assurance:v2'


@asynccontextmanager
async def serve_opc(controller,endpoint):
    server=Server(); await server.init(); server.set_endpoint(endpoint)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    idx=await server.register_namespace(NAMESPACE)
    obj=await server.nodes.objects.add_object(idx,'Bench')
    node=await obj.add_variable(ua.NodeId('snapshot',idx),'Snapshot',controller.snapshot().model_dump_json())
    # Not writable: all target requests use the scoped receiver, never raw UA writes.
    async def publish():
        while True:
            await node.write_value(controller.snapshot().model_dump_json())
            await asyncio.sleep(.2)
    async with server:
        task=asyncio.create_task(publish())
        try: yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError): await task


class OpcSource:
    def __init__(self,endpoint):
        self.endpoint=endpoint; self.latest=None; self.epoch=str(uuid4()); self.client=None
    async def __aenter__(self):
        self.client=Client(self.endpoint,timeout=3)
        await self.client.connect()
        try:
            idx=await self.client.get_namespace_index(NAMESPACE)
            self.node=self.client.get_node(ua.NodeId('snapshot',idx))
            self.subscription=await self.client.create_subscription(200,self)
            await self.subscription.subscribe_data_change(self.node)
        except BaseException:
            await self.client.disconnect(); raise
        return self
    async def __aexit__(self,*args):
        if self.client:
            with suppress(Exception): await self.subscription.delete()
            with suppress(Exception): await self.client.disconnect()
    def datachange_notification(self,node,value,data):
        self.latest=(value,time.time())
    async def capture(self,package):
        # Integrity read checks channel + DataValue status. Subscription caches never
        # refresh source timestamps and are never returned after a failed read.
        dv=await self.node.read_data_value()
        dv.StatusCode.check()
        snapshot=Snapshot.model_validate_json(dv.Value.Value)
        if snapshot.package_hash!=package.fingerprint(): raise ValueError('OPC package mismatch')
        # One serialized versioned envelope is the server's atomic snapshot boundary.
        return snapshot.model_copy(update={'received_at':time.time(),'connection_epoch':self.epoch})
