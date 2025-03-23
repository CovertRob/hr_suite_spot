from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path
from typing import Dict, List
from uuid import uuid4
from pprint import pprint

# Path to your Service Account JSON key
SERVICE_ACCOUNT_FILE = Path("./booking/hr-suite-spot-8164bd363e86.json")

# The email of the business user you are impersonating
BUSINESS_EMAIL = "jasmin.scalli@hrsuitespot.com"

# Define the required scope
SCOPES = ["https://www.googleapis.com/auth/calendar"]

class BookingService:

    def __init__(self, guests: Dict[str, str], schedule: Dict[str, str]):
        guests = [{"email": email} for email in guests.values()]
        service = self._authorize()
        self.event_states = self._plan_event(guests, schedule, service)

    @staticmethod
    def _authorize():
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
            subject=BUSINESS_EMAIL  # Impersonating the business email
        )
        return build("calendar", "v3", credentials=creds)
    
    @staticmethod
    def _plan_event(attendees: List[Dict[str, str]], event_time, service: build):
        event = {"summary": "test meeting",
                 "start": {"dateTime": event_time["start"]},
                 "end": {"dateTime": event_time["end"]},
                 "attendees": attendees,
                 "conferenceData": 
                    {"createRequest": {"requestId": f"{uuid4().hex}", "conferenceSolutionKey": {"type": "hangoutsMeet"}}},
                 "reminders": {"useDefault": True}
                 }
        event = service.events().insert(calendarId=BUSINESS_EMAIL, sendNotifications=True, body=event, conferenceDataVersion=1).execute()

        return event


if __name__ == "__main__":
    plan = BookingService({"test_guest": "rfsuzuki85@gmail.com"}, {"start": "2025-03-24T16:00:00Z",
    "end": "2025-03-24T16:30:00Z"})
    pprint(plan.event_states)
