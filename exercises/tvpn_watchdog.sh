#!/usr/bin/env bash
# MODULE 3 EXERCISE - Tactical Link Watchdog & PACE Failover
# Lesson: lessons/03-tvpn-failover.md
#
# Goal: keep the drone's C2 link alive. Ping the TVPN peer through the
# PRIMARY radio link (LOS). If it stops answering, move the route to the
# CONTINGENCY link (BLOS SATCOM). When LOS comes back, move it back.
# Our persistent TVPN address (100.64.2.102) never changes.
#
# Fill in every block marked TODO (there are 4).
#   Try it:       python3 course.py run 3
#   Grade it:     python3 course.py check 3
#   Stuck?        python3 course.py hint 3

TARGET_NODE="${TARGET_NODE:-100.64.2.1}"       # the TVPN peer we must stay connected to
TVPN_SRC="${TVPN_SRC:-100.64.2.102}"            # our persistent TVPN address
PRIMARY_DEV="${PRIMARY_DEV:-los0}";         PRIMARY_GW="${PRIMARY_GW:-10.10.1.2}"
CONTINGENCY_DEV="${CONTINGENCY_DEV:-sat0}"; CONTINGENCY_GW="${CONTINGENCY_GW:-10.20.1.2}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"           # failed probes in a row before failing over
RECOVER_THRESHOLD="${RECOVER_THRESHOLD:-3}"     # healthy LOS checks in a row before failing back
INTERVAL="${INTERVAL:-1}"                       # seconds between checks
STATE_FILE="${STATE_FILE:-/tmp/tvpn_watchdog.state}"

[[ $EUID -eq 0 ]] || { echo "[!] Changing routes needs root. Run: sudo bash $0"; exit 1; }

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Is the PRIMARY radio link itself up? Pings the radio at the other end of los0. (Provided -
# use it as an example for TODO 1.) A command "succeeds" when its exit status is 0.
los_ok() {
    ping -c 1 -W 1 -I "$PRIMARY_DEV" "$PRIMARY_GW" >/dev/null 2>&1
}

# Can we reach the TVPN peer right now, over whichever path is active?
probe() {
    # TODO 1: Send ONE ping, waiting at most 1 second, FROM our TVPN address
    #   ($TVPN_SRC) TO the peer ($TARGET_NODE). Hide its output.
    #   Look at los_ok() above: it's almost the same command.
    #   The function's result is the exit status of the last command it runs.
    #   Replace the line below.
    return 0
}

# Switch the route to the peer onto a path: set_path PRIMARY  or  set_path CONTINGENCY
set_path() {
    local dev gw
    if [[ $1 == PRIMARY ]]; then
        dev=$PRIMARY_DEV;     gw=$PRIMARY_GW
    else
        dev=$CONTINGENCY_DEV; gw=$CONTINGENCY_GW
    fi
    ip neigh flush dev "$dev" 2>/dev/null   # forget stale neighbor (ARP) entries on that link

    # TODO 2: Point the route for "$TARGET_NODE/32" at gateway $gw on interface $dev,
    #   using our persistent address $TVPN_SRC as the source. The command is:
    #       ip route replace <destination> via <gateway> dev <interface> src <source-ip>
    #   Write it on the line below (remember to "quote" your variables).


    ACTIVE=$1
    echo "ACTIVE=$ACTIVE DEV=$dev" > "$STATE_FILE"   # lets the grader see what you decided
}

trap 'log "Watchdog stopped (active path: ${ACTIVE:-unknown})."; exit 0' INT TERM

ACTIVE=""
set_path PRIMARY
fails=0
recov=0
log "[*] Monitoring route to $TARGET_NODE from $TVPN_SRC (primary: $PRIMARY_DEV)"

while true; do
    if [[ $ACTIVE == PRIMARY ]]; then
        # ---- On the PRIMARY link: watch for failures --------------------------
        if probe; then
            fails=0
        else
            fails=$((fails + 1))
            log "[WARN] Probe to $TARGET_NODE failed ($fails/$FAIL_THRESHOLD)"

            # TODO 3: If fails has reached FAIL_THRESHOLD, fail over:
            #     - log an [ALERT] message
            #     - call: set_path CONTINGENCY
            #     - reset fails back to 0
            #   Bash numeric comparison:   if (( a >= b )); then ... fi


        fi
    else
        # ---- On the CONTINGENCY link: wait for LOS to recover -----------------
        probe || log "[WARN] Contingency path degraded: $TARGET_NODE unreachable via $CONTINGENCY_DEV"
        if los_ok; then
            recov=$((recov + 1))
        else
            recov=0
        fi

        # TODO 4: If recov has reached RECOVER_THRESHOLD, fail back:
        #     - log a [RECOVER] message
        #     - call: set_path PRIMARY
        #     - reset recov back to 0


    fi
    sleep "$INTERVAL"
done
