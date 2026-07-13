"""Outlook / Microsoft 365 calendar backend (Microsoft Graph API).

Delegated auth via MSAL: a token cache file (``token_path``) is minted once
interactively with ``mint_outlook_token.py`` and refreshed silently afterwards,
mirroring the Google backend's credentials/token split.

``credentials_path`` points to a small JSON with the Azure app registration:

    {"client_id": "...", "tenant_id": "...", "authority": "https://login.microsoftonline.com/<tenant_id>"}

``authority`` is optional and defaults to ``login.microsoftonline.com/<tenant_id>``.
"""
import json
import logging
import os
from datetime import timezone
from urllib.parse import quote

import msal
import requests
from dateutil import parser as date_parser

from calendar_sync.calendars.base import BaseCalendar

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Keep in sync with SCOPES in mint_outlook_token.py — the cached token must be
# acquired for the same scopes that acquire_token_silent requests here.
SCOPES = ["Calendars.ReadWrite"]


@BaseCalendar.register
class OutlookCalendar(BaseCalendar):
    type = 'outlook'

    def __init__(self, cfg):
        super().__init__(cfg)
        self.id = cfg['id']
        self.credentials_path = cfg['credentials_path']
        self.token_path = cfg['token_path']
        # Optional Graph calendar id to read from; default = the user's primary.
        self.graph_calendar_id = cfg.get('graph_calendar_id')
        # Optional Graph calendar id to write Busy events to; default = primary.
        self.busy_calendar_id = cfg.get('busy_calendar_id')

        with open(self.credentials_path) as fh:
            creds = json.load(fh)
        self.client_id = creds['client_id']
        authority = creds.get('authority') or (
            f"https://login.microsoftonline.com/{creds['tenant_id']}"
        )

        self._cache = msal.SerializableTokenCache()
        if os.path.exists(self.token_path):
            with open(self.token_path) as fh:
                self._cache.deserialize(fh.read())
        self._app = msal.PublicClientApplication(
            self.client_id, authority=authority, token_cache=self._cache
        )

    # -- auth ---------------------------------------------------------------
    def _save_cache(self):
        if self._cache.has_state_changed:
            with open(self.token_path, 'w') as fh:
                fh.write(self._cache.serialize())

    def _token(self):
        accounts = self._app.get_accounts()
        if not accounts:
            raise RuntimeError(
                f"No cached Outlook account for {self.id}; "
                f"run mint_outlook_token.py to authorize and create {self.token_path}"
            )
        result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
        self._save_cache()
        if not result or 'access_token' not in result:
            raise RuntimeError(
                f"Failed to acquire Outlook token for {self.id}: {result}. "
                f"The refresh token may have expired — re-run mint_outlook_token.py"
            )
        return result['access_token']

    def _headers(self, extra=None):
        headers = {
            'Authorization': f'Bearer {self._token()}',
            'Prefer': 'outlook.timezone="UTC"',
        }
        if extra:
            headers.update(extra)
        return headers

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _to_iso(graph_dt):
        """Convert a Graph dateTimeTimeZone into an ISO string (UTC)."""
        dt = date_parser.isoparse(graph_dt['dateTime'])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _graph_dt(value):
        """Normalize an ISO string into Graph's naive-UTC dateTime form."""
        dt = date_parser.isoparse(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S')

    def _events_path(self, calendar_id):
        """events collection for create/list, scoped to a calendar when given."""
        if calendar_id:
            return f"{GRAPH_BASE}/me/calendars/{quote(calendar_id, safe='')}"
        return f"{GRAPH_BASE}/me"

    # -- API ----------------------------------------------------------------
    def list_events(self, time_min, time_max):
        """Return expanded event instances in the configured time window."""
        url = f"{self._events_path(self.graph_calendar_id)}/calendarView"
        params = {
            'startDateTime': time_min,
            'endDateTime': time_max,
            '$select': 'id,subject,start,end,body,isAllDay,isCancelled',
            '$orderby': 'start/dateTime',
            '$top': 250,
        }
        results = []
        while url:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for ev in data.get('value', []):
                if ev.get('isCancelled'):
                    continue
                if ev.get('isAllDay'):
                    # Match the Google backend: emit a date-only string so the
                    # sync loop's "no 'T'" check skips all-day events.
                    start = date_parser.isoparse(ev['start']['dateTime']).date().isoformat()
                    end = date_parser.isoparse(ev['end']['dateTime']).date().isoformat()
                else:
                    start = self._to_iso(ev['start'])
                    end = self._to_iso(ev['end'])
                results.append({
                    'id': ev['id'],
                    'start': start,
                    'end': end,
                    'summary': ev.get('subject', '') or '',
                    'description': (ev.get('body') or {}).get('content', '') or '',
                })
            url = data.get('@odata.nextLink')
            params = None  # nextLink already carries the query
        return results

    def create_busy_event(self, start, end, source_event_id=None):
        """Create a Busy event (on the busy calendar if configured)."""
        url = f"{self._events_path(self.busy_calendar_id)}/events"
        body = {
            'subject': 'Busy',
            'body': {
                'contentType': 'text',
                'content': f'Managed-by: calendar-sync (source {source_event_id})',
            },
            'start': {'dateTime': self._graph_dt(start), 'timeZone': 'UTC'},
            'end': {'dateTime': self._graph_dt(end), 'timeZone': 'UTC'},
            'showAs': 'busy',
            'isReminderOn': False,
        }
        resp = requests.post(
            url,
            headers=self._headers({'Content-Type': 'application/json'}),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()['id']

    def delete_event(self, event_id):
        """Delete an event by id.

        Graph event ids are unique within the mailbox, so deletion works
        regardless of which calendar the event lives on. That also makes the
        base ``delete_main_event`` (which defers to this) correct for Outlook.
        """
        url = f"{GRAPH_BASE}/me/events/{quote(event_id, safe='')}"
        try:
            resp = requests.delete(url, headers=self._headers(), timeout=30)
            if resp.status_code not in (204, 404):
                resp.raise_for_status()
            logger.info(f"Deleted busy event {event_id}")
        except Exception:
            logger.exception(f"Failed to delete busy event {event_id}")
