try:
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.ofproto import ofproto_v1_3
    from os_ken.lib.packet import packet, ethernet
except ImportError:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet

Base = getattr(app_manager, "OSKenApp", None) or app_manager.RyuApp


class Diag(Base):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mac = {}
        print("DIAG: loaded", flush=True)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features(self, ev):
        dp = ev.msg.datapath
        o, p = dp.ofproto, dp.ofproto_parser
        print("DIAG: switch connected, id", dp.id, flush=True)
        acts = [p.OFPActionOutput(o.OFPP_CONTROLLER, o.OFPCML_NO_BUFFER)]
        inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, acts)]
        dp.send_msg(p.OFPFlowMod(dp, priority=0, match=p.OFPMatch(), instructions=inst))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        o, p = dp.ofproto, dp.ofproto_parser
        port = msg.match["in_port"]
        eth = packet.Packet(msg.data).get_protocol(ethernet.ethernet)
        if eth is None:
            return
        print("DIAG: packet in", eth.src, "->", eth.dst, flush=True)
        self.mac.setdefault(dp.id, {})[eth.src] = port
        out = self.mac[dp.id].get(eth.dst, o.OFPP_FLOOD)
        acts = [p.OFPActionOutput(out)]
        if out != o.OFPP_FLOOD:
            inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, acts)]
            m = p.OFPMatch(in_port=port, eth_dst=eth.dst, eth_src=eth.src)
            dp.send_msg(p.OFPFlowMod(dp, priority=1, match=m, instructions=inst, idle_timeout=30))
        data = msg.data if msg.buffer_id == o.OFP_NO_BUFFER else None
        dp.send_msg(p.OFPPacketOut(dp, msg.buffer_id, port, acts, data))
