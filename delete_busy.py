#!/usr/bin/env python3
"""Delete managed Busy events in ebac primary over +/-5 years, monthly batches."""
import sys
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CAL = "dmitrii.balabanov@ebaconline.com.br"
MARKER = "Managed-by: calendar-sync"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

creds = Credentials.from_authorized_user_file("dimonb-token-calendar.json", SCOPES)
svc = build("calendar", "v3", credentials=creds)


def month_bounds(year, month):
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


now = datetime.now(timezone.utc)
cur = now.year * 12 + (now.month - 1)
total_deleted = 0
total_unmarked = 0
total_failed = 0

# Walk outward from the current month in both directions:
# 0, +1, -1, +2, -2, ... up to +/-60 months.
offsets = [0]
for d in range(1, 61):
    offsets.append(d)
    offsets.append(-d)

for off in offsets:
    ym = cur + off
    y, m = ym // 12, ym % 12 + 1
    tmin, tmax = month_bounds(y, m)
    deleted = 0
    unmarked = 0
    page = None
    while True:
        resp = svc.events().list(
            calendarId=CAL, timeMin=tmin.isoformat(), timeMax=tmax.isoformat(),
            singleEvents=True, maxResults=2500, pageToken=page,
        ).execute()
        for e in resp.get("items", []):
            summ = (e.get("summary") or "").strip().lower()
            if summ == "busy":
                try:
                    svc.events().delete(calendarId=CAL, eventId=e["id"]).execute()
                    deleted += 1
                except Exception as ex:
                    total_failed += 1
                    print(f"  FAIL delete {e['id']}: {ex}", flush=True)
        page = resp.get("nextPageToken")
        if not page:
            break
    total_deleted += deleted
    if deleted:
        print(f"{y}-{m:02d}: deleted {deleted} Busy events", flush=True)

print(f"=== TOTAL deleted Busy events: {total_deleted} | failures: {total_failed} ===", flush=True)
