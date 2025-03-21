from operator import mul
from flask import Flask, render_template, request, jsonify, flash, redirect, g
import secrets
from booking import database # This is the database persistance module, all interactions with google calendar API module should take place here
from booking import error_utils
from booking import booking_utils as util
from functools import wraps
from pprint import pprint
from werkzeug.datastructures import MultiDict

def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32) #256 bit
    return app

app = create_app()

# Use decorator to create g.db instance within request context window for functions that require it to conserve resources
def instantiate_database(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        g.db = database.DatabasePersistence()
        return f(*args, **kwargs)
    return decorated_function

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
    generated_availability = util.generate_availability(availability_data, reoccurring_data, 2)
    
    # Convert to official ISO-format and verify no inputs in past
    # Use try-catch block with convert_to_iso_with_tz
    try:
        converted_input = util.convert_to_iso_with_tz(generated_availability)
    except error_utils.TimeValidationError as e:
        message = e.message # get the message passed
        flash(f"{message}", "error")
        return redirect('/calendar')
    # Insert the availability into the local database for each day of the week
    # If fails, logs database error and returns false
    if g.db.insert_availability(converted_input):
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
def book_coaching_call():
    pass
    # Get availability periods from database
    util.generate_booking_slots()
    return render_template('booking.html')

@app.errorhandler(404)
def error_handler(error):
    flash(f"An error occurred.", "error")
    return redirect("/index")

# Add resume route

# Add Interview route

# Add Career Path route

if __name__ == '__main__':
    # util.generate_booking_slots()
    app.run(debug=True, port=5003)
    