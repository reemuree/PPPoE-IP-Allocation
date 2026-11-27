# Docker deployment

The container listens on port 5000. The supplied configurations publish it on host port 8088.
Open `http://<server-LAN-IP>:8088` from your management LAN. The container must be able to reach
your MikroTik management IP and the configured RouterOS API port. Use the router's IP address
as reachable from the Docker host. The Compose network uses Docker's default bridge.

## Prepare the files

Extract the ZIP on your Docker host. For CasaOS, extract the `pppoe-ip-manager` folder under
`/DATA/AppData/`, so the Compose bind mounts match. Run these commands from inside the project folder.

Fresh installation:

```sh
cp -n .env.example .env
mkdir -p instance
```

Edit `.env` with `ROUTER_HOST`, `ROUTER_USER`, `ROUTER_PASSWORD` and a strong initial
`ADMIN_PASSWORD` of at least 10 characters. Set API port and TLS options to match the router.
If a password includes an inline comment or expansion characters, follow python-dotenv quoting rules.

Migration: stop the old app, back up its files, then copy its `.env` and entire `instance/` directory
into this project. Copying the full directory preserves the SQLite database, login accounts,
IP settings, existing events and secret key. If the old app used a custom `DATABASE_PATH`,
copy the database and corresponding secret key into `instance/` and set
`DATABASE_PATH=/app/instance/app.db` in `.env`. Rename the copied database to `app.db` if necessary.
For a standard installation, remove any old host-only `DATABASE_PATH` override.
For direct HTTP access, set `SESSION_COOKIE_SECURE=false` if that setting was previously enabled
for an HTTPS proxy.

For destination monitoring, enable `ENABLE_DESTINATION_MONITOR=1` in `.env`.
Set `ASN_MMDB` to a direct HTTPS download link for GeoLite2 ASN:

```dotenv
ASN_MMDB="https://github.com/FyraLabs/geolite2/releases/download/1795745698/GeoLite2-ASN.mmdb"
```

The container needs outbound HTTPS access. On first use of Destination Traffic, the app
streams the database to a temporary file and memory-maps it for local IP lookups.
The app refreshes the database on demand after one hour and keeps the last usable
database if a refresh fails. A fixed release URL stays on that release until you
change it. No ASN file is required in the persistent data directory.

You can also set `ASN_MMDB=/app/instance/GeoLite2-ASN.mmdb` for a local file.
Existing `ASN_CSV` configuration still works when `ASN_MMDB` is unset.

Give the non-root container user access to the application data before starting:

```sh
sudo chown 1000:1000 .env
sudo chown -R 1000:1000 instance
sudo chmod 600 .env
```

## Option 1: Docker Compose

```sh
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=100 pppoe-ip-manager
```

## Option 2: CasaOS Custom Install

Build the image on the CasaOS server:

```sh
cd /DATA/AppData/pppoe-ip-manager
sudo docker build -t pppoe-ip-manager:local .
```

In CasaOS, open **App Store → Custom Install → Import** and paste the contents of
`casaos-compose.yaml`. Install and open the app. The image tag refers to the image built on
that server. If your CasaOS version rejects the import, use the Docker Compose commands above
on the same server. Use one deployment option for this host port.

## Operations

- To use another host port, change `8088:5000` in the selected Compose file. For CasaOS also
  set `port_map` to the new host port.
- After editing `.env`, restart the app in CasaOS or run `sudo docker compose restart`.
- Back up `.env` and `instance/` with the app stopped. Docker image rebuilds do not replace them.
- Gunicorn uses one worker with threads so polling and rate baselines are shared.
  The Docker health check verifies that the login page responds. Router connectivity is
  shown separately inside the app.
