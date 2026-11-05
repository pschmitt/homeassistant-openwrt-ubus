# Router setup

The OpenWrt device needs `rpcd` and `uhttpd` with ubus HTTP support, and Home
Assistant must be able to reach its ubus endpoint. Install the appropriate
OpenWrt packages for your release (`rpcd`, `uhttpd-mod-ubus`), enable both
services and configure a router account with the ubus permissions needed for
the features you select. Protect access with your network firewall and TLS
where available. Avoid granting unrestricted `ubus` read/write access to a
root account solely for this integration; use a least-privilege account and
OpenWrt's rpcd ACL mechanism.

Access depends on enabled features. System and wireless monitoring may need
`system.info`, `system.board`, `iwinfo` and `hostapd.*` reads; DHCP names can
require lease-file reads. Service controls require the appropriate `rc`
actions. Client disconnection requires `hostapd.*.del_client`. UCI actions
require `uci get`, `set` and `commit`. If NLBWMon top hosts are enabled, the
account additionally needs `file.exec` permission for `/usr/sbin/nlbw`;
leave this option off for an AP without `nlbwmon`. Permission sets differ
between router builds, so inspect denied ubus calls in the router log and
grant only those needed.

In Home Assistant, add **OpenWrt ubus** under **Settings → Devices & services**
and supply the router address, username and password. The options flow
selects wireless (`iwinfo`, `hostapd` or none), DHCP (`dnsmasq`, `odhcpd` or
none), device tracking mode, timeouts and optional sensors and controls.

If the connection fails, check that both router services are running, the
endpoint is reachable from Home Assistant and credentials have matching
ACL grants. If wireless stations are missing, check the selected wireless
backend and DHCP source. If station names show only hardware identifiers,
check the lease-file permissions. For slow sensors, adjust the relevant
system, modem or service timeout in the integration options and review the
Home Assistant logs. Do not put router passwords into shell commands or log
captures while diagnosing access.
