#!/usr/bin/env python3
"""Mint an EWS token via interactive auth-code + PKCE with Apple's client.

This reproduces exactly what Apple's native Calendar does — the only flow that
passes this tenant's Conditional Access (device-code -> 53003; Azure CLI -> 65002).
Apple's redirect is a custom scheme we capture by hand.

Step 1 — get the sign-in URL:
    .venv-auth/bin/python mint_ews_authcode.py url

  Open the printed URL, sign in as dimonb@constructor.tech. The browser will then
  try to redirect to  com.apple.Preferences://oauth-redirect?code=...&state=...
  and fail to open anything — that's fine, we just need that URL:
    Chrome/Edge: open DevTools (Cmd+Opt+I) -> Network, tick "Preserve log",
      THEN sign in. Click the last 'authorize' request -> Headers -> Response
      Headers -> copy the full 'location:' value (com.apple.Preferences://...).
    Firefox: it pops a dialog with the URL — copy it from there.

Step 2 — exchange the captured redirect for tokens:
    REDIRECT='com.apple.Preferences://oauth-redirect?code=...&state=...' \
      .venv-auth/bin/python mint_ews_authcode.py exchange
"""
import base64
import json
import os
import sys
import urllib.parse

import msal

APPLE_CLIENT_ID = "f8d98a96-0999-43f5-8af3-69971c7bb423"
AUTHORITY = os.environ.get("AUTHORITY", "https://login.microsoftonline.com/organizations")
SCOPES = ["https://outlook.office365.com/EWS.AccessAsUser.All"]
REDIRECT_URI = os.environ.get("REDIRECT_URI", "com.apple.Preferences://oauth-redirect")
FLOW_FILE = ".ews_authcode_flow.json"
OUT = os.environ.get("OUT", "dimonb-token-outlook-ews.json")
CREDS_OUT = os.environ.get("CREDS_OUT", "exchange_client.json")
EWS_ENDPOINT = "https://outlook.office365.com/EWS/Exchange.asmx"


def _claims(jwt):
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def cmd_url():
    app = msal.PublicClientApplication(APPLE_CLIENT_ID, authority=AUTHORITY)
    flow = app.initiate_auth_code_flow(SCOPES, redirect_uri=REDIRECT_URI)
    with open(FLOW_FILE, "w") as fh:
        json.dump(flow, fh)
    print("Open this URL, sign in as the mailbox, then capture the redirect URL:\n")
    print(flow["auth_uri"])


def cmd_exchange():
    with open(FLOW_FILE) as fh:
        flow = json.load(fh)
    redirect = os.environ.get("REDIRECT") or (sys.argv[2] if len(sys.argv) > 2 else "")
    if not redirect:
        raise SystemExit("Pass the captured redirect via REDIRECT='com.apple.Preferences://...'")
    query = urllib.parse.urlparse(redirect.strip()).query or redirect.split("?", 1)[-1]
    auth_response = dict(urllib.parse.parse_qsl(query))

    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(APPLE_CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    result = app.acquire_token_by_auth_code_flow(flow, auth_response, scopes=SCOPES)

    if "access_token" not in result:
        raise SystemExit(f"Exchange failed: {result.get('error_description', result)}")

    claims = _claims(result["access_token"])
    aud, scp, tid = claims.get("aud", ""), claims.get("scp", ""), claims.get("tid")
    smtp = claims.get("upn") or claims.get("preferred_username") or claims.get("unique_name")
    print("Access-token routing claims:")
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
    cmd = sys.argv[1] if len(sys.argv) > 1 else "url"
    {"url": cmd_url, "exchange": cmd_exchange}.get(cmd, cmd_url)()
