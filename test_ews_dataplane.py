#!/usr/bin/env python3
"""Prove the EWS data plane end-to-end with the minted token.

Mirrors ExchangeCalendar.account()/list_events()/create_busy_event()/delete_event()
but standalone (no calendar_sync package deps), so it runs in the auth venv:

    .venv-auth/bin/python test_ews_dataplane.py

Reads exchange_client.json + the MSAL cache, then: counts events in the next 2
days, creates a throwaway Busy event, and deletes it. If all three succeed, the
ExchangeCalendar backend will work.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import msal
from oauthlib.oauth2 import OAuth2Token

from exchangelib import (
    DELEGATE,
    OAUTH2,
    Account,
    CalendarItem,
    Configuration,
    EWSDateTime,
    OAuth2AuthorizationCodeCredentials,
)
from exchangelib.items import SEND_TO_NONE

CREDS = os.environ.get("CREDS_OUT", "exchange_client.json")
TOKEN = os.environ.get("OUT", "dimonb-token-outlook-ews.json")
SCOPES = ["https://outlook.office365.com/EWS.AccessAsUser.All"]


def main():
    creds = json.load(open(CREDS))
    cache = msal.SerializableTokenCache()
    cache.deserialize(open(TOKEN).read())
    app = msal.PublicClientApplication(
        creds["client_id"], authority=creds["authority"], token_cache=cache
    )
    accts = app.get_accounts()
    assert accts, "no cached account; run a mint script first"
    tok = app.acquire_token_silent(SCOPES, account=accts[0])
    assert tok and "access_token" in tok, f"silent token failed: {tok}"
    if cache.has_state_changed:
        open(TOKEN, "w").write(cache.serialize())
    print(f"✅ silent token OK (expires_in={tok.get('expires_in')})")

    credentials = OAuth2AuthorizationCodeCredentials(
        access_token=OAuth2Token({"access_token": tok["access_token"], "token_type": "Bearer"})
    )
    config = Configuration(
        service_endpoint=creds.get("ews_endpoint", "https://outlook.office365.com/EWS/Exchange.asmx"),
        credentials=credentials,
        auth_type=OAUTH2,
    )
    account = Account(
        primary_smtp_address=creds["primary_smtp_address"],
        config=config,
        access_type=DELEGATE,
        autodiscover=False,
    )
    print(f"✅ connected to mailbox {creds['primary_smtp_address']} via EWS")

    now = datetime.now(timezone.utc)
    start = EWSDateTime.from_datetime(now)
    end = EWSDateTime.from_datetime(now + timedelta(days=2))
    n = account.calendar.view(start=start, end=end).only("id", "start", "end").count()
    print(f"✅ READ: {n} event instance(s) in the next 2 days")

    # create
    s = EWSDateTime.from_datetime((now + timedelta(days=1)).replace(microsecond=0))
    e = EWSDateTime.from_datetime((now + timedelta(days=1, minutes=15)).replace(microsecond=0))
    item = CalendarItem(
        account=account,
        folder=account.calendar,
        subject="Busy",
        body="Managed-by: calendar-sync (dataplane-test)",
        start=s,
        end=e,
        legacy_free_busy_status="Busy",
        reminder_is_set=False,
    )
    item.save(send_meeting_invitations=SEND_TO_NONE)
    print(f"✅ WRITE: created test Busy event id={item.id[:32]}...")

    # delete (by id, changekey omitted)
    account.bulk_delete([(item.id, None)], send_meeting_cancellations=SEND_TO_NONE)
    print("✅ DELETE: removed test Busy event")
    print("\n🎉 EWS data plane fully working (read + create + delete).")


if __name__ == "__main__":
    main()
