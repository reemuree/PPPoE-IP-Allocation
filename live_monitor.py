"""Shared, on-demand read-only monitoring samples."""
import csv
import ipaddress
import os
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import router_client as router


def pair(value):
    try:
        first, second = str(value).split("/")
        return int(first), int(second)
    except ValueError:
        return None


def delta(current, previous):
    if current is None or previous is None or any(a < b for a, b in zip(current, previous)):
        return None
    return tuple(a - b for a, b in zip(current, previous))


def address(value):
    value = str(value or "")
    try:
        return ipaddress.IPv4Address(value)
    except ValueError:
        try:
            return ipaddress.IPv4Address(value.rsplit(":", 1)[0])
        except ValueError:
            return None


@lru_cache(maxsize=2)
def asn_index(path, modified):
    groups = defaultdict(dict)
    with open(path, encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            network = ipaddress.IPv4Network(row["network"])
            groups[network.prefixlen][int(network.network_address)] = (
                "AS" + row["autonomous_system_number"] + " " + row["autonomous_system_organization"]
            )
    return sorted(groups.items(), reverse=True)


def asn_name(ip, index):
    for prefix, entries in index:
        match = entries.get((ip >> (32 - prefix)) << (32 - prefix))
        if match:
            return match
    return ""


class LiveMonitor:
    def __init__(self, destinations=False):
        self.destinations = destinations
        self.interval = 10 if destinations else 4
        self.lock = threading.Lock()
        self.last_attempt = float("-inf")
        self.previous_at = None
        self.previous = {}
        self.output = {}
        self.error = None

    def read(self, cfg):
        with self.lock:
            if time.monotonic() - self.last_attempt >= self.interval:
                try:
                    self.output = self.collect(cfg)
                    self.error = None
                except router.RouterError as exc:
                    self.error = exc
                    self.previous_at = None
                    self.previous = {}
                finally:
                    self.last_attempt = time.monotonic()
            if self.error is not None:
                raise self.error
            return self.output

    def collect(self, cfg):
        api = None
        warnings = []
        try:
            api = router._connect(cfg)
            active = router._read(api, ("ppp", "active"),
                                  router.ACTIVE_FIELDS + (".id", "session-id"))
            active = [row for row in active if row.get("service") == "pppoe"]
            if self.destinations:
                flows = router._read(api, ("ip", "firewall", "connection"), (
                    ".id", "protocol", "src-address", "dst-address", "orig-bytes",
                    "repl-bytes", "fasttrack",
                ))
            else:
                secrets = self.optional(api, ("ppp", "secret"), ("name", "profile"), warnings)
                interfaces = self.optional(api, ("interface",), router.INTERFACE_FIELDS + (".id",), warnings)
                queues = self.optional(api, ("queue", "simple"), ("name", "target", "rate", "bytes", "disabled", ".id"), warnings)
        except Exception as exc:
            raise router._translate(exc, cfg) from None
        finally:
            router._close(api)

        now = time.monotonic()
        elapsed = None if self.previous_at is None else now - self.previous_at
        # A return after a long pause starts a fresh baseline.
        if elapsed is not None and not 0 < elapsed <= self.interval * 4:
            elapsed = None
        counters = {}
        if self.destinations:
            rows = self.destination_rows(active, flows, counters, elapsed, warnings)
        else:
            rows = self.session_rows(active, secrets, interfaces, queues, counters, elapsed)
        self.previous, self.previous_at = counters, now
        return {"rows": rows, "warnings": warnings, "warming": elapsed is None,
                "sampled_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def optional(api, path, fields, warnings):
        try:
            if path == ("queue", "simple"):
                props = ",".join(fields)
                return list(api.rawCmd("/queue/simple/print", "=stats=", f"=.proplist={props}"))
            return router._read(api, path, fields)
        except router.TrapError:
            warnings.append(f"/{'/'.join(path)} data unavailable.")
            return []

    def rate(self, key, current, counters, elapsed):
        counters[key] = current
        change = delta(current, self.previous.get(key))
        return [round(value * 8 / elapsed) for value in change] if elapsed and change is not None else None

    def session_rows(self, active, secrets, interfaces, queues, counters, elapsed):
        profiles = {row.get("name"): row.get("profile") for row in secrets}
        by_interface = {row.get("name"): row for row in interfaces if row.get("type") == "pppoe-in"}
        names = Counter(row.get("name") for row in active)
        ips = Counter(row.get("address") for row in active)
        by_target = defaultdict(list)
        for queue in queues:
            if str(queue.get("disabled")).lower() in ("true", "yes", "1"):
                continue
            target = str(queue.get("target") or "").strip()
            # Only single-host or single-interface queues can be attributed.
            if target.endswith("/32"):
                target = target[:-3]
            if target and "," not in target:
                by_target[target].append(queue)

        rows = []
        for session in active:
            name, ip = session.get("name"), session.get("address")
            iface_name = f"<pppoe-{name}>"
            iface = by_interface.get(iface_name) if names[name] == 1 else None
            key = (session.get(".id"), session.get("session-id"), name, ip, session.get("caller-id"))
            traffic = None
            if iface:
                values = pair(f"{iface.get('rx-byte')}/{iface.get('tx-byte')}")
                traffic = self.rate(("iface", key, iface.get(".id")), values, counters, elapsed)
            matches = list(by_target.get(ip, ())) if ips[ip] == 1 else []
            if names[name] == 1:
                matches.extend(by_target.get(iface_name, ()))
            queue_rates = []
            for queue in matches:
                measured = self.rate(("queue", key, queue.get(".id"), queue.get("name")),
                                     pair(queue.get("bytes")), counters, elapsed)
                queue_rates.append({"name": queue.get("name"), "rate": pair(queue.get("rate")) or measured})
            rows.append({"id": str(session.get(".id") or name), "name": name, "ip": ip,
                         "uptime": session.get("uptime"), "caller_id": session.get("caller-id"),
                         "profile": profiles.get(name), "traffic": traffic, "queues": queue_rates})
        return rows

    def destination_rows(self, active, flows, counters, elapsed, warnings):
        owners = defaultdict(list)
        for row in active:
            ip = address(row.get("address"))
            if ip is not None:
                owners[ip].append(row)
        paths = defaultdict(lambda: [0, 0])
        fasttrack = False
        for flow in flows:
            source = address(flow.get("src-address"))
            dest = address(flow.get("dst-address"))
            if len(owners.get(source, ())) != 1 or dest is None or source == dest:
                continue
            session = owners[source][0]
            key = (session.get(".id"), session.get("session-id"), flow.get(".id"),
                   flow.get("protocol"), flow.get("src-address"), flow.get("dst-address"))
            current = pair(f"{flow.get('orig-bytes')}/{flow.get('repl-bytes')}")
            fasttrack |= str(flow.get("fasttrack")).lower() in ("true", "yes", "1")
            counters[key] = current
            if elapsed is None:
                continue
            change = delta(current, self.previous[key]) if key in self.previous else current
            if change and any(change):
                total = paths[(session.get("name"), str(source), int(dest))]
                total[0] += change[0]
                total[1] += change[1]

        if fasttrack:
            warnings.append("FastTracked traffic may be undercounted.")
        index = []
        configured = os.environ.get("ASN_CSV")
        if configured:
            try:
                path = Path(configured)
                index = asn_index(str(path), path.stat().st_mtime_ns)
            except (OSError, KeyError, ValueError):
                warnings.append("ASN CSV could not be loaded.")
        else:
            warnings.append("Set ASN_CSV to show destination ASN and organization.")
        return [{"name": name, "ip": source, "destination": str(ipaddress.IPv4Address(dest)),
                 "asn": asn_name(dest, index), "up": up, "down": down,
                 "bps": round((up + down) * 8 / elapsed)}
                for (name, source, dest), (up, down) in sorted(
                    paths.items(), key=lambda item: sum(item[1]), reverse=True)]
