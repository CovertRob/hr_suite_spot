from typing import Dict
import os
from pathlib import Path
import json
from flask import Flask, jsonify
import stripe

class StripeProcessor:
    
    def __init__(self, app: Flask, price_id: str):
        # Set domain for either prod or local dev
        self.domain = app.config['DOMAIN']

    def find_api_key(self) -> str:
        api_key = os.getenv('STRIPE_API_KEY')
        # If none, then get local development key
        if not api_key:
            try:
                api_key_path = Path("./booking/stripe_test_api_key.json")
                with open(api_key_path, 'r') as file:
                    data = json.load(file)
                api_key = data.get("STRIPE_API_KEY")
                if not api_key:
                    raise ValueError(f"ERROR: STRIPE_API_KEY not found in {api_key_path}")
            except FileNotFoundError:
                 raise FileNotFoundError(f"ERROR: API key path not found!")
            except json.JSONDecodeError:
                raise ValueError(f"ERROR: Invalid JSON format in API key file!")
        return api_key



    def create_checkout_session(self, price_id: str, quantity: int, customer_info: Dict[str, str]):
        try:
            session = stripe.checkout.Session.create(
                ui_mode='embedded',
                line_items=[
                    {
                        # Provide the exact Price ID (for example, pr_1234) of the product you want to sell
                        'price': price_id,
                        'quantity': quantity
                    },
                ],
                mode='payment',
                return_url=self.domain + '/return?session_id={CHECKOUT_SESSION_ID}',
                metadata={
                    'customer_info': customer_info
                }
            )
        except Exception as e:
            return str(e)
        return jsonify(clientSecret=session.client_secret)