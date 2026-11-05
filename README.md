<p align="center">
  <a href="https://my.home-assistant.io/redirect/marketplace_repository/?owner=pschmitt&amp;repository=homeassistant-openwrt-ubus&amp;category=integration"><img src="https://my.home-assistant.io/badges/marketplace_repository.svg" alt="Open this integration in Home Assistant Marketplace"></a>
</p>

<h1 align="center">OpenWrt Ubus for Home Assistant</h1>

<p align="center">Monitor OpenWrt devices, wireless clients and services through ubus.</p>

[中文版本](README_zh.md)

## Features

- **Network presence:** Track wireless stations and DHCP clients per access point or across roaming access points. See [Network tracking](docs/network-tracking.md).
- **Router telemetry:** Monitor uptime, memory, load, access points and optional QModem, MWAN3 and NLBWMon data.
- **Service control:** Start, stop, enable and restart supported OpenWrt services through Home Assistant controls. See [Router actions](docs/router-actions.md).
- **UCI actions:** Read and write router configuration through ubus when the configured account has permission.

## Install

Use the Marketplace badge above on Home Assistant 2026.11 or later to add this
repository as a custom integration. On older versions, add it as a HACS
custom repository of type **Integration**. Install and restart Home Assistant.
The badge does not imply a public catalog listing. For manual installation,
copy `custom_components/openwrt_ubus/` into Home Assistant's
`custom_components/` directory and restart.

## Quick start

1. Prepare the OpenWrt ubus HTTP endpoint and a suitably limited account. See [Router setup](docs/router-setup.md).
2. Add **OpenWrt ubus** under **Settings → Devices & services → Add integration**.
3. Enter the router address and account credentials, then select wireless and DHCP monitoring options.
4. Inspect the router's system sensors and discovered wireless devices.

## Documentation

| Topic | Description |
|-------|-------------|
| [Router setup](docs/router-setup.md) | Required services, access and troubleshooting |
| [Network tracking](docs/network-tracking.md) | Wireless, DHCP and roaming entity modes |
| [Router actions](docs/router-actions.md) | Service, UCI and optional device controls |
| [Release notes](CHANGELOG.md) | Notable changes |
| [中文版本](README_zh.md) | Chinese-language project documentation |

## License

[GPL-3.0](LICENSE). The older README's MPL-2.0 label did not match the
repository's license file.
