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


logger = logging.getLogger('__name__')

# Path to your Service Account JSON key
SERVICE_ACCOUNT_FILE = Path("./booking/hr-suite-spot-8164bd363e86.json")

SCOPES = ['https://mail.google.com/']

BUSINESS_EMAIL = 'contact@hrsuitespot.com'

def create_message_with_attachment(to, from_email, subject, body, file_path):
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = from_email
    message['subject'] = subject

    # Add plain text part
    message.attach(MIMEText(body, 'plain'))

    # Add attachment
    with open(file_path, 'rb') as f:
        part = MIMEBase('application', 'pdf')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename='resume_guide.pdf')
        message.attach(part)

    # Encode to base64 for Gmail API
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}

def send_email():
    try:
        service = _authorize()
        message = create_message_with_attachment('rfsuzuki85@gmail.com', 'contact@hrsuitespot.com', 'Test', 'Test email via gmail API', Path('./static/products/salary_negotiation_guide.pdf'))
        send_message = (service.users().messages().send(userId='me', body=message).execute())
    except HttpError as e:
        logger.error(f'An error occurred: {e}')
        send_message = None
    return send_message
        

def _authorize():
    # print(SERVICE_ACCOUNT_FILE)
    creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE.absolute(),
            scopes=SCOPES,
            subject=BUSINESS_EMAIL  # Impersonating the business email
        )
    return build("gmail", "v1", credentials=creds)

if __name__ == '__main__':
    send_email()