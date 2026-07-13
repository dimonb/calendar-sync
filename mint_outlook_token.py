#!/usr/bin/env python3
"""Mint an MSAL token cache for an Outlook / Microsoft 365 calendar account.

Runs the device-code flow: prints a URL and a code, you sign in as the target
account in any browser and grant Calendar access. The resulting MSAL token
cache (access + refresh token) is written to OUT and reused/refreshed silently
by the OutlookCalendar backend.

Run it in the auth venv (has msal):
    .venv-auth/bin/python mint_outlook_token.py

Requires an Azure app registration with:
  - "Allow public client flows" = Yes (Authentication blade)
  - Delegated permission Microsoft Graph > Calendars.ReadWrite (+ offline_access)
"""
import json

import msal

# --- edit these ----------------------------------------------------------- #
CREDENTIALS = "outlook_client.json"   # {"client_id": "...", "tenant_id": "..."}
OUT = "dimonb-token-outlook.json"     # token cache to create (gitignored)
# Keep in sync with SCOPES in calendar_sync/calendars/outlook_calendar.py
SCOPES = ["Calendars.ReadWrite"]
# -------------------------------------------------------------------------- #

if __name__ == "__main__":
    with open(CREDENTIALS) as fh:
        creds = json.load(fh)
    authority = creds.get("authority") or (
        f"https://login.microsoftonline.com/{creds['tenant_id']}"
    )

    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(
        creds["client_id"], authority=authority, token_cache=cache
    )

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise SystemExit(f"Failed to start device flow: {flow}")
    print(flow["message"], flush=True)

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise SystemExit(f"Auth failed: {result.get('error_description', result)}")

    with open(OUT, "w") as fh:
        fh.write(cache.serialize())
    print(f"Wrote {OUT} for {result.get('id_token_claims', {}).get('preferred_username', '?')}")
