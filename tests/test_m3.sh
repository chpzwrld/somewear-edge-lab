#!/usr/bin/env bash
# Grader for Module 3 (TVPN watchdog & PACE failover).
# Usage: bash tests/test_m3.sh [path/to/tvpn_watchdog.sh]
# (defaults to exercises/tvpn_watchdog.sh - normally run via: python3 course.py check 3)
set -uo pipefail
cd "$(dirname "$0")/.."

WATCHDOG="${1:-exercises/tvpn_watchdog.sh}"
SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"
NET="lab/tvpn_lab_net.sh"
STATE_FILE="/tmp/tvpn_watchdog.state"
LOG="/tmp/edge-course/watchdog.log"
VIP="100.64.2.1"; TVPN_IP="100.64.2.102"
WD_PID=""
TOTAL=5

if [[ -t 1 && -z ${NO_COLOR:-} ]]; then B=$'\e[1m' G=$'\e[32m' R=$'\e[31m' Y=$'\e[33m' C=$'\e[1;36m' N=$'\e[0m'
else B="" G="" R="" Y="" C="" N=""; fi

step() { echo; echo "${B}[$1/$TOTAL] $2${N}"; }
pass() { echo "${G}  PASS${N} $*"; }
fail() {  # fail <message> [hint]
    echo "${R}  FAIL${N} $1"
    [[ -n ${2:-} ]] && echo "${Y}  HINT${N} $2"
    if [[ -s $LOG ]]; then echo "       Your watchdog's output:"; sed 's/^/         | /' "$LOG" | tail -15; fi
    echo; echo "${R}Not quite yet - fix the item above and run the check again.${N}"
    exit 1
}

cleanup() {
    [[ -n $WD_PID ]] && $SUDO kill "$WD_PID" 2>/dev/null
    $SUDO pkill -f '^bash [^ ]*tvpn_watchdog\.sh$' 2>/dev/null   # only real watchdog processes
    $SUDO bash "$NET" down >/dev/null 2>&1
    $SUDO rm -f "$STATE_FILE"
}
trap cleanup EXIT

# wait_for <seconds> <command...>  - retries the command every 0.5 s
wait_for() {
    local t=$1; shift
    for ((i = 0; i < t * 2; i++)); do "$@" && return 0; sleep 0.5; done
    return 1
}
active_is()     { grep -q "ACTIVE=$1" "$STATE_FILE" 2>/dev/null; }
route_dev()     { ip route get "$VIP" from "$TVPN_IP" 2>/dev/null | grep -q "dev $1"; }
vip_reachable() { $SUDO ping -c 1 -W 2 -I "$TVPN_IP" "$VIP" >/dev/null 2>&1; }

echo "${C}=== Module 3: Tactical Link Watchdog & PACE Failover ===${N}"
mkdir -p "$(dirname "$LOG")"; : > "$LOG"

step 1 "Checking your script and the lab environment"
[[ -f $WATCHDOG ]] || fail "Can't find $WATCHDOG."
syntax=$(bash -n "$WATCHDOG" 2>&1) || fail "Bash can't read your script: $syntax" \
    "Check the line number above for a missing 'fi', 'then', quote or bracket."
command -v ping >/dev/null || fail "'ping' is not installed." "Run: bash .devcontainer/setup.sh"
[[ -z $SUDO ]] || sudo -n true 2>/dev/null || fail "This module needs sudo (root) to change routes."
$SUDO bash "$NET" up >/dev/null 2>&1 || fail "Could not build the lab network." \
    "The container needs network-admin rights. In Docker use --privileged (launch.sh does this)."
pass "script syntax OK; lab network is up (LOS + SATCOM links, TVPN IP $TVPN_IP)"

step 2 "Steady state - LOS healthy, watchdog must stay on PRIMARY"
$SUDO bash "$WATCHDOG" >"$LOG" 2>&1 &
WD_PID=$!
wait_for 5 active_is PRIMARY || fail "The watchdog never reported ACTIVE=PRIMARY." \
    "Did you change the provided lines at the end of set_path()? They write the state file."
wait_for 5 vip_reachable || fail "The peer $VIP isn't reachable over LOS at startup." \
    "TODO 2: check your 'ip route replace' line in set_path()."
sleep 4
active_is PRIMARY || fail "The watchdog failed over even though the LOS link is healthy." \
    "TODO 1: probe() must ping FROM \$TVPN_SRC (-I) TO \$TARGET_NODE and succeed when it answers."
route_dev los0 || fail "The route to $VIP is not on los0." "TODO 2: set_path PRIMARY should use los0."
pass "stays on PRIMARY (los0) while the link is healthy"

step 3 "Jamming the LOS link - watchdog must fail over to CONTINGENCY"
$SUDO bash "$NET" jam >/dev/null
if ! wait_for 10 active_is CONTINGENCY; then
    if grep -q "WARN" "$LOG"; then
        fail "Your probe noticed the failures, but the watchdog never switched to CONTINGENCY." \
             "TODO 3: when (( fails >= FAIL_THRESHOLD )), call set_path CONTINGENCY."
    else
        fail "The watchdog didn't notice the LOS link went down." \
             "TODO 1: probe() is probably still 'return 0' (always healthy). Replace it with a real ping."
    fi
fi
pass "switched to CONTINGENCY"

step 4 "Traffic must now flow over SATCOM with the same TVPN address"
route_dev sat0 || fail "The watchdog says CONTINGENCY, but the route to $VIP did not move to sat0." \
    "TODO 2: set_path must run: ip route replace \"\$TARGET_NODE/32\" via \"\$gw\" dev \"\$dev\" src \"\$TVPN_SRC\""
wait_for 5 vip_reachable || fail "The route moved, but $VIP still isn't reachable over SATCOM." \
    "TODO 2: double-check the 'via' (gateway) and 'src' parts of your route command."
ip -br addr show tvpn0 | grep -q "$TVPN_IP" || fail "The persistent TVPN address disappeared."
pass "peer reachable via sat0; persistent IP $TVPN_IP preserved"

step 5 "Restoring LOS - watchdog must fail back to PRIMARY"
$SUDO bash "$NET" unjam >/dev/null
wait_for 15 active_is PRIMARY || fail "LOS came back, but the watchdog stayed on CONTINGENCY." \
    "TODO 4: when (( recov >= RECOVER_THRESHOLD )), call set_path PRIMARY."
route_dev los0 || fail "The watchdog says PRIMARY but the route is not back on los0." "TODO 2."
wait_for 5 vip_reachable || fail "Back on PRIMARY, but $VIP is unreachable."
pass "failed back to PRIMARY (los0)"

echo; echo "Your watchdog's log:"; sed 's/^/  | /' "$LOG"
echo; echo "${G}${B}[SUCCESS] Module 3: Tactical Link Watchdog & PACE Failover - all checks passed!${N}"
