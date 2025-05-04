from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from pathlib import Path
from datetime import datetime
import logging
import os
from pprint import pprint

logger = logging.getLogger(__name__)

# The email of the business user you are impersonating
BUSINESS_EMAIL = "noreply@hrsuitespot.com"

# Define the required scope
SCOPES = ["https://www.googleapis.com/auth/drive"]

class DriveIntegration:

    def __init__(self):
        self.service = self._authorize()
        
    
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

    @staticmethod
    def _authorize():
        creds = service_account.Credentials.from_service_account_file(
            DriveIntegration._find_api_key(),
            scopes=SCOPES,
            subject=BUSINESS_EMAIL  # Impersonating the business email
        )
        return build("drive", "v3", credentials=creds)
    # catch exception from build if needed

    def upload_file(self, uploaded_file, safe_uploaded_filename, user_name):
        # Metadata for upload
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        timestamped_name = f"{timestamp}_{user_name}_{safe_uploaded_filename}"
        file_metadata = {
            "name": timestamped_name,
            "parents": ["0AKmI6mVHxZHJUk9PVA"]
        }

        # In-memory stream upload
        media = MediaIoBaseUpload(uploaded_file.stream, mimetype='application/pdf')

        uploaded = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True # Must include to access shared drives
        ).execute()

        file_id = uploaded.get("id")
        pprint(uploaded)
        return True, f"https://drive.google.com/file/d/{file_id}/view"

if __name__ == "__main__":
    pass
