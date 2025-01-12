from flask import Flask, render_template, request, jsonify
from booking import calendar

app = Flask(__name__)

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

@app.route("/calendar")
def get_calendar():
    return calendar.create_calendar()

if __name__ == '__main__':
    app.run(debug=True, port=5003)