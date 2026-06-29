#!/usr/bin/env python3
"""Probe whether Conditional Access blocks an *Exchange Online (EWS)* token on this
device — the test our earlier Graph attempts never ran.

Background: every prior attempt requested a **Microsoft Graph** token via the
**device-code** flow and hit AADSTS53003. But (1) CA is evaluated per *resource*,
so Exchange Online (outlook.office365.com) is a separate CA target from Graph, and
(2) device-code can *never* satisfy a device-based CA grant by design. Apple's
native Calendar talks **EWS over interactive OAuth** and works on this same
unmanaged Mac — so the EXO resource may be open.

This probe mimics the part that matters (resource = EXO, flow = interactive
auth-code) without touching the Keychain or Apple's rotating refresh token.

Outcomes:
  * prints a decoded access token (aud/appid/scp) -> EXO is NOT CA-blocked here
    -> an EWS backend (exchangelib) is feasible (until the tenant's EWS cutoff).
  * AADSTS53003 / blocked -> EXO is in the device policy too -> only the
    read-only published-ICS feed remains as a CA-free path.

Run on the Mac (it opens a browser), in the auth venv:
    .venv-auth/bin/python probe_exo_token.py
Optionally override the client / scope / authority:
    CLIENT_ID=... SCOPE=... AUTHORITY=... .venv-auth/bin/python probe_exo_token.py
"""
import base64
import json
import os

import msal

# Azure CLI: a Microsoft first-party PUBLIC client that registers http://localhost,
# so MSAL's interactive flow works without owning an app. We only care whether the
# *EXO token request* is allowed by CA — the resource is the lever, not the client.
# To test faithfully as Apple instead, knowing it won't work with localhost:
#   Apple Internet Accounts = f8d98a96-0999-43f5-8af3-69971c7bb423 (custom-scheme redirect only)
CLIENT_ID = os.environ.get("CLIENT_ID", "04b07795-8ddb-461a-bbee-02f9e1bf7b46")
# EWS delegated scope on the Exchange Online resource (what macOS Calendar uses).
SCOPE = os.environ.get("SCOPE", "https://outlook.office365.com/EWS.AccessAsUser.All")
# 'organizations' = any work/school tenant; or pin to the constructor.tech tenant GUID.
AUTHORITY = os.environ.get("AUTHORITY", "https://login.microsoftonline.com/organizations")


def _decode_claims(jwt):
    """Decode (not verify) a JWT payload; return only the non-secret routing claims."""
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return {k: data.get(k) for k in ("aud", "appid", "app_displayname", "scp", "tid", "upn", "unique_name")}
    except Exception as exc:  # noqa: BLE001
        return {"<decode-failed>": str(exc)}


def main():
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    print(f"client_id : {CLIENT_ID}")
    print(f"scope     : {SCOPE}")
    print(f"authority : {AUTHORITY}")
    print("Opening browser for interactive sign-in (log in as the M365 account)...\n")

    result = app.acquire_token_interactive(scopes=[SCOPE])

    if "access_token" in result:
        print("✅ TOKEN ISSUED — Conditional Access did NOT block the Exchange Online resource here.")
        print("   Access-token routing claims (no secret, no signature):")
        for k, v in _decode_claims(result["access_token"]).items():
            print(f"     {k:16}: {v}")
        print("\n   => EWS path is feasible. Next: prove the data plane with exchangelib,")
        print("      and remember EWS retires Oct 2026 (tenant flip) -> Apr 2027 (final).")
    else:
        err = result.get("error")
        desc = result.get("error_description", "")
        print(f"❌ NO TOKEN — error: {err}")
        print(f"   {desc.splitlines()[0] if desc else result}")
        if "53003" in desc or "AADSTS53003" in desc:
            print("\n   => This is the same Conditional Access block as Graph, now on EXO too.")
            print("      The EWS escape hatch is closed for this tenant; only the read-only")
            print("      published-ICS feed remains as a CA-free path.")


if __name__ == "__main__":
    main()
