from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path
from typing import Dict, List
from uuid import uuid4
from pprint import pprint
from googleapiclient.http import HttpRequest, _retry_request, HttpError
import logging
import urllib
import os
import json

logger = logging.getLogger(__name__)

# The email of the business user you are impersonating
BUSINESS_EMAIL = "noreply@hrsuitespot.com"

# Define the required scope
SCOPES = ["https://www.googleapis.com/auth/calendar"]

class BookingService:

    def __init__(self, guests: Dict[str, str], schedule: Dict[str, str], meeting_name: str):
        guests = [{"email": email} for email in guests.values()]
        self.service = self._authorize()
        self.event_states = self._plan_event(guests, schedule, self.service, meeting_name)
    
    @staticmethod
    def _find_api_key() -> str:
        """
        Since Credentials.from_service_acccount_file() takes file path, find the file path to either the environment variable in prod or local dev file.
        """
        api_key_path = os.getenv('SERVICE_ACCOUNT_FILE')
        # If none, then get local development key
        if not api_key_path:
            api_key_path = Path("./booking/hr-suite-spot-8164bd363e86.json")
        return api_key_path

    @staticmethod
    def _authorize():
        creds = service_account.Credentials.from_service_account_file(
            BookingService._find_api_key(),
            scopes=SCOPES,
            subject=BUSINESS_EMAIL  # Impersonating the business email
        )
        return build("calendar", "v3", credentials=creds, requestBuilder=CustomHttpRequest)
    # catch exception from build if needed
    
    @staticmethod
    def _plan_event(attendees: List[Dict[str, str]], event_time, service: build, meeting_name):
        event = {"summary": f"{meeting_name}",
                 "start": {"dateTime": event_time["start"]},
                 "end": {"dateTime": event_time["end"]},
                 "attendees": attendees,
                 "conferenceData": 
                    {"createRequest": {"requestId": f"{uuid4().hex}", "conferenceSolutionKey": {"type": "hangoutsMeet"}}},
                 "reminders": {"useDefault": True}
                 }
        event = service.events().insert(calendarId=BUSINESS_EMAIL, sendNotifications=True, body=event, conferenceDataVersion=1).execute()

        return event

class CustomHttpRequest(HttpRequest):
    "Custom request class to intercept HTTP response details because API client only returns serialized JSON response."

    MAX_URI_LENGTH = 2048

    def execute(self, http=None, num_retries=0):
        """Execute the request.

        Args:
          http: httplib2.Http, an http object to be used in place of the
                one the HttpRequest request object was constructed with.
          num_retries: Integer, number of times to retry with randomized
                exponential backoff. If all retries fail, the raised HttpError
                represents the last request. If zero (default), we attempt the
                request only once.

        Returns:
          A deserialized object model of the response body as determined
          by the postproc.

        Raises:
          googleapiclient.errors.HttpError if the response was not a 2xx.
          httplib2.HttpLib2Error if a transport error has occurred.
        """
        if http is None:
            http = self.http

        if self.resumable:
            body = None
            while body is None:
                _, body = self.next_chunk(http=http, num_retries=num_retries)
            return body

        # Non-resumable case.

        if "content-length" not in self.headers:
            self.headers["content-length"] = str(self.body_size)
        # If the request URI is too long then turn it into a POST request.
        # Assume that a GET request never contains a request body.
        if len(self.uri) > self.MAX_URI_LENGTH and self.method == "GET":
            self.method = "POST"
            self.headers["x-http-method-override"] = "GET"
            self.headers["content-type"] = "application/x-www-form-urlencoded"
            parsed = urllib.parse.urlparse(self.uri)
            self.uri = urllib.parse.urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, None, None)
            )
            self.body = parsed.query
            self.headers["content-length"] = str(len(self.body))

        # Handle retries for server-side errors.
        resp, content = _retry_request(
            http,
            num_retries,
            "request",
            self._sleep,
            self._rand,
            str(self.uri),
            method=str(self.method),
            body=self.body,
            headers=self.headers,
        )

        for callback in self.response_callbacks:
            callback(resp)
        logger.info(f"HTTP Response code: {resp.status}")
        if resp.status >= 300:
            raise HttpError(resp, content, uri=self.uri)
        return self.postproc(resp, content)

if __name__ == "__main__":
    plan = BookingService({"test_guest": "rfsuzuki85@gmail.com"}, {"start": "2025-03-24T16:00:00Z",
    "end": "2025-03-24T16:30:00Z"})
    pprint(plan.event_states)
