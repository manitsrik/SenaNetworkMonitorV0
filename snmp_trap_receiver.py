"""
SNMP Trap Receiver for Network Monitor
Listens for SNMP traps on UDP port 162 and stores them in the database
"""
import threading
import json
from datetime import datetime

try:
    from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
    from pysnmp.carrier.asyncio.dgram import udp
    from pyasn1.codec.ber import decoder
    from pysnmp.proto import api
    TRAP_AVAILABLE = True
except ImportError:
    TRAP_AVAILABLE = False
    print("[TrapReceiver] pysnmp trap modules not available")

# Well-known trap OID mappings
TRAP_NAMES = {
    '1.3.6.1.6.3.1.1.5.1': 'coldStart',
    '1.3.6.1.6.3.1.1.5.2': 'warmStart',
    '1.3.6.1.6.3.1.1.5.3': 'linkDown',
    '1.3.6.1.6.3.1.1.5.4': 'linkUp',
    '1.3.6.1.6.3.1.1.5.5': 'authenticationFailure',
    '1.3.6.1.6.3.1.1.5.6': 'egpNeighborLoss',
}

# Map trap OIDs to severity
TRAP_SEVERITY = {
    '1.3.6.1.6.3.1.1.5.1': 'warning',    # coldStart
    '1.3.6.1.6.3.1.1.5.2': 'info',        # warmStart
    '1.3.6.1.6.3.1.1.5.3': 'critical',    # linkDown
    '1.3.6.1.6.3.1.1.5.4': 'info',        # linkUp
    '1.3.6.1.6.3.1.1.5.5': 'warning',     # authenticationFailure
}


class SnmpTrapReceiver:
    """Receives SNMP traps on UDP port 162"""
    
    def __init__(self, db, port=162):
        self.db = db
        self.port = port
        self._thread = None
        self._running = False
        self._dispatcher = None
    
    def start(self):
        """Start listening for SNMP traps in a background thread"""
        if not TRAP_AVAILABLE:
            print("[TrapReceiver] Cannot start — pysnmp trap modules not available")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[TrapReceiver] Started listening on UDP port {self.port}")
    
    def stop(self):
        """Stop the trap receiver"""
        self._running = False
        if self._dispatcher:
            try:
                self._dispatcher.closeDispatcher()
            except:
                pass
        print("[TrapReceiver] Stopped")
    
    def _run(self):
        """Main trap receiver loop"""
        import asyncio
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            self._dispatcher = AsyncioDispatcher()
            
            # Register callback
            self._dispatcher.registerRecvCbFun(self._trap_callback)
            
            # Open UDP transport on port 162
            self._dispatcher.registerTransport(
                udp.DOMAIN_NAME,
                udp.UdpAsyncioTransport().openServerMode(('0.0.0.0', self.port))
            )
            
            # Run dispatcher
            self._dispatcher.runDispatcher()
            
        except PermissionError:
            print(f"[TrapReceiver] ERROR: Permission denied on port {self.port}. "
                  f"Run as administrator or use port > 1024.")
        except OSError as e:
            if 'address already in use' in str(e).lower() or '10048' in str(e):
                print(f"[TrapReceiver] ERROR: Port {self.port} already in use")
            else:
                print(f"[TrapReceiver] ERROR: {e}")
        except Exception as e:
            print(f"[TrapReceiver] ERROR: {e}")
    
    def _trap_callback(self, dispatcher, transportDomain, transportAddress, wholeMsg):
        """Process incoming SNMP trap"""
        source_ip = transportAddress[0]
        
        try:
            # Try SNMPv2c first
            while wholeMsg:
                msg_ver = int(api.decodeMessageVersion(wholeMsg))
                
                if msg_ver in (api.SNMP_VERSION_1, api.SNMP_VERSION_2C):
                    p_mod = api.PROTOCOL_MODULES[msg_ver]
                else:
                    print(f"[TrapReceiver] Unsupported SNMP version: {msg_ver}")
                    return
                
                req_msg, wholeMsg = decoder.decode(
                    wholeMsg, asn1Spec=p_mod.Message()
                )
                
                req_pdu = p_mod.apiMessage.getPDU(req_msg)
                community = str(p_mod.apiMessage.getCommunity(req_msg))
                
                # Extract trap info
                trap_oid = ''
                varbinds_list = []
                
                if msg_ver == api.SNMP_VERSION_1:
                    # SNMPv1 Trap
                    enterprise = str(p_mod.apiTrapPDU.getEnterprise(req_pdu).prettyPrint())
                    generic = p_mod.apiTrapPDU.getGenericTrap(req_pdu)
                    specific = p_mod.apiTrapPDU.getSpecificTrap(req_pdu)
                    trap_oid = f"{enterprise}.0.{int(generic)}"
                    
                    var_binds = p_mod.apiTrapPDU.getVarBinds(req_pdu)
                    for oid, val in var_binds:
                        varbinds_list.append({
                            'oid': str(oid.prettyPrint()),
                            'value': str(val.prettyPrint())
                        })
                else:
                    # SNMPv2c Trap
                    var_binds = p_mod.apiPDU.getVarBinds(req_pdu)
                    for oid, val in var_binds:
                        oid_str = str(oid.prettyPrint())
                        val_str = str(val.prettyPrint())
                        
                        # snmpTrapOID.0
                        if '1.3.6.1.6.3.1.1.4.1.0' in oid_str:
                            trap_oid = val_str
                        else:
                            varbinds_list.append({
                                'oid': oid_str,
                                'value': val_str
                            })
                
                # Resolve trap name and severity
                trap_name = TRAP_NAMES.get(trap_oid, trap_oid)
                severity = TRAP_SEVERITY.get(trap_oid, 'info')
                
                # Try to match source IP to a known device
                device_id = None
                device_name = None
                try:
                    devices = self.db.get_all_devices()
                    for d in devices:
                        if d.get('ip_address') == source_ip:
                            device_id = d['id']
                            device_name = d['name']
                            break
                except:
                    pass
                
                # Store in database
                varbinds_json = json.dumps(varbinds_list, ensure_ascii=False)
                self.db.add_trap(
                    source_ip=source_ip,
                    trap_oid=trap_oid,
                    trap_name=trap_name,
                    severity=severity,
                    varbinds=varbinds_json,
                    device_id=device_id,
                    device_name=device_name
                )
                
                print(f"[TrapReceiver] Trap from {source_ip}: {trap_name} ({severity})")
                
        except Exception as e:
            print(f"[TrapReceiver] Error processing trap from {source_ip}: {e}")
        
        return wholeMsg
