#!/usr/bin/env python3
"""Mint a fresh OAuth token for dmitrii.balabanov@ebaconline.com.br (creds1).

Opens a browser (and prints the URL). Log in as the ebac account and grant
Calendar access; the token JSON is written to OUT.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRET = "client_secret_928579721954-vne1skg1sl3h0okds1dlo0e68vo24vn9.apps.googleusercontent.com.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
OUT = "dimonb-token-calendar.json"

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(OUT, "w") as f:
        f.write(creds.to_json())
    print(f"Wrote {OUT}")
