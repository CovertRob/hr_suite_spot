from datetime import timedelta, datetime
import json
import logging
import os
from uuid import UUID, uuid4
from flask import Flask, render_template, request, flash, redirect, g, url_for, jsonify, session
import secrets
from flask_debugtoolbar import DebugToolbarExtension
from hr_suite_spot.booking import database, booking_service, stripe_integration, mailchimp_integration, gmail, drive_integration
from hr_suite_spot.booking import booking_utils as util
from functools import wraps
from werkzeug.datastructures import MultiDict
from json import dumps
from googleapiclient.http import HttpError
import stripe
from stripe import SignatureVerificationError
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from pprint import pprint
from werkzeug.utils import secure_filename
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
if os.environ.get('FLASK_ENV') == 'production':
    # Live environment price
    STRIPE_PRICE_IDS = {"coaching_call": "price_1RKucIH8d4CYhArRHXFepWtG",
                    "salary_guide": "price_1RKuc7H8d4CYhArRZCt2wQKn"}
else:
    STRIPE_PRICE_IDS = {"coaching_call": "price_1R6LuhH8d4CYhArR8yogdHvb",
                    "salary_guide": "price_1RKuEtH8d4CYhArRVnpdf9sy"}

# Use decorator to create g.db instance within request context window for functions that require it to conserve resources and prevent N +1 instances
def instantiate_database(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.db = database.DatabasePersistence()
        return f(*args, **kwargs)
    return decorated_function

# Decorator to set state token
def set_state_token(session_key='state_token'):
    def decorated_func(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = secrets.token_urlsafe(32)
            session[session_key] = token
            session.modified = True
            logger.info(f"Set state token: {session_key}: {token}")
            return f(*args, **kwargs)
        return wrapper
    return decorated_func

# Decorator to check state token, factory style
def require_state_token(session_key='state_token', query_param='token'):
    def decorated_func(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token_from_cookie = session.get(session_key)
            if not token_from_cookie:
                flash("Invalid or missing state token.", "error")
                return redirect(url_for('index'))
            # Do not pop state token because they must persist for purchase workflows through redirects
            return f(*args, **kwargs)
        return wrapper
    return decorated_func

# Future - improved logging w/ decorator and trace-id's

@app.route('/')
def home():
    return redirect(url_for('index'))

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
    # Record usage while inside protected endpoint for visibility on actions
    logger.info(
            "Report on usage of protected /calendar-availability endpoint: | IP: %s | UA: %s | Method: %s | Args: %s | Time: %s",
            request.remote_addr,
            request.user_agent.string,
            request.method,
            request.args.to_dict(),
            datetime.now().isoformat()
        )
    return render_template('admin_input.html', days_of_week=days_of_week)

@app.route("/admin/availability", methods=["GET", "POST", "DELETE"])
@instantiate_database
@auth.login_required
def api_admin_availability():
    if request.method == "GET":
        rows = g.db.retrieve_availability_periods()
        return jsonify([
            {
                "id":      row["id"],               # PK from table
                "start":   row["start"],
                "end":     row["end"]
            } for row in rows
        ])
    elif request.method == "POST":
        payload = request.get_json(force=True) or {}
        slots = payload.get("slots", [])

        # perform time checks here
        user_tz = payload.get("tz", "UTC") # fallback if omitted
        # validate
        if not util.slots_are_valid(slots, timezone=user_tz):
            return jsonify({"error": "Invalid time selection"}), 400
        
        appointments = []
        for slot in slots:
            # Note that the _split_into_30min_segments() function returns a list of individual datetimes in 30 minute segments between two datetimes, NOT a begin to end period of two datetime objects by 30 minutes.

            start = slot['start'].replace("Z", "+00:00")
            end = slot['end'].replace("Z", "+00:00")
            slots_in_30 = util.split_into_30min_segments(datetime.fromisoformat(start), datetime.fromisoformat(end))
            # Add in the end period for storage in db
            appointments += [[slot.isoformat(' '), (slot + timedelta(minutes=30)).isoformat(' ')] for slot in slots_in_30]
        g.db.insert_availability(appointments)
        return ("", 204)
    
    elif request.method == "DELETE":
        payload = request.get_json(force=True) or {}
        ids = payload.get("ids")
        rng = payload.get("range")
        status = None
        if payload.get("all") is True:
            status = g.db.delete_all_availability()
        if ids:
            status = g.db.delete_availability_by_id(ids)
        elif rng:
            status = g.db.delete_availability_range(rng["start"], rng["end"])
        if status:
                flash("Success", "success")
                return "", 204
        flash("An error occurred, please retry or contact your boyfrined.", "error")
        return "", 500
    return jsonify({"error": "Not allowed"}), 400

@app.route("/booking/coaching", methods=["GET"])
@instantiate_database
def pick_coaching_call():
    # Get availability periods from database
    appointments = util.get_booking_slots(g.db)
    # Remove the T for easier management on front-end and convert to ISO str
    # appointments_in_iso = [slot.isoformat().replace('T', ' ') for day in appointments for slot in day]
    return render_template('booking.html', appointments=json.dumps(appointments))

@app.route("/booking/coaching/purchase", methods=["POST"])
@instantiate_database
def purchase_coaching_call():
    # Google API requires the 'T' in ISO format to be valid payload
    # Need to verify query params are clean before passing
    selected_datetime_utc = request.form['selected_datetime_utc'].replace(' ', 'T')
    slot_id = request.form.get('slot_id')
    token = g.db.acquire_hold(int(slot_id))
    if token is None:
        flash("Someone is holding that slot. Please pick another.", 'error')
        return redirect(url_for('pick_coaching_call'))
    
    booking_name = request.form['booking_name']
    booking_email = request.form['booking_email']
    checkout_type = "coaching_call"
    checkout_amount = "1"
    # Redirect to checkout session page with necessary params
    return redirect(url_for('checkout', booking_name=booking_name, booking_email=booking_email, checkout_type=checkout_type, checkout_amount=checkout_amount, selected_datetime_utc=selected_datetime_utc, slot_id=slot_id, hold_token=token, heartbeat=30*1000) )# In ms

# In future - allow people to submit message with their booking & upload docs
def book_coaching_call(db, datetime_utc: str, booking_name: str, booking_email: str, client_ref_id: UUID):
    # Google API requires the 'T':
    start_time = datetime_utc.replace(' ', 'T')
    end_time = (datetime.fromisoformat(start_time) + timedelta(minutes=30)).isoformat()
    # Create meeting resource with the googleapiclient:
    try:
        # Add in admin so email notification pops up - added fix 06/09/2025
        meeting = booking_service.BookingService({booking_name: booking_email, "admin": "hello@hrsuitespot.com"}, {"start": f"{start_time}",
        "end": f"{end_time}"}, 'Coaching Call')

        # Send email notification to admin of booking so they see it
        gmail_client = gmail.GmailIntegration()
        notification = gmail_client.create_message("hello@hrsuitespot.com", "cto@hrsuitespot.com", "Coaching Call Purchase", "A coaching call has been booked on the website. Please check your calendar.")
        send_message = (gmail_client.service.users().messages().send(userId='me', body=notification).execute())
        
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

@app.post("/api/extend_hold")
@instantiate_database
def api_extend_hold():
    # Get appointment slot to hold
    payload = request.get_json(force=True)
    # slot_id is PK in database, token is uuid4 representing potential user transaction
    pprint(payload)
    g.db.extend_hold(payload["slot_id"], payload["token"])
    return "", 204

@app.post("/api/release_hold")
@instantiate_database
def api_release_hold():
    payload = request.get_json(force=True)
    g.db.release_hold(int(payload["slot_id"]), payload["token"])
    return "", 204


@app.errorhandler(404)
def error_handler(error):
    flash(f"An error occurred.", "error")
    logger.critical(f"A 404 Error occurred ATT. error: {error}")
    return redirect("/index")

# Handle in invalid googleapiclient response which raises a custom HttpError
@app.errorhandler(HttpError)
def handle_bad_api_call(error):
    # Will need to handle this differently in the future if the google booking fails after the user has already paid
    flash("An error occurred in your submission. Please re-try.", "error")
    logger.critical(f"An HTTP Error occurred.")
    return redirect("/index")

# Note: this route requires the submission of query parameters
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():

    # Get query parameters
    checkout_type = request.args.get("checkout_type")
    price_id = STRIPE_PRICE_IDS[checkout_type]
    amount = int(request.args.get("checkout_amount")) # This is a quantity, not price. Required

    # Need to get client_ref_id here from query pass

    # Not all customer info query params may exist, depends on purchase being made
    customer_info = {
        "checkout_type": checkout_type, # Required
        "booking_name": request.args.get("booking_name", ""), 
        "booking_email": request.args.get("booking_email", ""), "selected_datetime_utc": request.args.get("selected_datetime_utc", ""),
        }
    # Generate client reference id to attach for db cross-references
    ref_id = uuid4()

    # Create and return checkout session with attached meta-data
    payment_processor = stripe_integration.StripeProcessor(app, price_id, amount, customer_info, ref_id)

    # Set Flask session flag to check and protect return route later
    session['stripe_checkout_initiated'] = True
    session.modified = True

    return payment_processor.get_checkout_session

# Web-hook route
# Use the secret provided by Stripe CLI for local testing
# or your webhook endpoint's secret.
endpoint_secret = os.environ.get('WHSEC') # Provide in Render env var

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
    logger.warning("Catch all response reached on webhook function.")
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
    # If the record already exists, Postgres function will return the boolean fulfillment status, otherwise will insert new record and return fulfillment status as False. This is to make the function safe to double call with web-hook.
    fulfillment_status = db.check_or_insert_fulfillment(client_ref_id, meta_data_as_json, False)

    payment_status = checkout_session.payment_status
    customer_info = checkout_session.metadata
    fulfillment_action_type = customer_info.get('checkout_type')
    # Check the Checkout Session's payment_status property
    # to determine if fulfillment should be peformed
    if payment_status != 'unpaid' and not fulfillment_status:
        match fulfillment_action_type:
            case 'coaching_call':
                # Function returns meeting event_states
                event_states = book_coaching_call(db, customer_info.get('selected_datetime_utc'), customer_info.get('booking_name'), customer_info.get('booking_email'), client_ref_id)
                if event_states.get('status') == 'confirmed':
                    # Submit info the MailChimp to send info email about call after it's been confirmed book via google api.
                    customer_email = checkout_session.get('customer_details').get('email')
                    state = submit_to_mailchimp(customer_email, client_ref_id, 'coaching call')
                    if not state:
                        logger.error(f'Error occurred sending coaching call client to MailChimp. client_ref_id: {client_ref_id}, customer_info: {customer_info}')
                        return False
                    return True
                logger.error(f"An error occurred booking the coaching call. client_ref_id: {client_ref_id}, customer_info: {customer_info}")
                return False
            case 'salary_guide':
                customer_email = checkout_session.get('customer_details').get('email')
                state = submit_to_mailchimp(customer_email, client_ref_id, 'salary_guide')
                if not state:
                    logger.error(f'Error occurred fulfilling salary guide via mailchimp. client_ref_id: {client_ref_id}, customer_info: {customer_info}')
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

@app.route('/return', methods=['GET'])
@instantiate_database
def checkout_return():
    # Verify that no outside entity is trying to interact with the checkout return route by using session flag
    if not session.get('stripe_checkout_initiated'):
        logger.warning(
            "Unauthorized /return access attempt | IP: %s | UA: %s | Method: %s | Args: %s | Time: %s",
            request.remote_addr,
            request.user_agent.string,
            request.method,
            request.args.to_dict(),
            datetime.now().isoformat()
        )
        flash("Session expired. Please try again", 'error')
        return redirect(url_for('index'))
    # Reset flag by removing
    session.pop('stripe_checkout_initiated', None)

    stripe_session = stripe.checkout.Session.retrieve(request.args.get("session_id"))
    fulfillment_status = False
    # Log prior generated client_reference_id prior to any actions to store payment attempt to enable manual intervention if needed

    # This is the UUID4 generated by the backend during checkout session creation
    client_ref_id = stripe_session.client_reference_id
    meta_data_as_json = json.dumps(stripe_session.metadata)
    # Fulfill product purchased if successful, otherwise return to homepage
    if stripe_session.status == 'open' or stripe_session.status == 'expired':
        logger.error(f"Stripe processor error: payment_stauts: {stripe_session.payment_status}, fulfillment status: {fulfillment_status}, client_ref_id: {client_ref_id}, metadata: {meta_data_as_json}")
        # Store reference to purchase attempt in local db
        g.db.insert_fulfillment(client_ref_id, meta_data_as_json, False)
        flash("Payment failed or cancelled. Please try again.", "error")
        return render_template(url_for('index'))
    
    if stripe_session.status == 'complete' and stripe_session.payment_status == 'paid':
        
        # Storage of reference to purchase will happen in fulfillment function to avoid duplicate database connection with successful payments
        # Fulfillmment status can be false if any of the api calls fail: stripe, google calendar booking, mailchimp
        fulfillment_status = fulfill_checkout(stripe_session, g.db)
        if fulfillment_status:
            logger.info(f"Stripe processor success: payment_status: {stripe_session.payment_status}, fulfillment status: {fulfillment_status}")
        else:
            logger.error(f"Stripe processor error or api error: payment_status: {stripe_session.payment_status}, fulfillment status: {fulfillment_status}")
        return redirect(url_for('checkout_success'))
    
    # General failure for unknown reason, insert the fulfillment locally for reference
    g.db.insert_fulfillment(client_ref_id, meta_data_as_json, False)
    logger.error(f"Stripe processor error: payment_stauts: {stripe_session.payment_status}, fulfillment status: {fulfillment_status}")
    flash("An error occurred. Please try again. If you were charged, contact support please.", "error")
    return render_template(url_for('index'))

@app.route("/checkout")
def checkout():
    query_params = request.args.to_dict()
    slot_id = query_params.get("slot_id")
    hold_token = query_params.get("hold_token")
    heartbeat = int(query_params.get("heartbeat", 30000)) # Default to 30,000 ms

    return render_template('checkout.html', title='Checkout', slot_id=slot_id, hold_token=hold_token, heartbeat=heartbeat)

# Route for subscribe forms
@app.route("/subscribe", methods=['POST'])
def mailchimp_handler():
    # Get the email and product type being subscribed to, if any, from the args passed
    user_email = request.form.get('user_email')
    formatted_email = util.sanitize_email(user_email)
    # Right now, this can only be for resume guide or Q&A guide. The salary negotiation guide, since it's a purchase, will be submitted without a tag. Someone just subscribing to mailing list will be submitted with no tag.
    journey_tag = request.form.get('product_subscription', '')
    submission_status = submit_to_mailchimp(formatted_email, 'Free Resource', journey_tag)
    if not submission_status: 
        logger.error(f"An error occurred submitting {formatted_email} to Mailchimp.")
        flash('An error occurred. Please try again', 'error')
        return redirect('/index')
    flash('Submitted! Keep an eye out for more FREE resources and early access to releases this spring.', 'success')
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
    name = request.form.get('name', '').strip()
    message = request.form.get('Message', '').strip()
    uploaded_file = request.files.get('pdfFile')

    # Check that all fields are present
    if any(field.strip() == '' for field in [email, name, message]):
        flash('Name, email, and message are required', 'error')
        return redirect(url_for('get_contact'))
    # Check email input
    formatted_email = util.sanitize_email(email)
    # Check phone input
    formatted_phone = util.sanitize_phone(phone)
    # Check message input
    formatted_message = util.sanitize_email_body(message)
    # Upload file if it is present
    view_link = None
    pprint(request.files)
    if uploaded_file:
        if uploaded_file.content_type != "application/pdf":
            flash("File upload failure. Only PDF's are allowed.", 'error')
            return redirect(url_for('get_contact'))
        
        drive = drive_integration.DriveIntegration()
        safe_name = secure_filename(uploaded_file.filename)
        logger.info("Uploading file now.")
        upload_status, view_link = drive.upload_file(uploaded_file, safe_name, name)
        logger.info("Upload complete")
    if view_link:
        formatted_message += f"User File Upload: {view_link}"
    
    gmail_service = gmail.GmailIntegration()
    return_message = gmail_service.send_email(name, formatted_email, formatted_message, formatted_phone)
    logger.info(f"Gmail return from subscribe submission: {return_message}")
    try:
        if return_message.get('labelIds', None)[0] == 'SENT':
            flash("Submitted! We'll be in touch soon.", 'success')
            return redirect(url_for('get_contact'))
    except TypeError as e:
        flash('An error occurred, please try again.', 'error')
        logger.error(f"Error occurred submitting contact form: Exception: {e.args}, Gmail API response: {return_message}")
        return redirect(url_for('get_contact'))
    # If 'SENT' not present and an id was present, return failure and log
    logger.error(f"Error occurred submitting contact form: Exception: {e.args}, Gmail API response: {return_message}")
    flash('An error occurred, please try again.', 'error')
    return redirect(url_for('get_contact'))


@app.route("/subscribe/<product>", methods=['GET'])
def render_product_subscription(product):
    return render_template('subscribe_template.html', product_type=product)

@app.route("/coach")
def render_coaching_call():
    return render_template('coaching_call.html')

if __name__ == '__main__':
    # production
    if os.environ.get('FLASK_ENV') == 'production':
       app.run(debug=False)
    else:
       toolbar = DebugToolbarExtension(app)
       app.run(debug=True, port=5003)