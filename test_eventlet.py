import async_runtime
async_runtime.monkey_patch(all=True)

import time
import requests
import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

def test_requests():
    print("Testing requests...")
    start = time.time()
    try:
        r = requests.get('http://172.22.40.9', timeout=2)
        print(f"Requests ok, status: {r.status_code}")
    except Exception as e:
        print(f"Requests error: {e}")
    print(f"Requests took {time.time()-start:.2f}s")

async def _test_snmp():
    transport = await UdpTransportTarget.create(('172.22.40.9', 161), timeout=2, retries=1)
    engine = SnmpEngine()
    errI, errS, errX, varBinds = await get_cmd(
        engine, CommunityData('public', mpModel=1), transport, ContextData(), ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0'))
    )
    if errI:
        print(f"SNMP err: {errI}")
    else:
        print(f"SNMP ok: {varBinds[0][1]}")

def test_snmp():
    print("Testing SNMP...")
    start = time.time()
    try:
        import sys
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(_test_snmp())
    except Exception as e:
        print(f"SNMP error: {e}")
    print(f"SNMP took {time.time()-start:.2f}s")

def background_yield():
    for _ in range(5):
        print("Background greenlet running...")
        async_runtime.sleep(0.5)

if __name__ == '__main__':
    async_runtime.spawn(background_yield)
    test_requests()
    test_snmp()
    async_runtime.sleep(3)
