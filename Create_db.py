import psycopg2

# PostgreSQL connection configuration
conn = psycopg2.connect(
    dbname="FlightDB",
    user="postgres",
    password="root",
    host="localhost",
    port="5432"
)

# Create tables
def create_tables():
    commands = (
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            phone_number VARCHAR(20),
            password VARCHAR(255) NOT NULL,
            notification_preference VARCHAR(20),
            flights_list INTEGER[] -- Array of flight IDs
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS flights (
            id SERIAL PRIMARY KEY,
            flight_number VARCHAR(10) NOT NULL,
            airline VARCHAR(50),
            departure VARCHAR(50),
            arrival VARCHAR(50),
            date DATE,
            status VARCHAR(20),
            gate_no VARCHAR(10),
            delay VARCHAR(10),
            cancellation VARCHAR(10)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS previous_flight_status (
            email VARCHAR(255) NOT NULL,
            flight_number VARCHAR(10) NOT NULL,
            status VARCHAR(20),
            gate_no VARCHAR(10),
            delay VARCHAR(10),
            cancellation VARCHAR(10),
            PRIMARY KEY (email, flight_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users (id),
            flight_id INTEGER NOT NULL REFERENCES flights (id)
        )
        """
    )
    print('in create table')

    try:
        with conn.cursor() as cursor:
            for command in commands:
                cursor.execute(command)
            conn.commit()
        print("Tables created successfully.")
    except Exception as e:
        print(f"Error creating tables: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    create_tables()
