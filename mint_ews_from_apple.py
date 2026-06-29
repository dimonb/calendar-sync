#!/usr/bin/env python3
"""Fallback minter: seed the EWS token cache by reusing Apple Calendar's own
refresh token from the macOS Keychain.

Use this only if mint_ews_token.py can't obtain an EWS-scoped token (its client
isn't authorized for EWS in the tenant). Apple's native Calendar already holds a
refresh token for this mailbox, minted for Apple's public client with the EWS
scope already consented — we redeem it for our own EWS access/refresh tokens.

⚠️ Redeeming rotates the refresh token and will likely BREAK the native Apple
Calendar sync for this account. Reconnect it in System Settings afterwards.

Run on the Mac (needs Keychain access — you may get a GUI "allow" prompt), in the
auth venv:
    .venv-auth/bin/python mint_ews_from_apple.py
Override the keychain account (the Internet-Accounts UUID or the email) if needed:
    KC_ACCOUNT=8A71E59E-7310-4037-919B-E37D178B7A35 .venv-auth/bin/python mint_ews_from_apple.py
"""
import base64
import json
import os
import subprocess

import msal

# Apple "Internet Accounts" / "iOS Accounts" — public client, same GUID every
# tenant, already consented for EWS.AccessAsUser.All.
APPLE_CLIENT_ID = "f8d98a96-0999-43f5-8af3-69971c7bb423"
AUTHORITY = os.environ.get("AUTHORITY", "https://login.microsoftonline.com/organizations")
SCOPES = ["https://outlook.office365.com/EWS.AccessAsUser.All"]
OUT = os.environ.get("OUT", "dimonb-token-outlook-ews.json")
CREDS_OUT = os.environ.get("CREDS_OUT", "exchange_client.json")
EWS_ENDPOINT = "https://outlook.office365.com/EWS/Exchange.asmx"
# The CT (constructor.tech) Exchange account's Internet-Accounts UUID, from
# ~/Library/Accounts/Accounts4.sqlite. Used as the keychain item's account attr.
KC_ACCOUNT = os.environ.get("KC_ACCOUNT", "8A71E59E-7310-4037-919B-E37D178B7A35")
CANDIDATE_SERVICES = [
    os.environ.get("KC_SERVICE")] if os.environ.get("KC_SERVICE") else [
    "com.apple.account.Exchange.oauth-refresh-token",
    "com.apple.account.Exchange.oauth-refreshtoken",
    "com.apple.account.Exchange.refresh-token",
]


def _claims(jwt):
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _read(service, account):
    cmd = ["security", "find-generic-password", "-s", service]
    if account:
        cmd += ["-a", account]
    cmd += ["-w"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        v = r.stdout.strip()
        # Reject access tokens (JWTs start "eyJ"); a refresh token is opaque.
        if v and not v.startswith("eyJ"):
            return v
    return None


def keychain_refresh_token():
    """Find Apple's Exchange OAuth refresh token in the login keychain.

    Tries the known service names, both scoped to the CT account UUID and
    unscoped. A GUI "allow" prompt may appear — click Allow (Always Allow).
    """
    for service in CANDIDATE_SERVICES:
        for account in (KC_ACCOUNT, None):
            rt = _read(service, account)
            if rt:
                print(f"  found keychain item: service={service} account={account or '(any)'}")
                return rt
    raise SystemExit(
        "Could not find Apple's Exchange refresh token in the keychain.\n"
        "Discover the exact item name with (then pass KC_SERVICE=...):\n"
        "  security dump-keychain 2>/dev/null | grep -iB2 -A4 'Exchange.*oauth'\n"
        "or open Keychain Access.app and search 'oauth-refresh'."
    )


def main():
    rt = keychain_refresh_token()
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(APPLE_CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    print(f"client_id : {APPLE_CLIENT_ID} (Apple Internet Accounts)")
    print(f"scope     : {SCOPES[0]}")
    print("Redeeming Apple's refresh token for an EWS token...\n")
    result = app.acquire_token_by_refresh_token(rt, scopes=SCOPES)

    if "access_token" not in result:
        desc = result.get("error_description", result)
        raise SystemExit(f"Redeem failed: {desc}")

    claims = _claims(result["access_token"])
    tid = claims.get("tid")
    smtp = claims.get("upn") or claims.get("preferred_username") or claims.get("unique_name")
    print("Access-token routing claims:")
    for k in ("aud", "appid", "scp", "tid", "upn"):
        print(f"  {k:6}: {claims.get(k)}")

    if "outlook.office365.com" not in claims.get("aud", ""):
        raise SystemExit(f"Unexpected aud {claims.get('aud')}; not an EWS token.")

    with open(OUT, "w") as fh:
        fh.write(cache.serialize())
    creds = {
        "client_id": APPLE_CLIENT_ID,
        "primary_smtp_address": smtp,
        "tenant_id": tid,
        "authority": f"https://login.microsoftonline.com/{tid}" if tid else AUTHORITY,
        "ews_endpoint": EWS_ENDPOINT,
    }
    with open(CREDS_OUT, "w") as fh:
        json.dump(creds, fh, indent=2)
    print(f"\n✅ Wrote {OUT} and {CREDS_OUT} for {smtp}")
    print("   Native Apple Calendar for this account may now be broken — reconnect it if you still want it.")


if __name__ == "__main__":
    main()
