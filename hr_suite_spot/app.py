from flask import Flask, render_template, request, jsonify, flash, redirect, g
import secrets
from booking import database # This is the database persistance module, all interactions with google calendar API module should take place here
from booking import error_utils
from booking import booking_utils as util
from functools import wraps

def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    return app

app = create_app()

# This is an issue right now becuase it's executing multiple queries when instantiating before every request. Need to figure out decorator.
@app.before_request
def instantiate_database():
    g.db = database.DatabasePersistence()

# Use decorator to create g.db instance within request context window for functions that require it to conserve resources
# def instantiate_database(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         with app.app_context():
#             g.db = database.DatabasePersistence()
#         return f(*args, **kwargs)
#     return decorated_function

# Create a custom decorator to iniitialize the db class in globabl g for prior to running the functions that neeed them.

# Landing page
@app.route("/")
def index():
    title = "HR Suite Spot"
    return render_template('index_2.html', title = title)

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

@app.route("/calendar", methods=["POST"])
# @instantiate_database currently throwing out of context error
def submit_availability():
    availability = request.form
    # Need to check / sanitize input here, create util function
    # Currently only implementing one main avail period per day
    
    # With MultiDict type, use getlist to create a list for each day of the week with the begin and end time periods. Ex: {"Monday": ['begin', 'end']}
    if not util.validate_availability_input_format(availability):
        flash("Availability is not formatted correctly.", "error")
        return redirect('/calendar')
    # Convert to official ISO-format and verify no inputs in past
    # Use try-catch block with convert_to_iso_with_tz
    try:
        converted_input = util.convert_to_iso_with_tz(availability)
    except error_utils.TimeValidationError as e:
        message = e.args[0] # arg 0 should be the message
        flash(f"{message}", "error")
        return redirect('/calendar')

    # Insert the availability into the local database for each day of the week
    # If fails, logs database error and returns false
    if g.db.insert_availability(converted_input):
        flash("Availability submitted", "succcess")
    else:
        flash("Availability insertion failed, probably due to format", "error")
        return redirect('/calendar')
    return redirect('/calendar')

@app.errorhandler(404)
def error_handler(error):
    flash(f"{error}", "An error occurred.")
    return redirect("/")

if __name__ == '__main__':
    # util.generate_booking_slots()
    app.run(debug=True, port=5003)
    