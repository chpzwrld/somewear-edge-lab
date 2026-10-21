#!/usr/bin/env bash
# Module 3 lab network: builds a simulated two-path tactical link to a TVPN peer.
#
#   Edge device (this container)                 TVPN peer (netns "tvpn-peer")
#   tvpn0  100.64.2.102/32  (persistent TVPN IP)  lo  100.64.2.1/32  (peer VIP)
#   los0   10.10.1.1/30  <==== PRIMARY: LOS radio ====>  los0-peer 10.10.1.2/30
#   sat0   10.20.1.1/30  <== CONTINGENCY: BLOS SATCOM ==> sat0-peer 10.20.1.2/30
#
# Usage: sudo bash lab/tvpn_lab_net.sh {up|down|jam|unjam|status}
#   jam    - simulate EW jamming of the LOS link (peer-side radio goes dark)
#   unjam  - restore the LOS link
set -euo pipefail

NS="tvpn-peer"
TVPN_IP="100.64.2.102"
PEER_VIP="100.64.2.1"
LOS_LOCAL="10.10.1.1";  LOS_PEER="10.10.1.2"
SAT_LOCAL="10.20.1.1";  SAT_PEER="10.20.1.2"

[[ $EUID -eq 0 ]] || { echo "[!] Run with sudo: sudo bash $0 ${1:-}"; exit 1; }
command -v ip >/dev/null || { echo "[!] 'ip' not found - install iproute2"; exit 1; }

nsx() { ip netns exec "$NS" "$@"; }

peer_routes() {
    # Peer prefers LOS back to us, falls back to SATCOM.
    nsx ip route replace "$TVPN_IP/32" via "$LOS_LOCAL" dev los0-peer metric 10 2>/dev/null || true
    nsx ip route replace "$TVPN_IP/32" via "$SAT_LOCAL" dev sat0-peer metric 100
}

up() {
    down >/dev/null 2>&1 || true
    ip netns add "$NS"
    nsx ip link set lo up
    nsx ip addr add "$PEER_VIP/32" dev lo

    ip link add los0 type veth peer name los0-peer
    ip link add sat0 type veth peer name sat0-peer
    ip link set los0-peer netns "$NS"
    ip link set sat0-peer netns "$NS"

    ip addr add "$LOS_LOCAL/30" dev los0 && ip link set los0 up
    ip addr add "$SAT_LOCAL/30" dev sat0 && ip link set sat0 up
    nsx ip addr add "$LOS_PEER/30" dev los0-peer && nsx ip link set los0-peer up
    nsx ip addr add "$SAT_PEER/30" dev sat0-peer && nsx ip link set sat0-peer up

    # Persistent TVPN address lives on a dummy interface, independent of transport.
    # (Falls back to a veth stub on kernels built without the dummy driver.)
    ip link add tvpn0 type dummy 2>/dev/null \
        || { ip link add tvpn0 type veth peer name tvpn0-stub && ip link set tvpn0-stub up; }
    ip addr add "$TVPN_IP/32" dev tvpn0
    ip link set tvpn0 up

    # Loose reverse-path filtering so replies may return on either transport.
    for i in all los0 sat0 tvpn0; do sysctl -qw "net.ipv4.conf.$i.rp_filter=2" 2>/dev/null || true; done
    nsx sysctl -qw net.ipv4.conf.all.rp_filter=0 2>/dev/null || true

    # SATCOM is high latency (best-effort: needs the sch_netem kernel module).
    tc qdisc add dev sat0 root netem delay 300ms 2>/dev/null \
        && echo "[*] SATCOM link: +300ms latency (netem)" \
        || echo "[*] SATCOM link: netem unavailable, no latency emulation"

    # Primary path: LOS.
    ip route replace "$PEER_VIP/32" via "$LOS_PEER" dev los0 src "$TVPN_IP"
    peer_routes
    echo "[+] Lab network up. TVPN IP $TVPN_IP -> peer VIP $PEER_VIP via LOS (los0)."
}

down() {
    ip netns del "$NS" 2>/dev/null || true      # also destroys the veth peers
    ip link del los0 2>/dev/null || true
    ip link del sat0 2>/dev/null || true
    ip link del tvpn0 2>/dev/null || true
    ip route del "$PEER_VIP/32" 2>/dev/null || true
    echo "[+] Lab network removed."
}

jam() {
    nsx ip link set los0-peer down
    echo "[JAM] LOS link jammed (peer radio dark). los0 has lost carrier."
}

unjam() {
    nsx ip link set los0-peer up
    peer_routes      # kernel flushed the peer's LOS route when the link went down
    echo "[UNJAM] LOS link restored."
}

status() {
    if ! ip netns list | grep -qw "$NS"; then echo "Lab network is DOWN."; return; fi
    echo "== Route to peer VIP =="; ip route get "$PEER_VIP" from "$TVPN_IP" 2>&1 | head -1
    echo "== Links =="; ip -br link show los0; ip -br link show sat0; ip -br addr show tvpn0
}

case "${1:-}" in
    up|down|jam|unjam|status) "$1" ;;
    *) echo "Usage: sudo bash $0 {up|down|jam|unjam|status}"; exit 1 ;;
esac
