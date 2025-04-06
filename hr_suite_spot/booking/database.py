from uuid import UUID
import psycopg2
from psycopg2.extras import DictCursor
from contextlib import contextmanager
import logging
import os
from werkzeug.datastructures import MultiDict
from pprint import pprint
from typing import Dict

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

    def insert_availability(self, availability: MultiDict):
        """
        Inserts the availability given for each day of the week into the local database for storage and display for appointment booking.

        Does not interact outside of the local environment. Connections to external google cloud calenar API are handled in the external calendar module.

        Returns True if insert successful, false otherwise
        """

        # To-do: Database needs to overwrite availability for a given day of the week when data is resubmitted by user
        
        # Define query to insert parameters
        query = "SELECT input_or_replace_availability(%s, %s, %s)"
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                for day_of_week, appointments in availability.items(multi=True):
                    for slot in appointments:
                        begin_period, end_period = slot
                        # Use a try-catch to return false if any of the availability inserts fail so not to interrup user session
                        try:
                            cursor.execute(query, (begin_period, end_period, self._days_of_week_ids.get(f"{day_of_week}"))) # Future - remove n +1 query
                        except psycopg2.DatabaseError as e:
                            logger.info("Insertion failed with error: %s", e.args)
                            return False
        return True
    
    def retrieve_availability_periods(self):
        """
        Gets the stored availability periods that user input. 

        Returns raw table data in DictRow format.
        """
        query = 'SELECT day_of_week, begin_period AS start, end_period AS end FROM availability_period JOIN availability_day ON availability_day_id = availability_day.id WHERE is_booked = FALSE GROUP BY availability_day_id, day_of_week, begin_period, end_period ORDER BY availability_day_id'
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                # Must set time zone here for each connection
                cursor.execute("SET TIME ZONE 'UTC';")
                cursor.execute(query)
                availability_data = cursor.fetchall()
        return availability_data

    def insert_booking(self, start, end, client_ref_id=None):
        """
        Marks a booking period in the availability_period table as booked by marking the 'is_booked' column value as True.
        Inserts the UUID if passed otherwise Null
        """
        pprint(start)
        pprint(end)
        query = """UPDATE availability_period SET is_booked = TRUE, client_ref_id = %s WHERE begin_period = %s AND end_period = %s;"""
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")
                try:
                    cursor.execute(query, (client_ref_id, start, end))
                except psycopg2.DatabaseError as e:
                    logger.error(f"Booking insertion failed: {e.args}")
                    return False
        return True

    def insert_fulfillment(self, ref_id: UUID, meta_data: Dict[str, str], fulfillment_status=False):
        query = """INSERT INTO product_fulfillments (client_ref_id, meta_data, is_fulfilled) VALUES (%s, %s, %s)"""
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")
                try:
                    cursor.execute(query, (ref_id, meta_data, fulfillment_status))
                except psycopg2.DatabaseError as e:
                    logger.error(f"Fulfillment insertion failed: {e.args}")
                    return False
        return True
    
    def check_or_insert_fulfillment(self, ref_id: UUID, meta_data: str, fulfillment_status) -> bool:
        query = "SELECT check_or_insert_fulfillment(%s, %s, %s)"
        logger.info("Executing query: %s", query)
        fulfillment_status_from_function = False
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, (ref_id, meta_data, fulfillment_status))
                    fulfillment_status_from_function = cursor.fetchone()[0] # Should be True or False
                except psycopg2.DatabaseError as e:
                    logger.error(f"Fulfillment insertion failed: {e.args}")
                    return False        
        return fulfillment_status_from_function

    # Need to run testing to ensure database created from this matches local environment
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
                    logger.info("Setting up the schema.")
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
                    WHERE table_schema = 'public' AND table_name = 'product_fulfillments';
                """)
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""CREATE TABLE product_fulfillments (
                                id serial PRIMARY KEY NOT NULL,
                                created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
                                client_ref_id UUID UNIQUE NOT NULL,
                                meta_data JSONB NOT NULL,
                                is_fulfilled boolean DEFAULT false
                                );""")
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
                                is_booked boolean DEFAULT false,
                                client_ref_id UUID REFERENCES product_fulfillments(client_ref_id)
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
                self._setup_availability_period_function(cursor)
                self._setup_purchase_fulfillment_function(cursor)
                self._setup_booking_to_fulfillment_trigger(cursor)
                # Set as UTC so we retrieve data in UTC for conversion on front-end
                # Don't think this really changes anything bc timezone is dependent on each cursor connection but I'm going to leave it for good measure
                cursor.execute("SET TIME ZONE 'UTC';")

    def _setup_booking_to_fulfillment_trigger(self, cursor):
        check_function_query = """
                                SELECT EXISTS (
                                SELECT 1
                                FROM pg_proc
                                JOIN pg_namespace ON pg_proc.pronamespace = pg_namespace.oid
                                WHERE proname = %s AND nspname = %s);
                                """
        function_name = 'update_fulfillment_on_booking'
        schema_name = 'public'
        # Check if the function exists within the database
        cursor.execute(check_function_query, (function_name, schema_name))
        function_exists = cursor.fetchone()[0]
        if not function_exists:
            create_function_query = """
            CREATE OR REPLACE FUNCTION update_fulfillment_on_booking()
            RETURNS TRIGGER AS $$
            BEGIN
                -- Only proceed if the new status is booked, and it wasn't booked before
                IF NEW.is_booked = TRUE AND OLD.is_booked IS DISTINCT FROM TRUE THEN
                    UPDATE product_fulfillments
                    SET is_fulfilled = TRUE
                    WHERE client_ref_id = NEW.client_ref_id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;"""
            create_trigger_query = """
            CREATE TRIGGER trigger_fulfillment_on_booking
            AFTER UPDATE ON availability_period
            FOR EACH ROW
            WHEN (OLD.is_booked IS DISTINCT FROM NEW.is_booked)
            EXECUTE FUNCTION update_fulfillment_on_booking();"""
            cursor.execute(create_function_query)
            cursor.execute(create_trigger_query)

    def _setup_purchase_fulfillment_function(self, cursor):
        check_function_query = """
                                SELECT EXISTS (
                                SELECT 1
                                FROM pg_proc
                                JOIN pg_namespace ON pg_proc.pronamespace = pg_namespace.oid
                                WHERE proname = %s AND nspname = %s);
                                """
        function_name = 'check_or_insert_fulfillment'
        schema_name = 'public'
        # Check if the function exists within the database
        cursor.execute(check_function_query, (function_name, schema_name))
        function_exists = cursor.fetchone()[0]
        if not function_exists:
            create_function_query = """
            CREATE FUNCTION check_or_insert_fulfillment(p_client_ref_id UUID, p_meta_data JSONB, fulfillment_status BOOLEAN)
            RETURNS BOOLEAN AS $$
            DECLARE
                fulfilled_status BOOLEAN;
            BEGIN
                -- Try to insert, do nothing if conflict
                INSERT INTO product_fulfillments (client_ref_id, meta_data, is_fulfilled)
                VALUES (p_client_ref_id, p_meta_data, fulfillment_status)
                ON CONFLICT (client_ref_id) DO NOTHING;

                -- Now fetch the row (whether newly inserted or pre-existing)
                SELECT is_fulfilled INTO fulfilled_status
                FROM product_fulfillments
                WHERE client_ref_id = p_client_ref_id;

                RETURN fulfilled_status;
            END;
            $$ LANGUAGE plpgsql;"""
            cursor.execute(create_function_query)

    def _setup_availability_period_function(self, cursor):
        """set up the function to run in the database that will check if availability periods exist for a given day of the week or not and if they do it will delete and overwrite the data when user resubmits new data
        """
        check_function_query = """
                                SELECT EXISTS (
                                SELECT 1
                                FROM pg_proc
                                JOIN pg_namespace ON pg_proc.pronamespace = pg_namespace.oid
                                WHERE proname = %s AND nspname = %s);
                                """
        function_name = 'input_or_replace_availability'
        schema_name = 'public'
        # Check if the function exists within the database
        cursor.execute(check_function_query, (function_name, schema_name))
        function_exists = cursor.fetchone()[0]

        # If the function doesn't exist, create it
        # Build function to only handle one availability period at a time based on system design. Can re-factor to loop through entire availability in future
        if not function_exists:
            create_function_query = """
                CREATE FUNCTION input_or_replace_availability(
                    start_period timestamp with time zone,
                    finish_period timestamp with time zone,
                    day_of_week_id integer)
                    RETURNS VOID AS $$
                    BEGIN
                        -- Delete existing availability
                        DELETE FROM availability_period
                        WHERE availability_day_id = day_of_week_id
                        --prevent deletion of booked periods
                        AND is_booked = FALSE
                        -- Delete overlapping time periods
                        AND begin_period < finish_period
                        AND end_period > start_period;
                        -- Insert the new availability
                        INSERT INTO availability_period (begin_period, end_period, availability_day_id) VALUES (start_period, finish_period, day_of_week_id);
                    END;
                    $$ LANGUAGE plpgsql;
                                    """
            cursor.execute(create_function_query)

# For testing:

if __name__ == "__main__":
    test = DatabasePersistence()
    test.retrieve_availability_periods()