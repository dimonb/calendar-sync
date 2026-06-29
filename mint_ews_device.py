#!/usr/bin/env python3
"""Mint an EWS token cache via DEVICE-CODE flow using Apple's public client.

Only Apple's client (f8d98a96) is preauthorized for the Exchange Online resource
(Azure CLI hits AADSTS65002). Apple's interactive redirect is a custom scheme we
can't capture from a browser — but device-code needs no redirect at all: it prints
a code + URL, you enter it on any browser. No Keychain, no redirect hacks.

Works only if Apple's app permits the device-code grant (allowPublicClient). If it
doesn't, expect AADSTS7000218 / invalid_client — then we fall back to extracting
Apple's refresh token from the Keychain.

Run in the auth venv:
    .venv-auth/bin/python mint_ews_device.py
"""
import base64
import json
import os

import msal

APPLE_CLIENT_ID = "f8d98a96-0999-43f5-8af3-69971c7bb423"
AUTHORITY = os.environ.get("AUTHORITY", "https://login.microsoftonline.com/organizations")
SCOPES = ["https://outlook.office365.com/EWS.AccessAsUser.All"]
OUT = os.environ.get("OUT", "dimonb-token-outlook-ews.json")
CREDS_OUT = os.environ.get("CREDS_OUT", "exchange_client.json")
EWS_ENDPOINT = "https://outlook.office365.com/EWS/Exchange.asmx"


def _claims(jwt):
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def main():
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(APPLE_CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise SystemExit(
            f"Device flow not allowed for Apple's client: {flow.get('error_description', flow)}\n"
            "Fall back to mint_ews_from_apple.py (Keychain refresh-token reuse)."
        )
    print(flow["message"], flush=True)  # "go to microsoft.com/devicelogin and enter CODE"

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise SystemExit(f"Auth failed: {result.get('error_description', result)}")

    claims = _claims(result["access_token"])
    aud = claims.get("aud", "")
    scp = claims.get("scp", "")
    tid = claims.get("tid")
    smtp = claims.get("upn") or claims.get("preferred_username") or claims.get("unique_name")
    print("\nAccess-token routing claims:")
    for k in ("aud", "appid", "scp", "tid", "upn"):
        print(f"  {k:6}: {claims.get(k)}")

    if "outlook.office365.com" not in aud or "EWS.AccessAsUser.All" not in scp:
        raise SystemExit(f"Not a usable EWS token (aud={aud!r}, scp={scp!r}).")

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


if __name__ == "__main__":
    main()
