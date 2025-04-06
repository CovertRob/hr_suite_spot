from datetime import timedelta, datetime
import json
import logging
import os
from uuid import UUID, uuid4
from flask import Flask, render_template, request, flash, redirect, g, url_for, jsonify
import secrets
from flask_debugtoolbar import DebugToolbarExtension
from hr_suite_spot.booking import database, error_utils, booking_service, stripe_integration, mailchimp_integration, gmail
from hr_suite_spot.booking import booking_utils as util
from functools import wraps
from werkzeug.datastructures import MultiDict
from json import dumps
from googleapiclient.http import HttpError
import stripe
from stripe import SignatureVerificationError
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import re
from pprint import pprint
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32) #256 bit
    app.config['SECRET_KEY'] = app.secret_key
    if os.environ.get('FLASK_ENV') == 'production':
        app.config['DOMAIN'] = 'https://www.hrsuitespot.com'
    else:
        app.config['DOMAIN'] = 'http://localhost:5003'
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False  # Prevents redirect issues
    return app

app = create_app()
# Set to make Flask debug toolbar work
if not os.environ.get('FLASK_ENV') == 'production':
    app.debug=True
auth = HTTPBasicAuth()


# Must set this in prod
prod_hash = os.getenv('HASH_ADMIN')

if prod_hash:
    users = {
        "admin": generate_password_hash(prod_hash)
    }
else: # For dev
    users = {
        "admin": generate_password_hash('secret')
    }

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# Static Stripe price-id's (short-term fix):
# To add config file for this later
STRIPE_PRICE_IDS = {"coaching_call": "price_1R6LuhH8d4CYhArR8yogdHvb",
                    "salary_guide": "price_1R91kAH8d4CYhArRjcIkKXvy"}

# Use decorator to create g.db instance within request context window for functions that require it to conserve resources and prevent N +1 instances
def instantiate_database(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.db = database.DatabasePersistence()
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return redirect('/index')

# Landing page
@app.route("/index")
def index():
    title = "HR Suite Spot"
    # return render_template('index_2.html', title = title)
    return render_template('index_2.html', title = title)

# Description page about User
@app.route("/about")
def get_about():
    return render_template('about.html')

# General overview of each service provided and provide links to book coaching calls/purchase products
@app.route("/resources")
def get_resources():
    return render_template('resources.html')

# General contact page. Should include address for company and contact information to include an email.
# Also include a contact me form submisson for general inquiries
@app.route("/contact")
def get_contact():
    return render_template('contact.html')


# Admin page for user to submit their availability to the system for appointments to be booked against.
@app.route("/calendar-availability", methods=['GET'])
@auth.login_required
def get_calendar():
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return render_template('calendar.html', days_of_week=days_of_week)

# This route only to be used by admin
# Look into protecting with secret key
@app.route("/calendar", methods=["POST"])
@instantiate_database
def submit_availability():
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    user_timezone = request.form.get('timezone')
    pprint(user_timezone)
    # Separate out availability period data so the "re-occurring" boolean values don't mess with time format validation functions
    availability_data = MultiDict()
    for k, v in request.form.items(multi=True):
        if k in days_of_week:
            availability_data.add(k, v)
    # Separate out name:value pairs from form submission. Note that javascript on the front end removes the hidden "false" submission if true is checked
    reoccurring_data = {k: v for k, v in request.form.items() if "repeat" in k}
    # Need to check / sanitize input here, create util function
    # Currently only implementing one main avail period per day
    
    # With MultiDict type, use getlist to create a list for each day of the week with the begin and end time periods. Ex: {"Monday": ['begin', 'end']}
    if not util.validate_availability_input_format(availability_data):
        flash("Availability is not formatted correctly.", "error")
        return redirect('/calendar-availability')
    
    # Generate availability periods, reoccurring for those marked
    # Input here is in MultiDict form, outputs a MultiDict
    generated_availability = util.generate_availability(availability_data, reoccurring_data, 2)
    
    # Convert to official ISO-format with timezone info and verify no inputs in past. Currently hard-coded for -8 PST.
    # Use try-catch block with convert_to_iso_with_tz
    try:
        converted_input = util.convert_to_iso_with_tz(generated_availability, user_timezone)
    except error_utils.TimeValidationError as e:
        message = e.message # get the message passed
        flash(f"{message}", "error")
        return redirect('/calendar-availability')
    
    # Generate the appointment slots for insertion. Currently hardcoded for 30 minutes.
    appointments = MultiDict()
    for day, period in converted_input.items(multi=True):
        # Note that the _split_into_30min_segments() function returns a list of individual datetimes in 30 minute segments between two datetimes, NOT a begin to end period of two datetime objects by 30 minutes.

        slots_in_30 = util.split_into_30min_segments(datetime.fromisoformat(period[0]), datetime.fromisoformat(period[1]))
        # Add in the end period for storage in db
        appointments.add(day, [[slot.isoformat(' '), (slot + timedelta(minutes=30)).isoformat(' ')] for slot in slots_in_30])
    
    # Insert the availability into the local database for each day of the week
    # If fails, logs database error and returns false
    
    if g.db.insert_availability(appointments):
        flash("Availability submitted", "success")
    else:
        flash("Availability insertion failed, probably due to format", "error")
        return redirect('/calendar-availability')
    return redirect('/calendar-availability')


# Placeholder for future admin functionality
@app.route("/calendar/clear/<date>", methods=['POST'])
@instantiate_database
def clear_date_availability(date):
    pass

@app.route("/booking/coaching", methods=["GET"])
@instantiate_database
def pick_coaching_call():
    # Get availability periods from database
    appointments = util.get_booking_slots(g.db)
    # Remove the T for easier management on front-end and convert to ISO str
    appointments_in_iso = [slot.isoformat().replace('T', ' ') for day in appointments for slot in day]
    appointments_json = dumps(appointments_in_iso)
    return render_template('booking.html', appointments=appointments_json)

@app.route("/booking/coaching/purchase", methods=["POST"])
def purchase_coaching_call():
    # Google API requires the 'T':
    # Need to verify query params are clean before passing
    selected_datetime_utc = request.form['selected_datetime_utc'].replace(' ', 'T')
    booking_name = request.form['booking_name']
    booking_email = request.form['booking_email']
    checkout_type = "coaching_call"
    checkout_amount = "1"
    # Redirect to checkout session page with necessary params
    return redirect(url_for('checkout', booking_name=booking_name, booking_email=booking_email, checkout_type=checkout_type, checkout_amount=checkout_amount, selected_datetime_utc=selected_datetime_utc))

# In future - allow people to submit message with their booking & upload docs
def book_coaching_call(db, datetime_utc: str, booking_name: str, booking_email: str, client_ref_id: UUID):
    # Google API requires the 'T':
    start_time = datetime_utc.replace(' ', 'T')
    end_time = (datetime.fromisoformat(start_time) + timedelta(minutes=30)).isoformat()
    # Create meeting resource with the googleapiclient:
    try:
        meeting = booking_service.BookingService({booking_name: booking_email}, {"start": f"{start_time}",
        "end": f"{end_time}"}, 'Coaching Call')
    except HttpError as e:
        raise # re-raise the error to be caught by the error-handler
    # Will execute if no exception is raised
    else:
        # Book appointment in database for local storage by updating appointment record as is_booked=True
        if db.insert_booking(start_time, end_time, client_ref_id):
            logger.info("Booking submitted.")
        else:
            logger.error("Booking insertion  in db failed.")
    # Return response object to indicate booking was successful
    return meeting.event_states

@app.errorhandler(404)
def error_handler(error):
    flash(f"An error occurred.", "error")
    return redirect("/index")

# Handle in invalid googleapiclient response which raises a custom HttpError
@app.errorhandler(HttpError)
def handle_bad_api_call(error):
    # Will need to handle this differently in the future if the google booking fails after the user has already paid
    flash("An error occurred while booking your google appointment. Please re-try.", "error")
    return redirect("/booking/coaching")

# Note: this route requires the submission of query parameters
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    # Protect endpont from cross-site requests and forgery
    # origin = request.headers.get("Origin") or request.headers.get("Referer")
    # if not app.config['DOMAIN'] in origin:
    #     return jsonify({"error": "Unauthorized Request"}), 403 # Forbidden

    # Get query parameters
    checkout_type = request.args.get("checkout_type")
    price_id = STRIPE_PRICE_IDS[checkout_type]
    amount = int(request.args.get("checkout_amount")) # This is a quantity, not price. Required
    # Not all customer info query params may exist, depends on purchase being made
    customer_info = {
        "checkout_type": checkout_type, # Required
        "booking_name": request.args.get("booking_name", ""), 
        "booking_email": request.args.get("booking_email", ""), "selected_datetime_utc": request.args.get("selected_datetime_utc", ""),
        }
    # Generate client reference id to attach
    ref_id = uuid4()
    # Store potential purchase at the return? endpoint to avoid storng people just checking out the purchase page

    # Create and return checkout session with attached meta-data
    payment_processor = stripe_integration.StripeProcessor(app, price_id, amount, customer_info, ref_id)

    return payment_processor.get_checkout_session

# Web-hook route
# Use the secret provided by Stripe CLI for local testing
# or your webhook endpoint's secret.
endpoint_secret = 'whsec_724431fe58f3768bb230cfa4ff30e72e96587192160691a201acaad0a9f3dbf2'

@app.route('/webhook', methods=['POST'])
@instantiate_database
def stripe_webhook():
    # Stripe webhook shouldn't be over 8-10kb
    MAX_CONTENT_LENGTH = 100 * 1024 # 100KB

    content_length = request.headers.get('Content-Length', None)
    if content_length: # If not None
        content_length = int(content_length)
        if content_length > MAX_CONTENT_LENGTH:
            logger.error(f"Rejecting webhook request. Payload too large: {content_length}")
            return jsonify({"error": "Max content length exceeded"}), 413
    # If it is None, manually verify length
    total_size = 0
    payload_chunks = []
    for chunk in request.stream:
        total_size += len(chunk)
        if total_size > MAX_CONTENT_LENGTH:
            logger.error(f"Rejecting webhook request. Payload too large: {content_length}")
            return jsonify({"error": "Max content length exceeded"}), 413
        payload_chunks.append(chunk)

    # Join into payload since stream can only be read once
    payload = b"".join(payload_chunks).decode("utf-8", errors='replace')
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        # Verify the Stripe webhook signature
        # Event will be a Checkout Session object
        logger.info("Constructing event via webhook")
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret)
        logger.info(f"Event constructed: {event}")
    except ValueError:
        # Invalid payload
        logger.error("Invalid webhook payload")
        return jsonify({"error": "Invalid payload"}), 400
    except SignatureVerificationError:
        # Invalid signature
        logger.error("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 400

    # Handle the event when checkout is completed
    if event["type"] in ["checkout.session.completed", "checkout.session.async_payment_succeeded"]:
        # In future, use an event queue to speed up code 200 response
        # Should return a Response object
        logger.info("Fulfilling checkout via webhook")
        if fulfill_checkout(event, g.db):
            return jsonify({"status": "success"}), 200        
    else:
        logger.error("Invalid webhook event type")
        return jsonify({"error": "Invalid event type"}), 400
    # Catch all response to avoid timeout
    logger.info("Catch all response reached on webhook function.")
    return jsonify({"status": "success"}), 200

# Fulfillment function
def fulfill_checkout(event, db) -> bool:
    """
    Fulfills a product for customer once payment is received.

    Args: event is either a checkout.session.complete JSON payload via webhook or a checkout.Session passed via client re-direct.

    Returns: boolean value representing fulfillment of product
    """
    logger.info("Fulfilling Checkout Session")
    
    # Use get() since regular dict subscripting will cause key-error if event is a checkout session type
    if event.get('type', '') == 'checkout.session.completed':
        checkout_session = stripe.checkout.Session.construct_from(event['data']['object'], key='object')
    else: 
        checkout_session = stripe.checkout.Session.retrieve(
        event.id, expand=['line_items'])

    client_ref_id = checkout_session.client_reference_id
    meta_data_as_json = json.dumps(checkout_session.metadata)
    # If the record already exists, Postgres function will return the boolean fulfillment status, otherwise will insert new record and return fulfillment status as False
    fulfillment_status = db.check_or_insert_fulfillment(client_ref_id, meta_data_as_json, False)

    payment_status = checkout_session.payment_status
    customer_info = checkout_session.metadata
    fulfillment_action_type = customer_info.get('checkout_type')
    # Check the Checkout Session's payment_status property
    # to determine if fulfillment should be peformed
    if payment_status != 'unpaid' and not fulfillment_status:
        # TODO: Perform fulfillment of the line items
        match fulfillment_action_type:
            case 'coaching_call':
                # Function returns meeting event_states
                event_states = book_coaching_call(db, customer_info.get('selected_datetime_utc'), customer_info.get('booking_name'), customer_info.get('booking_email'), client_ref_id)
                if event_states.get('status') == 'confirmed':
                    return True
                return False
            case 'salary_guide':
                customer_email = checkout_session.get('customer_details').get('email')
                state = submit_to_mailchimp(customer_email, client_ref_id, 'salary_guide')
                if not state:
                    logger.error(f'Error occurred fulfilling salary guide via mailchimp. client_ref_id: {client_ref_id}')
                    return False
                return True
            case _:
                return False
    logger.info(f"Already fulfilled. Fulfillment_status: {fulfillment_status}. Skipping fulfillment")
    return False

# Used to to render confirmation page after a successful checkout session
# Refactor to do actual confirmation pages in the future
@app.route('/success')
def checkout_success():
    flash("Thanks for your purchase! You'll receive an email with the details!", 'success')
    return redirect(url_for('index'))

# Need to figure out how to guard this route as well
@app.route('/return', methods=['GET'])
@instantiate_database
def checkout_return():
    session = stripe.checkout.Session.retrieve(request.args.get("session_id"))
    fulfillment_status = False
    # Log prior generated client_reference_id prior to any actions to store payment attempt to enable manual intervention if needed
    client_ref_id = session.client_reference_id
    meta_data_as_json = json.dumps(session.metadata)
    # Fulfill product purchased if successful, otherwise return to homepage
    if session.status == 'open' or session.status == 'expired':
        logger.error(f"Stripe processor error: payment_stauts: {session.payment_status}, fulfillment status: {fulfillment_status}")
        # Store reference to purchase attempt in local db
        g.db.insert_fulfillment(client_ref_id, meta_data_as_json, False)
        flash("Payment failed or cancelled. Please try again.", "error")
        return render_template(url_for('index'))
    
    if session.status == 'complete' and session.payment_status == 'paid':
        
        # Storage of reference to purchase will happen in fulfillment function to avoid duplicate database connection with successful payments
        fulfillment_status = fulfill_checkout(session, g.db)
        logger.info(f"Stripe processor success: payment_stauts: {session.payment_status}, fulfillment status: {fulfillment_status}")
        return redirect(url_for('checkout_success'))
    
    # General failure for unknown reason, insert the fulfillment locally for reference
    g.db.insert_fulfillment(client_ref_id, meta_data_as_json, False)
    logger.error(f"Stripe processor error: payment_stauts: {session.payment_status}, fulfillment status: {fulfillment_status}")
    flash("An error occurred. Please try again.", "error")
    return render_template(url_for('index'))

@app.route("/checkout")
def checkout():
    return render_template('checkout.html')

# Route for GET subscrbe pages

@app.route("/subscribe", methods=['POST'])
def mailchimp_handler():
    # Get the email and product type being subscribed to, if any, from the args passed
    user_email = request.form.get('user_email')
    # Right now, this can only be for resume guide or Q&A guide. The salary negotiation guide, since it's a purchase, will be submitted without a tag. Someone just subscribing to mailing list will be submitted with no tag.
    journey_tag = request.form.get('product_subscription', '')
    submission_status = submit_to_mailchimp(user_email, 'Free Resource', journey_tag)
    if not submission_status: 
        flash('An error occurred. Please try again', 'error')
        return redirect('/index')
    flash('Success! Thanks for subscribing.', 'success')
    return redirect('/index')

def submit_to_mailchimp(user_email, client_ref_id, journey_tag=None):
    submission_status = None
    try:
        mailchimp = mailchimp_integration.MailChimpIntegration()
        if journey_tag:
            submission_status = mailchimp.submit_member_to_mailchimp(user_email, journey_tag)
        else:
            submission_status = mailchimp.submit_member_to_mailchimp(user_email)
    except Exception as e:
        logger.error(f'An error occurred during MailChimp submission: {e.args}. Inspect logs. Associated client_ref_id: {client_ref_id}')
        return False
    if submission_status:
        return True
    logger.error(f'MailChimp submission returned false. Inspect logs. Associated client_ref_id: {client_ref_id}')
    return False

@app.route('/submit-contact-form', methods=['POST'])
def submit_contact_form():
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()

    if not re.match("^[^@]+@[^@]+\.[^@]+$", email):
         flash('Email contains disallowed symbols', 'error')
         return redirect(url_for('get_contact'))
    
    name = request.form.get('name', '').strip()
    message = request.form.get('Message', '').strip()

    if not name or not email or not message:
        flash('Name, email, and message are required', 'error')
        return redirect(url_for('get_contact'))
    
    if len(message) > 5000:
        flash('Message is too big.', 'error')
        return redirect(url_for('get_contact'))
    
    gmail_service = gmail.GmailIntegration()
    return_message = gmail_service.send_email(name, email, message, phone)
    logger.info(f"{return_message}")
    return redirect(url_for('get_contact'))

@app.route("/subscribe/<product>", methods=['GET'])
def render_product_subscription(product):
    return render_template('subscribe_template.html', product_type=product)

@app.route("/coaching-call")
def render_coaching_call():
    return render_template('coaching_call.html')

if __name__ == '__main__':
    # production
    if os.environ.get('FLASK_ENV') == 'production':
       app.run(debug=False)
    else:
       toolbar = DebugToolbarExtension(app)
       app.run(debug=True, port=5003)
       
    