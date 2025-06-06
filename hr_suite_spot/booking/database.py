from uuid import UUID
import psycopg2
from psycopg2.extras import DictCursor
from contextlib import contextmanager
import logging
import os
from werkzeug.datastructures import MultiDict
from pprint import pprint
from typing import Dict
from uuid import uuid4

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

class DatabasePersistence:
    def __init__(self):
        self._setup_schema()
        # remove call to get days of week id's

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

    def insert_availability(self, availability: list):
        """
        Inserts the availability into the local database for storage and display for appointment booking.

        Does not interact outside of the local environment. Connections to external google cloud calenar API are handled in the external calendar module.

        Returns True if insert successful, false otherwise
        """
        # Insertion query
        query = "INSERT INTO availability_period (begin_period, end_period) VALUES (%s, %s) ON CONFLICT DO NOTHING;"
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                for slots in availability:
                    pprint(slots)
                    try:
                        cursor.execute(query, (slots[0], slots[1]))
                    except psycopg2.DatabaseError as e:
                        logger.info("Insertion failed with error: %s", e.args)
                        return False
        return True
    
    def delete_availability_by_id(self, availability_id: int):
        """
        Deletes a single availability by it's unique id.
        """
        query = """DELETE FROM availability_period WHERE id = %s"""
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")
                try:
                    cursor.execute(query, (availability_id))
                except psycopg2.DatabaseError as e:
                    logger.error(f"Booking deletion failed: {e.args}")
                    return False
        return True      
    
    def delete_availability_range(self, start: str, end: str):
        """
        Deletes availability periods based on a given date range.
        start and end are both ISO-8601 strings
        """
        query =     """DELETE FROM availability_period
                        WHERE begin_period >= %s
                        AND end_period   <=  %s
                        AND is_booked    = FALSE;"""
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")
                try:
                    cursor.execute(query, (start, end))
                except psycopg2.DatabaseError as e:
                    logger.error(f"Booking deletion failed: {e.args}")
                    return False
        return True
    
    def delete_all_availability(self):
        """
        Deletes all availability in the db except for booked slots.
        """
        query = """DELETE FROM availability_period
                    WHERE is_booked = FALSE"""
        logger.info("Executing query: %s", query)
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TIME ZONE 'UTC'")
                try:
                    cursor.execute(query)
                except psycopg2.DatabaseError as e:
                    logger.error(f"Booking deletion failed: {e.args}")
                    return False
        return True
    
    def retrieve_availability_periods(self):
        """
        Gets the stored availability periods that user input. 

        Returns raw table data in DictRow format.
        """
        query = 'SELECT id, begin_period AS start, end_period AS end FROM availability_period WHERE is_booked = FALSE AND begin_period > NOW() GROUP BY id, begin_period, end_period'
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
    
    def acquire_hold(self, slot_id):
        """Try to place a hold; return token or None."""
        token = str(uuid4())
        INITIAL_HOLD_SEC = 60
        query = """
                SELECT id
                FROM availability_period
                WHERE id = %s
                AND is_booked = FALSE
                AND (locked_until IS NULL OR locked_until < NOW())
                FOR UPDATE SKIP LOCKED
            """
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, (slot_id,))
                    if cursor.fetchone() is None: # If none, its being held
                        return None
                except psycopg2.DatabaseError as e:
                    logger.error(f"Acquire hold query failed: {e.args}")
                    return None
            # Place the hold if not none
                else:
                    cursor.execute("""
                        UPDATE availability_period
                        SET locked_until = NOW() + INTERVAL %s,
                            hold_token   = %s
                        WHERE id = %s
                    """, (f"{INITIAL_HOLD_SEC} seconds", token, slot_id))
        return token

    def extend_hold(self, slot_id, token):
        """Return True if successful hold extended, otherwise false."""
        query = """
                UPDATE availability_period
                SET locked_until = NOW() + INTERVAL %s
                WHERE id = %s AND hold_token = %s AND is_booked = FALSE
            """
        HOLD_EXTENSION_SEC = str(30)
        logger.info(f"Executing query: {query} with args: {slot_id} {token}")
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, (f"{HOLD_EXTENSION_SEC} seconds", slot_id, token))
                    return True
                except psycopg2.DatabaseError as e:
                    logger.error(f"Extend hold query failed: {e.args}")
                    return False
        return False

    def release_hold(self, slot_id, token):
        """Return True if hold successfully released, otherwise false."""
        query = """
                UPDATE availability_period
                SET locked_until = NULL,
                    hold_token   = NULL
                WHERE id = %s AND hold_token = %s AND is_booked = FALSE
            """
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(query, (slot_id, token))
                    return True
                except psycopg2.DatabaseError as e:
                    logger.error(f"Fulfillment insertion failed: {e.args}")
                    return False
        return False

    # Need to run testing to ensure database created from this matches local environment
    def _setup_schema(self):
        """
        Internal function to set-up the database schema if the tables do not exist. Primarily used when being deployed in production.
        """
        with self._database_connect() as conn:
            with conn.cursor() as cursor:
                # Remove availability day table
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
                                is_booked boolean DEFAULT false,
                                client_ref_id UUID REFERENCES product_fulfillments(client_ref_id),
                                locked_until TIMESTAMPTZ,
                                hold_token TEXT,
                                CONSTRAINT unique_meeting_datetime UNIQUE (begin_period, end_period)
                                );""")                
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

# For testing:

if __name__ == "__main__":
    test = DatabasePersistence()
    test.retrieve_availability_periods()