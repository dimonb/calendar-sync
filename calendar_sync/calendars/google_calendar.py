import os
import logging
import uuid
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
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
            logger.info(f"Starting new OAuth2 flow for {self.id}...")
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(self.token_path, 'w') as token_file:
                token_file.write(creds.to_json())

        return build('calendar', 'v3', credentials=creds)

    def list_events(self, time_min, time_max):
        """Вернуть список событий"""
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
                'summary': event.get('summary', '')
            })
        return results

    def create_busy_event(self, start, end, source_event_id=None):
        """Создать событие типа Busy"""
        event = {
            'summary': 'Busy',
            'description': f'Managed-by: calendar-sync (source {source_event_id})',
            'start': {'dateTime': start, 'timeZone': 'UTC'},
            'end': {'dateTime': end, 'timeZone': 'UTC'},
            'transparency': 'opaque'
        }
        created_event = self.service.events().insert(calendarId=self.id, body=event).execute()
        return created_event['id']

    def delete_event(self, event_id):
        """Удалить событие по его ID"""
        try:
            self.service.events().delete(calendarId=self.id, eventId=event_id).execute()
            logger.info(f"Deleted busy event {event_id}")
        except Exception:
            logger.exception(f"Failed to delete busy event {event_id}")