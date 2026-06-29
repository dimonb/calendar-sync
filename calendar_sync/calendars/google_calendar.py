import os
import logging
import uuid
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from calendar_sync.calendars.base import BaseCalendar

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']

@BaseCalendar.register
class GoogleCalendar(BaseCalendar):
    type = 'google'
    
    def __init__(self, cfg):
        super().__init__(cfg)
        self.id = cfg['id']
        self.credentials_path = cfg['credentials_path'] or '/app/credentials.json'
        self.token_path = cfg['token_path'] or '/app/token.json'
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None

        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    logger.info(f"Refreshing OAuth2 token for {self.id}...")
                    creds.refresh(Request())
                    # Save refreshed token
                    with open(self.token_path, 'w') as token_file:
                        token_file.write(creds.to_json())
            except Exception as e:
                logger.warning(f"Failed to refresh token for {self.id}: {str(e)}")
                creds = None

        if not creds or not creds.valid:
            # Running headless (service/cron): never fall back to an interactive
            # browser flow — it cannot work in a container and would crash the
            # whole sync. Fail loudly so a single bad token can be re-minted.
            raise RuntimeError(
                f"No valid OAuth2 credentials for {self.id}: token at {self.token_path} "
                f"is missing, expired or revoked. Re-mint it (see mint_token.py) and redeploy."
            )

        return build('calendar', 'v3', credentials=creds)

    def list_events(self, time_min, time_max):
        """Return a list of events"""
        events_result = self.service.events().list(
            calendarId=self.id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        results = []
        for event in events:
            results.append({
                'id': event['id'],
                'start': event['start'].get('dateTime', event['start'].get('date')),
                'end': event['end'].get('dateTime', event['end'].get('date')),
                'summary': event.get('summary', ''),
                'description': event.get('description', '')
            })
        return results

    def create_busy_event(self, start, end, source_event_id=None):
        """Create a Busy event"""
        event = {
            'summary': 'Busy',
            'description': f'Managed-by: calendar-sync (source {source_event_id})',
            'start': {'dateTime': start, 'timeZone': 'UTC'},
            'end': {'dateTime': end, 'timeZone': 'UTC'},
            'transparency': 'opaque'
        }
        target_cal = self.busy_calendar_id or self.id
        created_event = self.service.events().insert(calendarId=target_cal, body=event).execute()
        return created_event['id']

    def _delete(self, calendar_id, event_id):
        try:
            self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info(f"Deleted busy event {event_id} from {calendar_id}")
        except Exception:
            logger.exception(f"Failed to delete busy event {event_id} from {calendar_id}")

    def delete_event(self, event_id):
        """Delete a busy event (from the busy calendar if configured)."""
        self._delete(self.busy_calendar_id or self.id, event_id)

    def delete_main_event(self, event_id):
        """Delete an event from this calendar's own id (never the busy calendar)."""
        self._delete(self.id, event_id)