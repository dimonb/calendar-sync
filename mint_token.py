#!/usr/bin/env python3
"""Mint an OAuth token for a new Google calendar account.

Opens a browser (run_local_server), you log in as the target account and grant
Calendar access; the resulting token JSON is written to OUT.

Usage:
    python mint_token.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow

# Reuse the existing creds1 OAuth (Desktop) client.
CLIENT_SECRET = "client_secret_dimonb.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
OUT = "dimonb-token-globalescorthub.json"

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(OUT, "w") as f:
        f.write(creds.to_json())
    print(f"Wrote {OUT}. Log in account was used to authorize.")
