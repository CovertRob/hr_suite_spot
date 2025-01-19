import psycopg2
from psycopg2.extras import DictCursor
from contextlib import contextmanager
import logging
import os

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

class DatabasePersistence:
    def __init__(self):
        self._setup_schema()
        # Store id's for days of the week from database upon initial setup since they are used throughout the module to reduce n+1 queries.
        # Stored in dictionary format {"Monday": 1}
        self._days_of_week_ids = self._identify_days_of_week_ids()

    @contextmanager
    def _database_connect(self):
        """
        Internal function to manage the Postgres database connections. 
        Must include environment variable for database url path when deploying to production.
        """
        if os.environ.get('FLASK_ENV') == 'production':
            connection = psycopg2.connect(os.environ['DATABASE_URL'])
        else:
            connection = psycopg2.connect(dbname='booking_calendar')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _identify_days_of_week_ids(self):
        """
        Internally used to identify the id's from the database for the days of the week since sequences in local database are not guaranteed to be sequential due to Postgres sequence/nextval behavior.
        """
        query = "SELECT day_of_week, id FROM availability_day"
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query)
                # Key values here are "day_of_week" and "id" respectively
                ids = cursor.fetchall()
        # Extract id's into regular dictionary
        ids_to_dict = {pair['day_of_week']: pair['id'] for pair in ids}
        return ids_to_dict

    def find_todos_for_list(self, list_id):
        query = "SELECT * FROM todos WHERE list_id = %s"
        logger.info("Executing query: %s with list_id: %s", query, list_id)
        with self._database_connect() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query, (list_id,))
                return cursor.fetchall()

    def insert_availability(self, availability: dict):
        """
        Inserts the availability given for each day of the week into the local database for storage and display for appointment booking.

        Does not interact outside of the local environment. Connections to external google cloud calenar API are handled in the external calendar module.

        Returns True if insert successful, false otherwise
        """
        
        # Define query to insert parameters
        query = "INSERT INTO availability_period (begin_period, end_period, availability_day_id) VALUES (%s, %s, %s)"
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                for day, period in availability.items():
                    begin_period, end_period = period
                    # Use a try-catch to return false if any of the availability inserts fail so not to interrup user session
                    try:
                        cursor.execute(query, (begin_period, end_period, self._days_of_week_ids.get(f"{day}")))
                    except psycopg2.DatabaseError:
                        return False
        return True
            
    def _setup_schema(self):
        """
        Internal function to set-up the database schema if the tables do not exist. Primarily used when being deployed in production.
        """
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'availability_day';
                """)
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        CREATE TABLE availability_day (
                        id serial PRIMARY KEY,
                        day_of_week text NOT NULL);
                    """)
                    cursor.execute("""
                            INSERT INTO availability_day 
                                   (day_of_week) VALUES
                                   ('Monday'), ('Tuesday'),
                                   ('Wednesday'), ('Thursday'),
                                   ('Friday'), ('Saturday'),
                                   ('Sunday');
                                """)
                
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'availability_period';
                """)
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                            CREATE TABLE availability_period (
                                id serial PRIMARY KEY NOT NULL,
                                begin_period timestamp with time zone NOT NULL,
                                end_period timestamp with time zone NOT NULL,
                                availability_day_id integer NOT NULL REFERENCES availability_day (id),
                                is_booked boolean DEFAULT false
                                );""")
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'bookings';
                """)
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                                   CREATE TABLE bookings (
                                   id serial PRIMARY KEY,
                                   availability_period_id integer NOT NULL REFERENCES availability_period (id));
                                   """)

# For testing:

if __name__ == "__main__":
    test = DatabasePersistence()