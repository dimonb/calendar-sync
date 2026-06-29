"""Exchange Online calendar backend via EWS (Exchange Web Services).

This is the CA-survivable sibling of :mod:`outlook_calendar` (Microsoft Graph).
For tenants whose Conditional Access blocks Graph on unmanaged devices, the
Exchange Online *resource* (``outlook.office365.com``) may still be reachable —
the same door Apple's native macOS Calendar uses (EWS + modern-auth OAuth).

Auth mirrors the Outlook/Graph backend: an MSAL token cache (``token_path``) is
minted once interactively (``mint_ews_token.py`` or ``mint_ews_from_apple.py``)
and refreshed silently afterwards. The cached token must be acquired for the EWS
scope below, against a *public* client that can obtain it (Apple's own client, or
a localhost-capable first-party client such as Azure CLI).

``credentials_path`` points to a small JSON:

    {
      "client_id": "...",                       # the public client used to mint
      "primary_smtp_address": "user@tenant",    # the mailbox to open (DELEGATE)
      "authority": "https://login.microsoftonline.com/organizations",  # or tenant GUID
      "ews_endpoint": "https://outlook.office365.com/EWS/Exchange.asmx" # optional
    }

⚠️ EWS in Exchange Online is being retired (disabled from ~Oct 2026, fully
Apr 2027). This backend is a stopgap for write access where Graph is CA-blocked.
"""
import json
import logging
import os
from datetime import timezone

import msal
from dateutil import parser as date_parser
from oauthlib.oauth2 import OAuth2Token

from exchangelib import (
    DELEGATE,
    OAUTH2,
    Account,
    CalendarItem,
    Configuration,
    EWSDateTime,
    EWSTimeZone,
    OAuth2AuthorizationCodeCredentials,
)
from exchangelib.errors import ErrorItemNotFound
from exchangelib.items import SEND_TO_NONE

from calendar_sync.calendars.base import BaseCalendar

logger = logging.getLogger(__name__)

EWS_ENDPOINT = "https://outlook.office365.com/EWS/Exchange.asmx"
# exchangelib's EWSDateTime.astimezone() only accepts an EWSTimeZone (not stdlib
# datetime.timezone.utc), so use this for all EWSDateTime tz conversions.
_UTC = EWSTimeZone("UTC")
# Keep in sync with the SCOPE used by the mint scripts — acquire_token_silent
# must request the same scope the cached refresh token was minted for.
SCOPES = ["https://outlook.office365.com/EWS.AccessAsUser.All"]


@BaseCalendar.register
class ExchangeCalendar(BaseCalendar):
    type = 'exchange'

    def __init__(self, cfg):
        super().__init__(cfg)
        self.id = cfg['id']
        self.credentials_path = cfg['credentials_path']
        self.token_path = cfg['token_path']
        # Optional display name of a Calendar *subfolder* to read from; default =
        # the mailbox's primary calendar. (The EWS analogue of graph_calendar_id.)
        self.calendar_name = cfg.get('calendar_name')

        with open(self.credentials_path) as fh:
            creds = json.load(fh)
        self.client_id = creds['client_id']
        self.primary_smtp = creds['primary_smtp_address']
        self.ews_endpoint = creds.get('ews_endpoint', EWS_ENDPOINT)
        authority = creds.get('authority') or (
            f"https://login.microsoftonline.com/{creds.get('tenant_id', 'organizations')}"
        )

        self._cache = msal.SerializableTokenCache()
        if os.path.exists(self.token_path):
            with open(self.token_path) as fh:
                self._cache.deserialize(fh.read())
        self._app = msal.PublicClientApplication(
            self.client_id, authority=authority, token_cache=self._cache
        )
        self._account = None  # lazily built exchangelib Account (per process run)

    # -- auth ---------------------------------------------------------------
    def _save_cache(self):
        if self._cache.has_state_changed:
            with open(self.token_path, 'w') as fh:
                fh.write(self._cache.serialize())

    def _token(self):
        accounts = self._app.get_accounts()
        if not accounts:
            raise RuntimeError(
                f"No cached Exchange account for {self.id}; "
                f"run mint_ews_token.py to authorize and create {self.token_path}"
            )
        result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
        self._save_cache()
        if not result or 'access_token' not in result:
            raise RuntimeError(
                f"Failed to acquire EWS token for {self.id}: {result}. "
                f"The refresh token may have expired — re-run mint_ews_token.py"
            )
        return result

    def account(self):
        """Build (once per run) an exchangelib Account on a fresh access token.

        Sync runs are short-lived, so a token minted at the start of the run
        outlives it; MSAL handles refresh-token rotation across runs in the cache.
        """
        if self._account is None:
            tok = self._token()
            credentials = OAuth2AuthorizationCodeCredentials(
                access_token=OAuth2Token({
                    'access_token': tok['access_token'],
                    'token_type': 'Bearer',
                    'expires_in': tok.get('expires_in', 3599),
                })
            )
            config = Configuration(
                service_endpoint=self.ews_endpoint,
                credentials=credentials,
                auth_type=OAUTH2,
            )
            self._account = Account(
                primary_smtp_address=self.primary_smtp,
                config=config,
                access_type=DELEGATE,
                autodiscover=False,
            )
        return self._account

    # -- helpers ------------------------------------------------------------
    def _read_folder(self):
        account = self.account()
        return self._folder_by_name(account, self.calendar_name)

    def _busy_folder(self):
        account = self.account()
        return self._folder_by_name(account, self.busy_calendar_id)

    @staticmethod
    def _folder_by_name(account, name):
        if not name:
            return account.calendar
        for folder in account.calendar.children:
            if folder.name == name:
                return folder
        raise RuntimeError(f"Calendar subfolder '{name}' not found under primary calendar")

    @staticmethod
    def _ews_dt(value):
        """Parse an ISO string into a UTC-aware EWSDateTime for view() bounds."""
        dt = date_parser.isoparse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return EWSDateTime.from_datetime(dt.astimezone(timezone.utc)).astimezone(_UTC)

    @staticmethod
    def _to_iso(dt):
        """Format an EWSDateTime as an ISO-8601 UTC string (with 'T')."""
        return dt.astimezone(_UTC).isoformat()

    # -- API ----------------------------------------------------------------
    def list_events(self, time_min, time_max):
        """Return expanded event instances in the window (matches Graph backend)."""
        folder = self._read_folder()
        results = []
        # view() expands recurring masters into individual occurrences, like Graph's
        # calendarView. .only() trims the SOAP payload to the fields we map.
        items = folder.view(start=self._ews_dt(time_min), end=self._ews_dt(time_max))
        for ev in items.only(
            'id', 'subject', 'start', 'end', 'is_all_day', 'is_cancelled', 'body'
        ):
            if getattr(ev, 'is_cancelled', False):
                continue
            if getattr(ev, 'is_all_day', False):
                # Emit date-only strings so the sync loop's "no 'T'" check skips
                # all-day events, mirroring the Graph/Google backends.
                start = ev.start.date().isoformat() if hasattr(ev.start, 'date') else str(ev.start)
                end = ev.end.date().isoformat() if hasattr(ev.end, 'date') else str(ev.end)
            else:
                start = self._to_iso(ev.start)
                end = self._to_iso(ev.end)
            results.append({
                'id': ev.id,
                'start': start,
                'end': end,
                'summary': ev.subject or '',
                'description': str(ev.body) if ev.body else '',
            })
        return results

    def create_busy_event(self, start, end, source_event_id=None):
        """Create a Busy event (on the busy subfolder if configured)."""
        folder = self._busy_folder()
        item = CalendarItem(
            account=self.account(),
            folder=folder,
            subject='Busy',
            body=f'Managed-by: calendar-sync (source {source_event_id})',
            start=self._ews_dt(start),
            end=self._ews_dt(end),
            legacy_free_busy_status='Busy',
            reminder_is_set=False,
        )
        item.save(send_meeting_invitations=SEND_TO_NONE)
        return item.id

    def delete_event(self, event_id):
        """Delete an event by id.

        EWS ItemIds are unique within the mailbox, so deletion works regardless of
        which calendar folder the event lives on — the base ``delete_main_event``
        (which defers here) is therefore correct for Exchange too. ChangeKey is
        omitted (passed as None); EXO does not require it for DeleteItem.
        """
        account = self.account()
        try:
            account.bulk_delete(
                [(event_id, None)],
                send_meeting_cancellations=SEND_TO_NONE,
            )
            logger.info(f"Deleted busy event {event_id}")
        except ErrorItemNotFound:
            logger.info(f"Busy event {event_id} already gone")
        except Exception:
            logger.exception(f"Failed to delete busy event {event_id}")
