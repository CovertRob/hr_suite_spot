from math import e
from flask.config import T
from mailchimp_marketing import Client
import mailchimp_marketing as MailchimpMarketing
from mailchimp_marketing.api_client import ApiClientError
from pathlib import Path
import os
import json
from hashlib import md5 # Used for subscriber email
import logging
from typing import Dict

logger = logging.getLogger(__file__)

MC_JOURNEYS = {'resume_guide': 'Test-Resume Guide'} # Update this upon push to prod
AUDIENCE_ID = '2b11290018' # This is a unique identifier for the list, will need to change for official HRSS audience upon push to prod

# Current implementation: functions don't return response objects at this time. Won't catch the responses until caching is implemented.

class MailChimpIntegration:
    """
    May raise the following errors upon instantiation:
        ValueError(f"ERROR: Mailchimp API key not found in {api_key_path}")
        FileNotFoundError(f"ERROR: API key path not found!")
        json.JSONDecodeError: raise ValueError(f"ERROR: Invalid JSON format in API key file!")
    """
     
    def __init__(self):
        self._mailchimp = Client()
        self._api_key = self._find_api_key()
        self._mailchimp.set_config({
            "api_key": self._api_key,
            "server": "us13"})
        

    @property
    def get_api_key(self):
        return self._api_key

    @property
    def get_client(self):
        return self._mailchimp

    def _find_api_key(self) -> str:
        """
        Store Stripe API key directly in environment variable for easy access.
        Otherwise, find via file name in local dev environment.
        """
        api_key = os.getenv('STRIPE_API_KEY')
            # If none, then get local development key
        if not api_key:
            try:
                api_key_path = Path("./booking/mailchimp.json")
                with open(api_key_path, 'r') as file:
                    data = json.load(file)
                    api_key = data.get("api_key")
                if not api_key:
                    raise ValueError(f"ERROR: Mailchimp API key not found in {api_key_path}")
            except FileNotFoundError:
                raise FileNotFoundError(f"ERROR: API key path not found!")
            except json.JSONDecodeError:
                raise ValueError(f"ERROR: Invalid JSON format in API key file!")
        
        return api_key

    def _add_member_without_tags(self, list_id: str, email: str, subscription_status: str):
        """
        Adds or updates member to the specified list/audience. Will overwrite fields provided. Use PATCH for single field updates. Use POST for tag submissions or updates.

        Must use separate member submission/tag submission to avoid extra API calls of checking if member exists or not already.

        Adding member with a tag will automatically trigger MailChimp journey associated with it.
        Subscription_status should be "subscribed".

        Route: PUT /lists/{list_id}/members/{subscriber_hash}
               Add if not exists, or update fully if exists
               Overwrites the fields supplied
               Idempotent - safe to call repeatedly

        Mailchimp Returns: HTTP Status 200 - List Members, Individuals who are currently or have been previously subscribed to this list, including members who have been bounced or unsubscribed.
        """
        try:
            subscriber_hash = md5(email.encode('utf-8').lower()).hexdigest()
            response = self.get_client.lists.set_list_member(list_id, subscriber_hash, {"email_address": email, "status_if_new": subscription_status})
            logger.info(f"Mailchimp API response: {response}")
        except ApiClientError as error:
            logger.error(f"Error: {error.text}")
            raise

    def _add_tag_to_member(self, list_id: str, email: str, tag: str):
        """
        Adds a tag to a member after they have been added to a list/audience.
        
        Route: POST /lists/{list_id}/members/{subscriber_hash}/tags

        MailChimp Return: HTTP 204
        """
        try:
            subscriber_hash = md5(email.encode('utf-8').lower()).hexdigest()
            response = self.get_client.lists.update_list_member_tags(list_id, subscriber_hash, {"tags": [{"name": tag, "status": "active"}]})
            logger.info(f"Mailchimp API response: {response}")
        except ApiClientError as error:
            logger.error(f"Error: {error.text}")
            raise
            

    def _update_member(self, list_id: str, email: str, **kwargs):
        """
        Used to update single field in member info. Only include via kwarg the fields you want to update. Email address is required since the actual required paramater is an MD5 hash of it.

        Available fields:
            email_address: str,
            email_type: str,
            status: str values = susbcribed, unsubscribed, cleaned, pending
            merge_fields: object,
            interests: object,
            language: str,
            vip: bool,
            location: object,
            marketing_permissions: object[],
            ip_signup: str,
            timestamp_signup: str,
            ip_opt: str,
            timestamp_opt: str
        
        Route: PATCH /lists/{list_id}/members/{subscriber_hash}

        Mailchimp Returns: HTTP Status 200 - List Members
        """
        try:
            subscriber_hash = md5(email.encode('utf-8').lower()).hexdigest()
            response = self.get_client.lists.update_list_member(list_id, subscriber_hash, {**kwargs})
            logger.info(f"Mailchimp response: {response}")
        except ApiClientError as error:
            logger.error(f"Error: {error.text}")
            raise


    def submit_member_to_mailchimp(self, email, product_key: str=None):
        """
        Submit a user to MailChimp audience. If tags are included, adds tags to trigger the associated journey & product delivery.

        Product key can only be the following:
        'resume_guide' (currently for testing)
        'Q&A_guide'

        """
        try:
            # PUT to list. This method is idempotic.
            self._add_member_without_tags(AUDIENCE_ID, email, "subscribed")
            # If tags present, POST tag to member
            if product_key:
                tag_name = MC_JOURNEYS.get(product_key)
                self._add_tag_to_member(AUDIENCE_ID, email, tag_name)
        except ApiClientError as e:
            logger.error(f"An error occurred submitting member to mailchimp: {e.text}")
            return False
        return True
        
if __name__ == '__main__':
    # For test ping:
    mailchimp = MailChimpIntegration().get_client
    response = mailchimp.ping.get()
    print(response)