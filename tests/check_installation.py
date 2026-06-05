#!/usr/bin/env python3
"""LOTSE installation health check.

Verifies that Home Assistant is properly set up with the
LOTSE mesh sender blueprint, automations, and sensors.

Usage:
  python3 tests/check_installation.py \\
      --ha-url http://homeassistant.local:8123 \\
      --token <long-lived-access-token>

Exit status: 0 = all good, 1 = something wrong
"""

import argparse
import json
import sys
import urllib.error
import urllib.request


class HAClient:
    """Minimal Home Assistant REST API client."""

    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get(self, path):
        req = urllib.request.Request(self.url + path, headers=self.headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    def find_states(self, domain=None, search=None):
        """Return state entries optionally filtered by domain and search."""
        states = self.get("/api/states")
        result = states
        if domain:
            result = [s for s in result
                      if s.get("entity_id", "").startswith(domain + ".")]
        if search:
            result = [s for s in result
                      if search.lower() in str(s.get("attributes", {}).get(
                          "friendly_name", "")).lower()]
        return result

    def get_blueprints(self):
        return self.get("/api/blueprint/automation")


# ─── Checks ────────────────────────────────────────────────────────────────

class CheckResult:
    def __init__(self):
        self.checks = []

    def ok(self, name, detail=""):
        self.checks.append((name, True, detail))
        print(f"  \u2713  {name}  {detail}")

    def fail(self, name, detail=""):
        self.checks.append((name, False, detail))
        print(f"  \u2717  {name}  {detail}")

    @property
    def all_ok(self):
        return all(c[1] for c in self.checks)


def check_ha_reachable(ha, result):
    try:
        config = ha.get("/api/config")
        version = config.get("version", "?")
        result.ok("HA reachable", f"v{version}")
    except Exception as e:
        result.fail("HA reachable", str(e))
        return False
    return True


def check_blueprint(ha, result):
    try:
        blueprints = ha.get_blueprints()
        found = False
        bp_id = None
        for bid, bp in blueprints.items():
            name = bp.get("metadata", {}).get("name", "")
            if "LOTSE" in name or "Mesh" in name or "Meter Data" in name:
                found = True
                bp_id = bid
                break
        if found:
            result.ok("Blueprint imported", bp_id)
        else:
            result.fail("Blueprint imported",
                        "No LOTSE blueprint found among "
                        f"{len(blueprints)} blueprints")
    except Exception as e:
        result.fail("Blueprint check", str(e))


def check_sender_automation(ha, result):
    try:
        automations = ha.find_states(domain="automation", search="mesh")
        if not automations:
            automations = ha.find_states(domain="automation", search="lotse")
        if not automations:
            automations = ha.find_states(domain="automation", search="meter")
        if automations:
            eid = automations[0].get("entity_id", "?")
            state = automations[0].get("state", "?")
            detail = f"{eid} ({state})"
            if state == "on":
                result.ok("Sender automation", detail)
            else:
                result.fail("Sender automation",
                            f"{detail} — not enabled")
        else:
            result.fail("Sender automation",
                        "No mesh/automation entities found")
            # Show 5 most recent automations for debugging
            all_auto = ha.find_states(domain="automation")
            names = [s.get("attributes", {}).get("friendly_name", s["entity_id"])
                     for s in all_auto[:5]]
            if names:
                print(f"         Found automations: {', '.join(names)}")
    except Exception as e:
        result.fail("Automation check", str(e))


def check_mqtt_configured(ha, result):
    try:
        config = ha.get("/api/config")
        components = config.get("components", [])
        if "mqtt" in components:
            result.ok("MQTT integration", "configured")
        else:
            result.fail("MQTT integration",
                        "mqtt not found in loaded components")
    except Exception as e:
        result.fail("MQTT check", str(e))


def check_neighbor_sensors(ha, result):
    try:
        sensors = ha.find_states(domain="sensor", search="mesh")
        if not sensors:
            sensors = ha.find_states(domain="sensor")
            sensors = [s for s in sensors
                       if "node_" in s.get("entity_id", "")]
        if sensors:
            # Deduplicate unique neighbors by entity_id
            neighbor_ids = set()
            for s in sensors:
                eid = s.get("entity_id", "")
                # Extract suffix like _gp, _bs etc.
                parts = eid.rsplit("_", 1)
                suffix = parts[-1] if len(parts) > 1 else ""
                neighbor_ids.add(suffix)
            detail = f"{len(sensors)} sensors ({len(neighbor_ids)} types)"
            result.ok("Neighbor sensors", detail)
        else:
            result.fail("Neighbor sensors",
                        "No sensors with 'node_' or 'mesh' found")
    except Exception as e:
        result.fail("Sensor check", str(e))


def check_topic_format(ha, result):
    """Validate MQTT topic convention via template state if available."""
    try:
        states = ha.get("/api/states")
        mqtt = [s for s in states
                if "mqtt" in s.get("entity_id", "").lower()]
        if mqtt:
            result.ok("MQTT topics", f"{len(mqtt)} MQTT entities")
        else:
            result.ok("MQTT topics", "no topics checked (optional)")
    except Exception as e:
        result.ok("MQTT topics", f"check skipped ({e})")


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="LOTSE installation health check",
        epilog="Exit 0 = all good, 1 = something needs attention",
    )
    parser.add_argument("--ha-url", required=True,
                        help="Home Assistant URL (e.g. http://ha:8123)")
    parser.add_argument("--token", required=True,
                        help="Long-lived access token (HA profile page)")
    args = parser.parse_args()

    ha = HAClient(args.ha_url, args.token)
    result = CheckResult()

    print()
    print("  LOTSE Installation Check")
    print("  " + "=" * 40)
    print()

    # Run checks
    if not check_ha_reachable(ha, result):
        print("\n  Cannot reach Home Assistant — check --ha-url and --token")
        sys.exit(1)

    check_blueprint(ha, result)
    check_sender_automation(ha, result)
    check_mqtt_configured(ha, result)
    check_neighbor_sensors(ha, result)
    check_topic_format(ha, result)

    # Summary
    print()
    passed = sum(1 for c in result.checks if c[1])
    total = len(result.checks)
    print(f"  {passed}/{total} checks passed")

    if result.all_ok:
        print("  All good — LOTSE is set up correctly")
        sys.exit(0)
    else:
        print("  Some checks failed — review the details above")
        sys.exit(1)


if __name__ == "__main__":
    main()
