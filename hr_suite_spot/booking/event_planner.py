from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from uuid import uuid4
from typing import Dict, List
from google.oauth2.credentials import Credentials
from pprint import pprint


class EventPlanner:

    def __init__(self, guests: Dict[str, str], schedule: Dict[str, str]):
        guests = [{"email": email} for email in guests.values()]
        service = self._authorize()
        self.event_states = self._plan_event(guests, schedule, service)

    @staticmethod
    def _authorize():
        scopes = ["https://www.googleapis.com/auth/calendar"]
        credentials = None
        token_file = Path("./token.json")

        if token_file.exists():
            with open(token_file, "rb") as token:
                credentials = Credentials.from_authorized_user_file("token.json", scopes)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file("/home/robert_feconda/web_projects/hr_suite_spot/hr_suite_spot/booking/credentials.json", scopes)

                credentials = flow.run_local_server(ost="localhost", open_browser=False, port=5003) # For development environment

            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(credentials.to_json())
        
        calendar_service = build("calendar", "v3", credentials=credentials)

        return calendar_service

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
        event = service.events().insert(calendarId="primary", sendNotifications=True, body=event, conferenceDataVersion=1).execute()

        return event


if __name__ == "__main__":
    plan = EventPlanner({"test_guest": "test.guest@gmail.com"}, {"start": "2020-07-31T16:00:00Z",
    "end": "2020-07-31T16:30:00Z"})
    pprint(plan.event_states)