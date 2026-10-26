
import csv, json, os, time
try:
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
    from os_ken.ofproto import ofproto_v1_3
    from os_ken.lib.packet import packet, ethernet, ipv4, arp, ether_types
    from os_ken.lib import hub
except ImportError:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ipv4, arp, ether_types
    from ryu.lib import hub

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY = os.path.join(HERE, "policy.json")
OUTCSV = os.path.join(HERE, "bandwidth.csv")
POLL = 2.0
EVENT_FILE = "/tmp/sdnfs_events.jsonl"      # written by server.py (application -> SDN channel)
DYNLOG = os.path.join(HERE, "dynamic_events.csv")


class FileShareSDN(getattr(app_manager, "OSKenApp", None) or app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.mac_to_port = {}
        self.dps = {}
        self.prev = {}
        self.policy = {"blocked_ips": [], "rate_limit_kbps": {}, "server_ip": None, "server_port": 5000,
                       "auto_block_seconds": 60}
        self.dyn_blocked = {}
        self._evpos = 0
        self._pmtime = 0
        self._load_policy()
        with open(OUTCSV, "w", newline="") as f:
            csv.writer(f).writerow(["time", "dpid", "src", "dst", "bytes", "mbps"])
        with open(DYNLOG, "w", newline="") as f:
            csv.writer(f).writerow(["time", "event", "ip", "detail"])
        open(EVENT_FILE, "w").close()
        hub.spawn(self._monitor)
        hub.spawn(self._app_events)

    def _load_policy(self):
        try:
            m = os.path.getmtime(POLICY)
        except OSError:
            return False
        if m == self._pmtime:
            return False
        try:
            with open(POLICY) as f:
                self.policy.update(json.load(f))
        except ValueError:
            return False
        self._pmtime = m
        self.logger.info("policy loaded: %s", self.policy)
        return True

    @staticmethod
    def _mid(ip):
        return int(ip.split(".")[-1])

    def _apply_policy(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        dp.send_msg(p.OFPFlowMod(dp, table_id=ofp.OFPTT_ALL, command=ofp.OFPFC_DELETE,
                                 out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))
        dp.send_msg(p.OFPMeterMod(dp, command=ofp.OFPMC_DELETE, flags=0, meter_id=ofp.OFPM_ALL))
        for ip, kbps in self.policy["rate_limit_kbps"].items():
            band = p.OFPMeterBandDrop(rate=int(kbps), burst_size=int(kbps) // 10 or 1)
            dp.send_msg(p.OFPMeterMod(dp, command=ofp.OFPMC_ADD, flags=ofp.OFPMF_KBPS,
                                      meter_id=self._mid(ip), bands=[band]))
        self._table_miss(dp)
        # static drop rules for blocked clients (priority above learned flows)
        for ip in sorted(set(self.policy["blocked_ips"]) | set(self.dyn_blocked)):
            for field in ("ipv4_src", "ipv4_dst"):
                match = p.OFPMatch(eth_type=0x0800, **{field: ip})
                self._add_flow(dp, 200, match, [])          # no actions = drop
        self.mac_to_port.pop(dp.id, None)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _features(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp
        self.logger.info("SWITCH CONNECTED dpid=%s -> installing base rules", dp.id)
        self._apply_policy(dp)
        self.logger.info("base rules sent for dpid=%s", dp.id)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state(self, ev):
        if ev.state == MAIN_DISPATCHER:
            self.dps[ev.datapath.id] = ev.datapath
        elif ev.datapath.id in self.dps:
            self.logger.info("SWITCH DISCONNECTED dpid=%s", ev.datapath.id)
            del self.dps[ev.datapath.id]

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def _ofp_error(self, ev):
        self.logger.error("OPENFLOW ERROR from switch: type=%s code=%s", ev.msg.type, ev.msg.code)

    def _table_miss(self, dp):
        ofp, p = dp.ofproto, dp.ofproto_parser
        self._add_flow(dp, 0, p.OFPMatch(), [p.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)])

    def _add_flow(self, dp, prio, match, actions, idle=0, meter=None):
        ofp, p = dp.ofproto, dp.ofproto_parser
        inst = []
        if meter:
            inst.append(p.OFPInstructionMeter(meter))
        inst.append(p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions))
        dp.send_msg(p.OFPFlowMod(dp, priority=prio, match=match, instructions=inst, idle_timeout=idle))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        dp, ofp, p = msg.datapath, msg.datapath.ofproto, msg.datapath.ofproto_parser
        in_port = msg.match["in_port"]
        self.logger.info("PACKET_IN dpid=%s in_port=%s", dp.id, in_port)
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        table = self.mac_to_port.setdefault(dp.id, {})
        table[eth.src] = in_port
        out_port = table.get(eth.dst, ofp.OFPP_FLOOD)
        actions = [p.OFPActionOutput(out_port)]

        ip = pkt.get_protocol(ipv4.ipv4)
        if ip and out_port != ofp.OFPP_FLOOD:
            # per-(src,dst) IP flow so stats give per-pair bandwidth; meter if either end is rate limited
            meter = None
            for host in (ip.src, ip.dst):
                if host in self.policy["rate_limit_kbps"]:
                    meter = self._mid(host)
            match = p.OFPMatch(in_port=in_port, eth_type=0x0800, ipv4_src=ip.src, ipv4_dst=ip.dst)
            self._add_flow(dp, 10, match, actions, idle=30, meter=meter)
        elif out_port != ofp.OFPP_FLOOD:
            self._add_flow(dp, 5, p.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src), actions, idle=30)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(p.OFPPacketOut(dp, msg.buffer_id, in_port, actions, data))

    def _monitor(self):
        while True:
            hub.sleep(POLL)
            if self._load_policy():
                for dp in list(self.dps.values()):
                    self._apply_policy(dp)
            for dp in list(self.dps.values()):
                dp.send_msg(dp.ofproto_parser.OFPFlowStatsRequest(dp))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _stats(self, ev):
        now = time.time()
        dpid = ev.msg.datapath.id
        with open(OUTCSV, "a", newline="") as f:
            w = csv.writer(f)
            for s in ev.msg.body:
                m = s.match
                if "ipv4_src" not in m or "ipv4_dst" not in m:
                    continue
                key = (dpid, m["ipv4_src"], m["ipv4_dst"])
                pb, pt = self.prev.get(key, (0, now - POLL))
                mbps = max(0, (s.byte_count - pb) * 8 / max(now - pt, 1e-6) / 1e6)
                self.prev[key] = (s.byte_count, now)
                w.writerow([f"{now:.2f}", dpid, key[1], key[2], s.byte_count, f"{mbps:.3f}"])
                if mbps > 0.01:
                    self.logger.info("s%s %s -> %s  %.2f Mbit/s", dpid, key[1], key[2], mbps)

    def _log_dyn(self, event, ip, detail=""):
        with open(DYNLOG, "a", newline="") as f:
            csv.writer(f).writerow([f"{time.time():.2f}", event, ip, detail])

    def _reapply_all(self):
        for dp in list(self.dps.values()):
            self._apply_policy(dp)

    def _drop_matches(self, p, ip):
        return [p.OFPMatch(eth_type=0x0800, **{f: ip}) for f in ("ipv4_src", "ipv4_dst")]

    def _block_ip(self, ip):
        for dp in list(self.dps.values()):
            for m in self._drop_matches(dp.ofproto_parser, ip):
                self._add_flow(dp, 200, m, [])

    def _unblock_ip(self, ip):
        for dp in list(self.dps.values()):
            ofp, p = dp.ofproto, dp.ofproto_parser
            for m in self._drop_matches(p, ip):
                dp.send_msg(p.OFPFlowMod(dp, table_id=0, command=ofp.OFPFC_DELETE_STRICT, priority=200,
                                         out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY, match=m))

    def _handle_event(self, ev):
        if ev.get("type") == "auth_fail_threshold":
            ip = ev["ip"]
            secs = float(self.policy.get("auto_block_seconds", 60))
            self.dyn_blocked[ip] = time.time() + secs
            self.logger.warning("APP EVENT: repeated failed logins from %s -> BLOCKING for %.0fs", ip, secs)
            self._log_dyn("block", ip, f"{secs:.0f}s after repeated failed logins")
            self._block_ip(ip)

    def _app_events(self):
        while True:
            hub.sleep(0.5)
            try:
                with open(EVENT_FILE) as f:
                    f.seek(self._evpos)
                    data = f.read()
                    self._evpos = f.tell()
                for line in data.splitlines():
                    try:
                        self._handle_event(json.loads(line))
                    except ValueError:
                        pass
            except OSError:
                pass
            now = time.time()
            expired = [ip for ip, exp in self.dyn_blocked.items() if exp <= now]
            for ip in expired:
                del self.dyn_blocked[ip]
                self.logger.info("block on %s expired -> restoring access", ip)
                self._log_dyn("unblock", ip, "block expired")
            for ip in expired:
                self._unblock_ip(ip)

