# MikroTik PPPoE IP Manager

A self-hosted dashboard for ISP operators who manage static PPPoE IP assignments and monitor MikroTik subscribers. It uses a read-only RouterOS API connection and runs on Docker, including CasaOS hosts.

## Features

| Feature | What you can see |
| --- | --- |
| IP allocation | Free, assigned and reserved IPs across selected CIDRs, duplicate assignments, out-of-range addresses and CSV export |
| Active PPPoE sessions | Username, client IP, configured PPP profile, uptime and live upload/download rates |
| Simple Queues | Bandwidth rates and live graphs for queues matched to individual clients |
| Destination traffic | Top IPv4 destinations by measured traffic, per-client destination traffic and optional ASN organization lookup |
| Connection logs | Connect/disconnect events, username and event filters, user history and most-disconnected subscribers |

Built with Python, Flask, SQLite, Gunicorn and vanilla JavaScript. The dashboard stores application settings and collected PPPoE events in SQLite.

## Quick start with Docker Compose

You need Docker with the Compose plugin and a RouterOS API account with `read,api` permissions. The Docker host must be able to reach the router's management address and API port.

From the project directory containing `Dockerfile` and `compose.yaml`:

```sh
cp -n .env.example .env
mkdir -p instance
```

Edit `.env` before starting:

| Variable | Value |
| --- | --- |
| `ROUTER_HOST` | MikroTik management IP or hostname |
| `ROUTER_USER` | Read-only RouterOS API username |
| `ROUTER_PASSWORD` | RouterOS API password |
| `ROUTER_PORT` | Your API service port. Defaults to 8728, or 8729 with API-SSL |
| `ROUTER_USE_SSL` | Set to `true` to use API-SSL |
| `ADMIN_USER` | Initial dashboard username. Defaults to `admin` |
| `ADMIN_PASSWORD` | Initial dashboard password, at least 10 characters |

```sh
sudo chown 1000:1000 .env
sudo chown -R 1000:1000 instance
sudo chmod 600 .env
sudo docker compose up -d --build
sudo docker compose ps
```

Open `http://<server-LAN-IP>:8088` and sign in. For an existing installation, stop the old app and back up and copy its `.env` and `instance/` before starting the container. See [Docker deployment](DOCKER_DEPLOYMENT.md) if you use a custom SQLite path.

## CasaOS

Use the Docker Compose quick start on the CasaOS server. To install through the CasaOS dashboard, place the project at `/DATA/AppData/pppoe-ip-manager` and complete the file and permission setup above. Build the image on that server:

```sh
cd /DATA/AppData/pppoe-ip-manager
sudo docker build -t pppoe-ip-manager:local .
```

In **App Store → Custom Install → Import**, paste [casaos-compose.yaml](casaos-compose.yaml). If the import fails, use Docker Compose on the same server and inspect its output. Both configurations publish port 8088.

## Enable destination traffic and ASN names

Set `ENABLE_DESTINATION_MONITOR=1` in `.env`. For ASN organization names, place a GeoLite2 ASN IPv4 Blocks CSV inside `instance/` and set:

```dotenv
ASN_CSV=/app/instance/GeoLite2-ASN-Blocks-IPv4.csv
```

Restart the app and open **Destination Traffic**. The view ranks IPv4 destinations by sampled traffic volume. Filter by username or client IP to see a subscriber's top destinations. IPs can be shared across websites, and FastTracked or short-lived connections can be undercounted. Queue rates are available for supported single-client Simple Queue targets. See [Live monitoring](LIVE_MONITORING.md) for collection details.

## Troubleshooting

```sh
sudo docker compose ps
sudo docker compose logs --tail=100 pppoe-ip-manager
```

- If CasaOS cannot find the image, check `sudo docker image inspect pppoe-ip-manager:local`.
- If the dashboard loads but cannot sync, check the router address, API port, account permissions and reachability from the Docker host.
- If SQLite reports a permission error, check UID/GID 1000 ownership on the mounted `instance/` directory.
- When opening an issue, include the failing command, relevant error, and RouterOS and Docker versions. Remove credentials and subscriber data from logs before posting.

