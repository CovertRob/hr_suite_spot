from datetime import timedelta, datetime
import json
import logging
import os
from uuid import UUID, uuid4
from flask import Flask, Response, render_template, request, flash, redirect, g, session, url_for, jsonify
import secrets
from flask_debugtoolbar import DebugToolbarExtension
from booking import database
from booking import error_utils
from booking import booking_utils as util
from functools import wraps
from pprint import pprint
from werkzeug.datastructures import MultiDict
from json import dumps
from booking import booking_service
from googleapiclient.http import HttpError
import stripe
from stripe import SignatureVerificationError
from booking import stripe_integration

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

# Static Stripe price-id's (short-term fix):
STRIPE_PRICE_IDS = {"coaching_call": "price_1R6LuhH8d4CYhArR8yogdHvb"}

# Use decorator to create g.db instance within request context window for functions that require it to conserve resources
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
    return render_template('test.html', title = title)

# Description page about User
@app.route("/about")
def get_about():
    return render_template('about.html')

# General overview of each service provided and provide links to book coaching calls/purchase products
@app.route("/services")
def get_services():
    return render_template('services.html')

# General contact page. Should include address for company and contact information to include an email.
# Also include a contact me form submisson for general inquiries
@app.route("/contact")
def get_contact():
    return render_template('contact.html')


# Admin page for user to submit their availability to the system for appointments to be booked against.
# Future - add authentication protection to route
@app.route("/calendar_availability", methods=['GET'])
def get_calendar():
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return render_template('calendar.html', days_of_week=days_of_week)

# This route only to be used by admin
@app.route("/calendar", methods=["POST"])
@instantiate_database
def submit_availability():
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
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
        return redirect('/calendar')
    
    # Generate availability periods, reoccurring for those marked
    # Input here is in MultiDict form, outputs a MultiDict
    generated_availability = util.generate_availability(availability_data, reoccurring_data, 2)
    
    # Convert to official ISO-format with timezone info and verify no inputs in past. Currently hard-coded for -8 PST.
    # Use try-catch block with convert_to_iso_with_tz
    try:
        converted_input = util.convert_to_iso_with_tz(generated_availability)
    except error_utils.TimeValidationError as e:
        message = e.message # get the message passed
        flash(f"{message}", "error")
        return redirect('/calendar')
    
    # Generate the appointment slots for insertion. Currently hardcoded for 30 minutes.
    appointments = MultiDict()
    for day, period in converted_input.items(multi=True):
        # Note that the _split_into_30min_segments() function returns a list of individual datetimes in 30 minute segments between two datetimes, NOT a begin to end period of two datetime objects by 30 minutes.

        slots_in_30 = util.split_into_30min_segments(datetime.fromisoformat(period[0]), datetime.fromisoformat(period[1]))
        # Add in the end period for storage in db
        appointments.add(day, [[slot.isoformat(' '), (slot + timedelta(minutes=30)).isoformat(' ')] for slot in slots_in_30])
    
    # Insert the availability into the local database for each day of the week
    # If fails, logs database error and returns false
    #pprint(appointments)
    
    if g.db.insert_availability(appointments):
        flash("Availability submitted", "success")
    else:
        flash("Availability insertion failed, probably due to format", "error")
        return redirect('/calendar')
    return redirect('/calendar')

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
    selected_datetime_utc = request.form['selected_datetime_utc'].replace(' ', 'T')
    booking_name = request.form['booking_name']
    booking_email = request.form['booking_email']
    checkout_type = "coaching_call"
    checkout_amount = "1"
    # Redirect to checkout session page with necessary params
    return redirect(url_for('checkout', booking_name=booking_name, booking_email=booking_email, checkout_type=checkout_type, checkout_amount=checkout_amount, selected_datetime_utc=selected_datetime_utc))

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
    
    

@app.route('/coaching/submit-appointment/success/', methods=['GET'])
def booking_confirmation():
    event_url = request.args.get('event_states')
    return render_template('booking_confirmation.html', confirmation_data=event_url)

@app.template_filter('parse_confirmation_data')
def parse_confirmation_data(data):
    
    return data

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
    amount = int(request.args.get("checkout_amount"))
    # Not all customer info query params may exist, depends on purchase being made
    customer_info = {
        "checkout_type": checkout_type,
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
endpoint_secret = 'whsec_...'

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
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        # Invalid payload
        return jsonify({"error": "Invalid payload"}), 400
    except SignatureVerificationError:
        # Invalid signature
        return jsonify({"error": "Invalid signature"}), 400

    # Handle the event when checkout is completed
    if event["type"] in ["checkout.session.completed", "checkout.session.async_payment_succeeded"]:
        # In future, use an event queue to speed up code 200 response
        # Should return a Response object
        fulfill_checkout(event, g.db)
        
    else:
        return jsonify({"error": "Invalid event type"}), 400
    # Catch all response to avoid timeout
    logger.info("Catch all response reached on webhook function.")
    return jsonify({"status": "success"}), 200

# Fulfillment function
def fulfill_checkout(event, db) -> Response:
    logger.info("Fulfilling Checkout Session:", event.id)

    FULFILLMENT_TYPES = ['resume_guide', 'coaching_call']
    
    # TODO: Make this function safe to run multiple times,
    # even concurrently, with the same session ID
    # Handled via the database function - Done

    # TODO: Make sure fulfillment hasn't already been
    # peformed for this Checkout Session - Done
    pprint(event)
    checkout_session = stripe.checkout.Session.retrieve(
    event.id, expand=['line_items'])
    client_ref_id = checkout_session.client_reference_id
    meta_data_as_json = json.dumps(checkout_session.client_reference_id)
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
                return True
            case 'resume_guide':
                pass
            case _:
                return False
    return False

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/return', methods=['GET'])
@instantiate_database
def checkout_return():
    session = stripe.checkout.Session.retrieve(request.args.get("session_id"))
    fulfillment_status = False
    # Log prior generated client_reference_id prior to any actions to store payment attempt to enable manual intervention if needed
    client_ref_id = uuid4()
    meta_data_as_json = json.dumps(session.metadata)
    # Fulfill product purchased if successful, otherwise return to homepage
    if session.status == 'open' or session.status == 'expired':
        logger.error(f"Stripe processor error: payment_stauts: {session.payment_status}, fulfillment status: {fulfillment_status}")
        # Store reference to purchase attempt in local db
        g.db.insert_fulfillment(client_ref_id, meta_data_as_json, False)
        flash("Payment failed or cancelled. Please try again.", "error")
        return render_template(url_for('index'))
    
    if session.status == 'complete' and session.payment_status == 'paid':
        customer_info = session.metadata
        # Storage of reference to purchase will happen in fulfillment function to avoid duplicate database connection with successful payments
        fulfillment_status = fulfill_checkout(session, g.db)
        logger.info(f"Stripe processor success: payment_stauts: {session.payment_status}, fulfillment status: {fulfillment_status}")
        # Still need to handle and pass event states for successs page
        return render_template('success.html')
    
    # General failure for unknown reason
    g.db.insert_fulfillment(client_ref_id, meta_data_as_json, False)
    logger.error(f"Stripe processor error: payment_stauts: {session.payment_status}, fulfillment status: {fulfillment_status}")
    flash("An error occurred. Please try again.", "error")
    return render_template(url_for('index'))

@app.route("/checkout")
def checkout():
    return render_template('checkout.html')

# Add resume route

# Add Interview route

# Add Career Path route

if __name__ == '__main__':
    # production
    if os.environ.get('FLASK_ENV') == 'production':
       app.run(debug=False)
    else:
       app.run(debug=True, port=5003)
       toolbar = DebugToolbarExtension(app)
    