from datetime import timedelta, datetime
import logging
import os
from flask import Flask, config, render_template, request, flash, redirect, g, session, url_for, jsonify
import secrets
from flask_debugtoolbar import DebugToolbarExtension
from requests import get
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

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32) #256 bit
    app.config['SECRET_KEY'] = app.secret_key
    if os.environ.get('FLASK_ENV') == 'production':
        app.config['DOMAIN'] = 'https://hrsuitespot.com'
    else:
        app.config['DOMAIN'] = 'http://localhost:5003'
        app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = False  # Prevents redirect issues
    return app

app = create_app()

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
@app.route("/calendar", methods=['GET'])
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

@app.route("/coaching/submit-appointment", methods=["POST"])
@instantiate_database
def book_coaching_call():
    # Google API requires the 'T':
    start_time = request.form['selected_datetime_utc'].replace(' ', 'T')
    end_time = (datetime.fromisoformat(start_time) + timedelta(minutes=30)).isoformat()
    # Create meeting resource with the googleapiclient:
    try:
        meeting = booking_service.BookingService({request.form['booking_name']: request.form['booking_email']}, {"start": f"{start_time}",
        "end": f"{end_time}"}, 'Coaching Call')
    except HttpError as e:
        raise # re-raise the error to be caught by the error-handler
    # Will execute if no exception is raised
    else:
        # Book appointment in database for local storage
        if g.db.insert_booking(start_time, end_time):
            logger.info("Booking submitted.")
        else:
            logger.error("Booking insertion  in db failed.")
        # Show success if google api was successful
        flash("Appointment booked", "success")
    
    url = meeting.event_states.get('htmlLink')
    # Pass event url from API response as query parameter
    return redirect(url_for('booking_confirmation', event_states=url))

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

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    pass
    coaching_call = "price_1R6LuhH8d4CYhArR8yogdHvb"

@app.route('/session-status', methods=['GET'])
def session_status():
    session = stripe.checkout.Session.retrieve(request.args.get('session_id'))
    return jsonify(status=session.status, customer_email=session.customer_details.email)

# Web-hook route
# Use the secret provided by Stripe CLI for local testing
# or your webhook endpoint's secret.
endpoint_secret = 'whsec_...'

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        # Verify the Stripe webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError:
        # Invalid payload
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return jsonify({"error": "Invalid signature"}), 400

    # Handle the event when checkout is completed
    if event["type"] in ["checkout.session.completed", "checkout.session.async_payment_succeeded"]:
        fulfill_checkout(event["data"]["object"]["id"])

    return jsonify({"status": "success"}), 200

# Fulfillment function
def fulfill_checkout(session_id):
    print("Fulfilling Checkout Session", session_id)

    # TODO: Make this function safe to run multiple times,
    # even concurrently, with the same session ID

    # TODO: Make sure fulfillment hasn't already been
    # peformed for this Checkout Session

    # Retrieve the Checkout Session from the API with line_items expanded
    checkout_session = stripe.checkout.Session.retrieve(session_id, expand=['line_items'],)

    # Check the Checkout Session's payment_status property
    # to determine if fulfillment should be peformed
    if checkout_session.payment_status != 'unpaid':
        # TODO: Perform fulfillment of the line items

        # TODO: Record/save fulfillment status for this
        # Checkout Session
        pass

@app.route('/return', methods=['GET'])
def checkout_return():
    return render_template('return.html')

@app.route('/checkout', methods=['GET'])
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
    