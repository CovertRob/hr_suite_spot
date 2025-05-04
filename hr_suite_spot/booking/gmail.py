from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import base64
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
import logging
import os

logger = logging.getLogger('__name__')

class GmailIntegration:

    SCOPES = ['https://mail.google.com/']

    BUSINESS_EMAIL = 'cto@hrsuitespot.com'

    def __init__(self):
        self._api_key_path = self._find_api_key()
        self.service = self._authorize()

    @property
    def get_api_key_path(self):
        return self._api_key_path


    @staticmethod
    def _find_api_key() -> str:
        """
        Since Credentials.from_service_acccount_file() takes file path, find the file path to either the environment variable in prod or local dev file.
        """
        api_key_path = os.getenv('SERVICE_ACCOUNT_FILE')
        # If none, then get local development key
        if not api_key_path:
            api_key_path = Path("./hr_suite_spot/booking/hr-suite-spot-8164bd363e86.json")
        return api_key_path
    

    def create_message(self, to, from_email, subject, body):
        message = MIMEMultipart()
        message['to'] = to
        message['from'] = from_email
        message['subject'] = subject

        # Add plain text part
        message.attach(MIMEText(body, 'plain'))

        # Encode to base64 for Gmail API
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw}

    # Attachment to remain None until document uploading implemented
    def send_email(self, name: str, email: str, body: str, phone: str):
        try:
            message = self.create_message('contact_submissions@hrsuitespot.com', 'cto@hrsuitespot.com', f'Contact From: {name} {phone} {email}', body)
            send_message = (self.service.users().messages().send(userId='me', body=message).execute())
        except HttpError as e:
            logger.error(f'An error occurred: {e}')
            send_message = None
        return send_message
            

    def _authorize(self):
        creds = service_account.Credentials.from_service_account_file(
                self.get_api_key_path,
                scopes=self.SCOPES,
                subject=self.BUSINESS_EMAIL  # Impersonating the business email
            )
        return build("gmail", "v1", credentials=creds)

if __name__ == '__main__':
    pass