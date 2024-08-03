from flask import Flask, request, jsonify, render_template
import psycopg2
from psycopg2 import sql
from twilio.rest import Client
import smtplib
from email.mime.text import MIMEText
from confluent_kafka import Producer
import json
import bcrypt 
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
print("in app");
os.system("python Create_db.py")
# PostgreSQL connection configuration
try:
    conn = psycopg2.connect(
        dbname="FlightDB",
        user="postgres",
        password="root",
        host="localhost",
        port="5432"
    )
    print("Database connection successful")
except Exception as e:
    print(f"Error connecting to database: {e}")

# Twilio configuration
TWILIO_SID = 'your-twilio-sid'
TWILIO_AUTH_TOKEN = 'your-twilio-auth-token'
TWILIO_PHONE_NUMBER = 'your-twilio-phone-number'

# Kafka configuration
KAFKA_BROKER = 'localhost:9092'
KAFKA_TOPIC = 'flight-status-notifications'

def send_sms(phone_number, message):
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=message,
        from_=TWILIO_PHONE_NUMBER,
        to=phone_number
    )

def send_email(email_address, subject, body):
    sender_email = 'your-email@example.com'
    password = 'your-email-password'
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = email_address
    
    with smtplib.SMTP('smtp.example.com', 587) as server:
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, email_address, msg.as_string())

def send_kafka_notification(user_email, message):
    producer = Producer({'bootstrap.servers': KAFKA_BROKER})
    producer.produce(KAFKA_TOPIC, key=user_email, value=json.dumps({'message': message}))
    producer.flush()

def get_flight_status(user_email):
    with conn.cursor() as cursor:
        cursor.execute("SELECT flight_number, status, gate_no, arriving, delay, cancellation FROM flights WHERE email = %s", (user_email,))
        return cursor.fetchall()

def get_previous_flight_status(user_email):
    with conn.cursor() as cursor:
        cursor.execute("SELECT flight_number, status, gate_no, delay, cancellation FROM previous_flight_status WHERE email = %s", (user_email,))
        return cursor.fetchall()

def update_previous_flight_status(user_email, flight_statuses):
    with conn.cursor() as cursor:
        for flight in flight_statuses:
            flight_number, status, gate_no, arriving, delay, cancellation = flight
            cursor.execute("""
                INSERT INTO previous_flight_status (email, flight_number, status, gate_no, delay, cancellation)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (email, flight_number)
                DO UPDATE SET status = EXCLUDED.status, gate_no = EXCLUDED.gate_no, delay = EXCLUDED.delay, cancellation = EXCLUDED.cancellation
            """, (user_email, flight_number, status, gate_no, delay, cancellation))
        conn.commit()

def get_user_details(user_email):
    with conn.cursor() as cursor:
        cursor.execute("SELECT phone_number, email FROM users WHERE email = %s", (user_email,))
        return cursor.fetchone()

def update_notification_preference():
    with conn.cursor() as cursor:
        cursor.execute("SELECT email, notification_preference FROM users")
        users = cursor.fetchall()

    for user_email, preference in users:
        # Fetch current flight status for the user
        current_flights = get_flight_status(user_email)

        # Fetch previous flight status for comparison
        previous_flights = get_previous_flight_status(user_email)

        # Track whether any changes have occurred
        notifications_sent = False

        for current_flight in current_flights:
            flight_number = current_flight[0]
            current_status = current_flight[1]
            current_gate_no = current_flight[2]
            current_delay = current_flight[4]
            current_cancellation = current_flight[5]

            # Find corresponding previous flight status
            previous_flight = next((f for f in previous_flights if f[0] == flight_number), None)
            
            if previous_flight:
                prev_status, prev_gate_no, prev_delay, prev_cancellation = previous_flight[1:]
            else:
                prev_status = prev_gate_no = prev_delay = prev_cancellation = None

            # Check for any changes
            if (current_status != prev_status or
                current_gate_no != prev_gate_no or
                current_delay != prev_delay or
                current_cancellation != prev_cancellation):

                message = f"Flight {flight_number} has an update: Status={current_status}, Gate No={current_gate_no}, Delay={current_delay}, Cancellation={current_cancellation}"
                
                # Retrieve user details
                user_details = get_user_details(user_email)
                phone_number = user_details[0]
                email_address = user_details[1]
                
                if preference == 'sms' and phone_number:
                    send_sms(phone_number, message)
                elif preference == 'email' and email_address:
                    send_email(email_address, "Flight Status Update", message)
                elif preference == 'in-app':
                    send_kafka_notification(user_email, message)

                notifications_sent = True

        # Update previous flight status with current data
        update_previous_flight_status(user_email, current_flights)

    return notifications_sent

@app.route('/more-option-flight-details', methods=['GET'])
def more_option_flight_details():
    departure = request.args.get('departure', '').strip()
    arrival = request.args.get('arrival', '').strip()
    airline = request.args.get('airline', '').strip()
    date = request.args.get('date', '').strip()

    # Validate the required date field
    if not date:
        return jsonify({'error': 'Date is required'}), 400

    # Build query dynamically based on provided filters
    query = "SELECT * FROM flights WHERE date = %s"
    params = [date]

    if departure:
        query += " AND departure = %s"
        params.append(departure)

    if arrival:
        query += " AND arrival = %s"
        params.append(arrival)

    if airline:
        query += " AND airline = %s"
        params.append(airline)

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            flights = cursor.fetchall()

            # If no flights found, return a message
            if not flights:
                return jsonify({'message': 'No flights found matching the criteria'}), 404

            # Construct response
            flights_list = []
            for flight in flights:
                flights_list.append({
                    'flight_number': flight[0],
                    'airline': flight[1],
                    'departure': flight[2],
                    'arrival': flight[3],
                    'date': flight[4],
                    'status': flight[5],
                    'gate': flight[6],
                    'delay': flight[7],
                    'cancellation': flight[8]
                })

            return jsonify(flights_list)

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'An error occurred while fetching flight details'}), 500

@app.route('/flight-details', methods=['GET'])
def flight_details():
 
    flight_number = request.args.get('flightNumber', '').strip()
    airline = request.args.get('airline', '').strip()
    date = request.args.get('date', '').strip()
    print('inside details');
  
    if not date:
        return jsonify({'error': 'Date is required'}), 400

    query = "SELECT * FROM flights WHERE date = %s"
    params = [date]

    if flight_number:
        query += " AND flight_number = %s"
        params.append(flight_number)

    if airline:
        query += " AND airline = %s"
        params.append(airline)

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            flights = cursor.fetchall()

            if not flights:
                return jsonify({'message': 'No flights found matching the criteria'}), 404

            flights_list = []
            for flight in flights:
                flights_list.append({
                    'flight_number': flight[0],
                    'airline': flight[1],
                    'departure': flight[2],
                    'arrival': flight[3],
                    'date': flight[4],
                    'status': flight[5],
                    'gate': flight[6],
                    'delay': flight[7],
                    'cancellation': flight[8]
                })

            return jsonify(flights_list)

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'An error occurred while fetching flight details'}), 500

@app.route('/update-notification', methods=['POST'])
def update_notification_preference_route():
    data = request.json
    user_email = data.get('email')
    preference = data.get('preference')

    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET notification_preference = %s WHERE email = %s", (preference, user_email))
        conn.commit()

    # Check and notify about flight status if preference is updated
    update_notification_preference()


@app.route('/get-flight-status', methods=['POST'])
def get_flight_st():
    data = request.json
    email = data.get('email')  # Get the email from the request

    try:
        with conn.cursor() as cursor:
            # Join flights with bookings to get only the user's flights
            query = sql.SQL("""
                SELECT flights.flight_number, flights.status, flights.gate_no, flights.arrival, flights.delay, flights.cancellation
                FROM flights
                JOIN bookings ON flights.id = bookings.flight_id
                JOIN users ON bookings.user_id = users.id
                WHERE users.email = %s
            """)
            cursor.execute(query, (email,))
            flights = cursor.fetchall()

        return jsonify(flights), 200
    except Exception as e:
        print(e)
        return jsonify({'error': 'Error fetching flight status'}), 500
        
@app.route('/submit-form', methods=['POST'])
def submit_form():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    phone_number = data.get('phoneNumber')
    password = data.get('password')
    notification_preference = data.get('notificationPreference')
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    hashed_password=hashed_password.decode('utf-8')
    try:
        with conn.cursor() as cursor:
            insert_query = sql.SQL("""
                INSERT INTO users (name, email, phone_number, password, notification_preference,flights_list)
                VALUES (%s, %s, %s, %s, %s,%s)
            """)
            cursor.execute(insert_query, (name, email, phone_number, hashed_password, notification_preference,[]))
            conn.commit()
        return jsonify({'message': 'Data added successfully'}), 201
    except Exception as e:
        print(e)
        return jsonify({'error': 'Error adding data'}), 500

@app.route('/update-notification-preference', methods=['POST'])
def update_notification_preference():
    data = request.json
    user_email = data.get('email')
    preference = data.get('preference')

    # Update the user's notification preference in the database
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET notification_preference = %s WHERE email = %s", (preference, user_email))
        conn.commit()

    # Fetch flight status for the user
    flights = get_flight_st(user_email)

    # Send notifications based on updated preference
    for flight in flights:
        flight_number, status, gate_no, arriving, delay, cancellation = flight
        message = f"Flight {flight_number} has an update: Status={status}, Gate No={gate_no}, Arriving={arriving}, Delay={delay}, Cancellation={cancellation}"
        
        if preference == 'sms':
            phone_number = get_user_phone_number(user_email)  # Ensure this function returns the phone number for the user
            send_sms(phone_number, message)
        elif preference == 'email':
            send_email(user_email, "Flight Status Update", message)
        elif preference == 'in-app':
            send_kafka_notification(user_email, message)

    return jsonify({'message': 'Notification preference updated and notifications sent successfully'})


@app.route('/login-user', methods=['POST'])
def login_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    try:
        with conn.cursor() as cursor:
            query = sql.SQL("""
                SELECT password FROM users WHERE email = %s
            """)
            cursor.execute(query, (email,))
            result = cursor.fetchone();
            
            if result:
                stored_password = result[0].encode('utf-8')  # Ensure proper encoding

                # Check if the stored password matches the provided password
                if bcrypt.checkpw(password.encode('utf-8'), stored_password):
                    return jsonify({'email': email}), 200
                else:
                    return jsonify({'error': 'Invalid credentials'}), 401
            else:
                return jsonify({'error': 'User not found'}), 404
                
    except Exception as e:
        print(e)
        return jsonify({'error': 'Error logging in'}), 500
if __name__ == '__main__':
    app.run(debug=True,port=5000)



