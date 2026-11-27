# Live PPPoE monitoring

## Upgrade

Stop the running app and extract this package to a new folder. From the previous installation,
copy your existing `.env` and `instance/` folder into the new project. If your database is
stored at a custom `DATABASE_PATH`, keep that setting and point it to the existing file.
Keep a backup first. This preserves the administrator accounts, IP allocations settings and
recorded PPPoE events. For a fresh install copy `.env.example` to `.env`, set the router
credentials and an initial admin password, and consult `INSTALLATION_GUIDE.md`.

Install the existing requirements with `python -m pip install -r requirements.txt` and
start the app with `python app.py` or the existing service. Use one worker process so the
log collector and live rate history baselines are shared across dashboard requests.
The RouterOS account needs `read,api` and access to the queried menus.
The app only reads RouterOS. Keep the dashboard on your management LAN or VPN.

## Active PPPoE & Queues

The page lists active PPPoE sessions across all pools. The package column uses the
local PPP secret profile when available. A RADIUS-only account can have an unknown profile.
Interface rates come from RX and TX byte counter differences in successive samples,
with RX shown as client upload. Per-session attribution uses the standard
`<pppoe-username>` interface name when there is one active session for that username.
If no interface can be matched safely, its rate displays as unavailable.

Simple Queues with a single client IP or matching PPPoE interface target show their own
upload/download rates. Shared subnet targets, PCQ sub-queues and Queue Trees cannot
be attributed by this view. Use the interface column for actual per-session traffic.
Click a username or queue name to switch the live graph. Samples are collected on
demand, typically every 4–6 seconds, and the graph retains up to 60 samples in the current tab.

## Destination Traffic

Set `ENABLE_DESTINATION_MONITOR=1` in `.env` and restart the app. Set
`ASN_MMDB` to a direct HTTPS GeoLite2 ASN MMDB URL or a local MMDB file path.
The app streams online MMDB data to temporary storage and memory-maps it.
The first visit starts the download in the background. While the page is used,
a successful download is refreshed after one hour, and a failed download is
retried after five minutes. A fixed release URL must be changed to use a newer
release. Lookups run locally without sending destination IPs to the data provider.
If `ASN_MMDB` is unset, `ASN_CSV` accepts a local path or HTTPS CSV URL.
See [Docker deployment](DOCKER_DEPLOYMENT.md) for configuration examples.

The page samples IPv4 connection tracking on demand about every 10 seconds. The
first sample establishes a baseline. The next samples rank destination IPs by measured
traffic and show upload/download bytes, total Mbps and client attribution. Enter a
username or client IP to see the top destinations in that filtered result.
The detail table shows up to 250 matching client/destination pairs per sample.

Results cover tracked IPv4 connections initiated by uniquely identified PPPoE addresses.
Connections that disappear between samples can be missed. FastTrack can bypass
connection tracking and Simple Queues, so the counters can be incomplete. Each
sample reads the connection table. Check router load before leaving the view open on
a busy router. The app makes no firewall or FastTrack changes. An IP/ASN identifies
a network endpoint and may be shared by many sites, including CDN-hosted domains.

## Recent Events

Open **Recent Events** and filter by username or Connected/Disconnected. The router
log collector checks about every 12 seconds. The page also refreshes about every
12 seconds when Auto refresh is enabled. The timestamp is when the app collected
the RouterOS message. Router log entries that have already rolled out of the logging
buffer cannot be retrieved. The existing **Most Disconnected** and per-user history
views continue to use the saved event database.
