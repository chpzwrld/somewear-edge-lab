# Lesson 3 - Tactical Link Watchdog & PACE Failover

## The mission

In contested airspace, the line-of-sight (**LOS**) radio link can be jammed at any moment.
Your edge device has a backup path - a beyond-line-of-sight (**BLOS**) satellite link - and a
TVPN that gives it a **persistent IP address** (`100.64.2.102`) no matter which path carries
the traffic. What's missing is the automation: something has to *notice* the LOS link died
and *move the traffic* to SATCOM, then move it back when LOS recovers. That's your watchdog.

---

## Concept 1: Interfaces, addresses and routes

- An **interface** is a network connection on a machine: a cable, a radio, a Wi-Fi card.
  Linux names them, e.g. `eth0`, `wlan0` - in our lab, `los0` (radio) and `sat0` (SATCOM).
- Each interface has an **IP address**. Our persistent TVPN address `100.64.2.102` lives on
  its own interface (`tvpn0`) so it never depends on one physical link.
- The **routing table** is the machine's signpost list: *"to reach address X, send it out
  interface Y, via next-hop gateway Z."*

```
destination      via (gateway)   dev (interface)   src (our address)
100.64.2.1/32    10.10.1.2       los0              100.64.2.102      <- today: radio
100.64.2.1/32    10.20.1.2       sat0              100.64.2.102      <- after failover: SATCOM
```

`/32` means "exactly this one address". Changing which line is in effect is a single command:

```bash
ip route replace <destination> via <gateway> dev <interface> src <source-ip>
```

`replace` means "add it, or overwrite the existing route to that destination". Because the
`src` stays `100.64.2.102` on both paths, the peer sees the *same* address before and after
- mission command-and-control (C2) sessions survive the switch.

## Concept 2: Ping - is anyone there?

`ping` sends a tiny "are you there?" packet (ICMP echo) and waits for a reply.

```bash
ping -c 1 -W 1 -I 100.64.2.102 100.64.2.1
#     │    │    │                └ who to ping
#     │    │    └ send FROM this address (or out this interface)
#     │    └ wait at most 1 second for the reply
#     └ send just 1 ping
```

Every Linux command finishes with an **exit status**: `0` means success, anything else means
failure. `ping` returns 0 only if a reply came back. Bash's `if` checks exit status
directly - this is the heart of the watchdog:

```bash
if ping -c 1 -W 1 10.0.0.1 >/dev/null 2>&1; then
    echo "reachable"
else
    echo "no answer"
fi
```

`>/dev/null 2>&1` throws away the command's printed output - we only care about success or
failure.

## Concept 3: PACE planning

Military communications plans name four layers, in order of preference:

| | Layer | Our lab |
|---|---|---|
| **P** | Primary | LOS radio (`los0`) - fast, low latency, jammable |
| **A** | Alternate | (another radio net) |
| **C** | Contingency | BLOS SATCOM (`sat0`) - works beyond line of sight, slower, costlier |
| **E** | Emergency | (e.g. text-only satellite messaging) |

The watchdog automates moving between them.

## Concept 4: Watchdog design - don't flap

A naive watchdog switches on the first failed ping. But one ping can be lost even on a good
link, and constant switching back and forth (**flapping**) is worse than either link alone.
So we use **thresholds**:

- Fail over only after **2 failures in a row** (`FAIL_THRESHOLD`).
- Fail back only after the primary has been healthy for **3 checks in a row**
  (`RECOVER_THRESHOLD`) - make sure the jamming has really stopped.

Different thresholds for going and returning is called **hysteresis**. The loop is a small
**state machine**:

```
         probe fails FAIL_THRESHOLD times
 PRIMARY ─────────────────────────────────> CONTINGENCY
   ^                                           │
   └───────────────────────────────────────────┘
      LOS healthy RECOVER_THRESHOLD times in a row
```

## Concept 5: Bash in five minutes

```bash
NAME="los0"                       # variable (no spaces around =)
echo "link is $NAME"              # use it with $ - and keep it in "double quotes"
count=$((count + 1))              # arithmetic
if (( count >= 3 )); then         # numeric comparison
    echo "three or more"
fi
my_func() {                       # a function...
    ping -c 1 -W 1 "$1" >/dev/null 2>&1
}                                 # ...whose result is the exit status of its last command
if my_func 10.0.0.1; then echo "up"; fi
```

---

## The lab network

Real radios aren't needed: `lab/tvpn_lab_net.sh` builds a tiny virtual network inside your
container, with a simulated TVPN peer at the far end of two links.

```
 YOUR EDGE DEVICE                                     TVPN PEER (simulated)
 tvpn0  100.64.2.102  (persistent TVPN IP)            100.64.2.1  (the address we must reach)
 los0   10.10.1.1  <====== PRIMARY: LOS radio ======>  10.10.1.2
 sat0   10.20.1.1  <=== CONTINGENCY: BLOS SATCOM ====>  10.20.1.2
```

"Jamming" switches off the radio at the peer's end, exactly as if its signal were drowned
out.

## Explore (10 minutes)

```bash
sudo bash lab/tvpn_lab_net.sh up                     # build the network
ip route get 100.64.2.1 from 100.64.2.102            # which path will traffic take? (los0)
ping -c 3 -I 100.64.2.102 100.64.2.1                 # it answers
sudo bash lab/tvpn_lab_net.sh jam                    # jam the radio
ping -c 3 -W 1 -I 100.64.2.102 100.64.2.1            # no answers: the route still points at a dead link
sudo ip route replace 100.64.2.1/32 via 10.20.1.2 dev sat0 src 100.64.2.102   # fail over BY HAND
ping -c 3 -I 100.64.2.102 100.64.2.1                 # answers again - same source address, via SATCOM
sudo bash lab/tvpn_lab_net.sh status                 # see links and the active route
sudo bash lab/tvpn_lab_net.sh down                   # clean up
```

You just did a failover by hand. Now you'll teach a script to do it automatically, in about
a second, at 3 a.m., while being jammed.

Want to see the goal first? `python3 course.py demo 3` - press `j` to jam, watch the
watchdog react, `u` to restore, `q` to quit.

---

## Your task

Open **`exercises/tvpn_watchdog.sh`**. Four `TODO`s:

**TODO 1 - `probe()`**: one ping from `$TVPN_SRC` to `$TARGET_NODE`, output hidden. The
provided `los_ok()` function is a nearly identical example.

**TODO 2 - `set_path()`**: the `ip route replace` command that points the route to
`$TARGET_NODE/32` at `$gw` on `$dev` with source `$TVPN_SRC`.

**TODO 3 - failover**: when `fails` reaches `FAIL_THRESHOLD`: log an alert, `set_path
CONTINGENCY`, reset `fails` to 0.

**TODO 4 - failback**: when `recov` reaches `RECOVER_THRESHOLD`: log it, `set_path PRIMARY`,
reset `recov` to 0.

### Try it

```bash
python3 course.py run 3
```

This builds the lab network, starts *your* watchdog and gives you a menu: `j` jams LOS, `u`
restores it, `s` shows the active route, `p` pings the peer. Watch your log lines react.

### Check it

```bash
python3 course.py check 3
```

The grader checks four things in order: the watchdog stays put while the link is healthy,
fails over when jammed, actually moves the traffic (same TVPN address), and fails back after
recovery.

---

## Knowledge check

1. Why does the watchdog wait for 2 failed probes instead of switching on the first one?
2. After failover, why does the peer still see traffic from `100.64.2.102`?
3. While on SATCOM, why does the watchdog test `los_ok()` instead of `probe()` to decide when
   to fail back?
4. `ping` printed nothing (output hidden). How does the `if` know whether it worked?
5. What does `/32` mean in `100.64.2.1/32`?

<details><summary>Answers</summary>

1. A single lost ping happens on healthy links too. Waiting for consecutive failures avoids
   needless switching (flapping).
2. The route's `src` is set to the persistent TVPN address on both paths - only the physical
   path changes, not the identity.
3. `probe()` goes over whatever path is *active* - SATCOM - so it would succeed even while
   LOS is still jammed. `los_ok()` tests the LOS radio link itself.
4. From its exit status: 0 means a reply came back, non-zero means it didn't.
5. A route for exactly one address (all 32 bits of the address must match).

</details>

## In the field

- Real transports are physical interfaces: a radio's Ethernet port, a SATCOM modem, an LTE
  dongle. The same `ip route` commands apply.
- Production systems add more layers (Alternate, Emergency), probe several targets, and
  often use routing daemons or policy routing - but the logic is the same state machine you
  just wrote.
- Thresholds are a trade-off: lower = faster failover but more flapping; higher = steadier
  but slower to react. Tune them to the link.

## Bonus challenges

1. Add an **Alternate** path: a third link the watchdog tries before SATCOM.
2. Log how long each outage lasted (`date +%s` gives seconds since 1970).
3. Run the watchdog with `INTERVAL=0.5 FAIL_THRESHOLD=1` - how does it behave? Why might
   that be risky on a real radio?

---

## Course complete

Run `python3 course.py` to see your progress. You've built the three core pieces of a
drone-to-ATAK edge integration:

1. a **serial-to-UDP bridge** that moves raw telemetry onto the network,
2. a **MAVLink-to-CoT gateway** that puts the drone on every ATAK map, with correct altitude,
3. a **link watchdog** that keeps C2 alive through jamming with PACE failover.
