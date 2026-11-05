# Router actions

Home Assistant entities can manage supported procd services, including
start, stop, restart, enable and disable operations. `openwrt_ubus.scan_devices`
requests a device scan. Only enable control features when the configured
router account has the appropriate rpcd ACL grants.

`openwrt_ubus.uci_get` reads a UCI option and can write the result into a
specified sensor. `openwrt_ubus.uci_set_commit` writes an option and commits
it; its optional `service` argument restarts named services afterwards.
For example, inspect a firewall configuration value:

```yaml
action: openwrt_ubus.uci_get
data:
  config: firewall
  section: example_rule
  option: enabled
  target_entity_id: sensor.example_rule_enabled
```

To set a value, use `uci_set_commit` with `config`, `section`, `option` and
`value` and confirm the effect on the router. Changing network and firewall
settings can cut off access to the router; use a separate management path
and review the target before applying changes. The router account needs
`uci get`, `set` and `commit` permissions for these actions.

**Device Kick Buttons** are off by default. When enabled with a compatible
hostapd ubus interface and `del_client` permission, a button can disconnect
an associated wireless station. This is an administrative action affecting
another device's network connection; enable it only on networks you manage.
The control is available only while the station is present.
