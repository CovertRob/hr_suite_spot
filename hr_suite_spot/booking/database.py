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

    @contextmanager
    def _database_connect(self):
        if os.environ.get('FLASK_ENV') == 'production':
            connection = psycopg2.connect(os.environ['DATABASE_URL'])
        else:
            connection = psycopg2.connect(dbname='booking_calendar')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def find_todos_for_list(self, list_id):
        query = "SELECT * FROM todos WHERE list_id = %s"
        logger.info("Executing query: %s with list_id: %s", query, list_id)
        with self._database_connect() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query, (list_id,))
                return cursor.fetchall()

    def insert_availability(self, availability: list):
        pass
            
    def _setup_schema(self):
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