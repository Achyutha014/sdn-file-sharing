import argparse
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

SERVER_IP = "10.0.0.100"


def build(n_clients=4, server_bw=100, client_bw=100, controller_ip="127.0.0.1"):
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip=controller_ip, port=6653)
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    srv = net.addHost("srv", ip=SERVER_IP + "/24")
    net.addLink(srv, s1, bw=server_bw)
    for i in range(1, n_clients + 1):
        h = net.addHost(f"h{i}", ip=f"10.0.0.{i}/24")
        net.addLink(h, s1, bw=client_bw)
    net.start()
    return net


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("-n", type=int, default=4)
    a = ap.parse_args()
    setLogLevel("info")
    net = build(a.n)
    CLI(net)
    net.stop()
