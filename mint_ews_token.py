#!/usr/bin/env python3
"""Mint an MSAL token cache for the Exchange Online (EWS) calendar backend.

Interactive auth-code + PKCE (NOT device-code — device-code can never satisfy a
device-based Conditional Access grant, and the EWS escape hatch depends on an
interactive flow against the Exchange Online resource). Opens a browser; sign in
as the target mailbox. The resulting MSAL cache (access + refresh token, scoped to
EWS) is written to OUT and refreshed silently afterwards by ExchangeCalendar.

Uses a first-party PUBLIC client that registers http://localhost so the flow needs
no app registration of our own. Default is the Azure CLI client; the requested
*resource* (outlook.office365.com / EWS) is the lever, not the client_id.

Run on a machine with a browser, in the auth venv:
    .venv-auth/bin/python mint_ews_token.py
Override the client if needed (e.g. to retry with a different public client):
    CLIENT_ID=... .venv-auth/bin/python mint_ews_token.py

On success it also writes/updates exchange_client.json (client_id, tenant, smtp)
for the backend to consume.

⚠️ EWS in Exchange Online is being retired (~Oct 2026 → Apr 2027); this is a
stopgap for write access where Microsoft Graph is Conditional-Access-blocked.
"""
import base64
import json
import os

import msal

# Azure CLI: first-party PUBLIC client with http://localhost redirect + broad
# (FOCI) resource access, so MSAL's interactive flow works without our own app.
CLIENT_ID = os.environ.get("CLIENT_ID", "04b07795-8ddb-461a-bbee-02f9e1bf7b46")
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
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    print(f"client_id : {CLIENT_ID}")
    print(f"scope     : {SCOPES[0]}")
    print("Opening browser — sign in as the target mailbox...\n")
    result = app.acquire_token_interactive(scopes=SCOPES)

    if "access_token" not in result:
        desc = result.get("error_description", result)
        raise SystemExit(f"Auth failed: {desc}")

    claims = _claims(result["access_token"])
    aud = claims.get("aud", "")
    scp = claims.get("scp", "")
    tid = claims.get("tid")
    smtp = claims.get("upn") or claims.get("preferred_username") or claims.get("unique_name")

    print("Access-token routing claims:")
    for k in ("aud", "appid", "scp", "tid", "upn"):
        print(f"  {k:6}: {claims.get(k)}")

    ok_aud = "outlook.office365.com" in aud
    ok_scp = "EWS.AccessAsUser.All" in scp
    if not (ok_aud and ok_scp):
        print("\n⚠️  This token is NOT a usable EWS token:")
        if not ok_aud:
            print(f"    aud is '{aud}', expected https://outlook.office365.com")
        if not ok_scp:
            print(f"    scp '{scp}' lacks EWS.AccessAsUser.All")
        print("    This client can't get EWS here — fall back to mint_ews_from_apple.py.")
        raise SystemExit(1)

    with open(OUT, "w") as fh:
        fh.write(cache.serialize())
    creds = {
        "client_id": CLIENT_ID,
        "primary_smtp_address": smtp,
        "tenant_id": tid,
        "authority": f"https://login.microsoftonline.com/{tid}" if tid else AUTHORITY,
        "ews_endpoint": EWS_ENDPOINT,
    }
    with open(CREDS_OUT, "w") as fh:
        json.dump(creds, fh, indent=2)

    print(f"\n✅ Wrote {OUT} and {CREDS_OUT} for {smtp}")
    print("   Next: prove the data plane with test_ews_dataplane.py, then wire into config.yaml.")


if __name__ == "__main__":
    main()
