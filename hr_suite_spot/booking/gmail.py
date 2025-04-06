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
    

    def create_message_with_attachment(self, to, from_email, subject, body, file_path):
        message = MIMEMultipart()
        message['to'] = to
        message['from'] = from_email
        message['subject'] = subject

        # Add plain text part
        message.attach(MIMEText(body, 'plain'))

        # Add attachment
        if file_path is not None:
            with open(file_path, 'rb') as f:
                part = MIMEBase('application', 'pdf')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename='resume_guide.pdf')
                message.attach(part)

        # Encode to base64 for Gmail API
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return {'raw': raw}

    # Attachment to remain None until document uploading implemented
    def send_email(self, name: str, email: str, body: str, phone: str, attachment: Path=None):
        try:
            message = self.create_message_with_attachment('contact_submissions@hrsuitespot.com', 'cto@hrsuitespot.com', f'Contact From: {name} {phone} {email}', body, attachment)
            send_message = (self.service.users().messages().send(userId='me', body=message).execute())
        except HttpError as e:
            logger.error(f'An error occurred: {e}')
            send_message = None
        return send_message
            

    def _authorize(self):
        creds = service_account.Credentials.from_service_account_file(
                self.get_api_key_path.absolute(),
                scopes=self.SCOPES,
                subject=self.BUSINESS_EMAIL  # Impersonating the business email
            )
        return build("gmail", "v1", credentials=creds)

if __name__ == '__main__':
    pass