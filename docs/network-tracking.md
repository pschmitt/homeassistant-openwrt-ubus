# Network tracking

The integration discovers AP interfaces, wireless stations and DHCP clients
using the wireless and lease backends chosen in the options flow. A station
can expose presence, hostname and address, signal, connection time, link
quality and data rates when the router provides those values. AP devices
show connected clients and radio status; system sensors show uptime, memory
and load. Optional QModem devices expose modem status and optional MWAN3
devices expose interface and policy state.

Two tracking modes serve different layouts:

| Mode | Entities | Roaming |
|------|----------|---------|
| `combined` | Separate device trackers for each station on each AP | A move to a different AP changes the per-AP tracker |
| `uniqueid` | One tracker per station across APs | The tracker follows the station and reports current AP attributes |

`combined` is useful for knowing which AP currently sees a station.
`uniqueid` reduces duplicate trackers on a roaming network; its current
router, AP device and SSID are available as attributes. Switching modes
changes entity identity and can affect automations; review entity IDs and
automation references after changing the option. Avoid deleting registry
entries by hand or running an unreviewed cleanup script against a live
installation.

Device-kick buttons are optional and disabled by default. See
[Router actions](router-actions.md) for the needed hostapd permissions.
