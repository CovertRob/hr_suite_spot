from flask import Flask, render_template, request, jsonify, flash, redirect, g
import secrets
from booking import database # This is the database persistance module, all interactions with google calendar API module should take place here

from booking import booking_utils as util

def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    with app.app_context():
        g.database = database.DatabasePersistence()
    return app

app = create_app()

# Landing page
@app.route("/")
def index():
    title = "HR Suite Spot"
    return render_template('index_2.html', title = title)

# Description page about Jasmin
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

@app.route("/calendar", methods=['GET'])
def get_calendar():
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return render_template('calendar.html', days_of_week=days_of_week)

@app.route("/calendar", methods=["POST"])
def submit_availability():
    availability = request.form
    # Need to check / sanitize input here, create util function
    # Currently only implementing one main avail period per day
    
    # With MultiDict type, use getlist to create a list for each day of the week with the begin and end time periods. Ex: {"Monday": ['begin', 'end']}
    if not util.validate_availability_input_format(availability):
        flash("Availability is not formatted correctly.", "error")
        return redirect('/calendar')
    # Convert to official ISO-format and verify no inputs in past
    converted_input = util.convert_to_iso_with_tz(availability)
    print(converted_input)

    #g.db.insert_availability(availability)
    flash("Availability submitted", "succcess")
    return redirect('/calendar')

@app.errorhandler(404)
def error_handler(error):
    flash(f"{error}", "error")
    return redirect("/")

if __name__ == '__main__':
    app.run(debug=True, port=5003)