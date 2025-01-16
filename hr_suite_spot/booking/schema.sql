--
-- PostgreSQL database dump
--

-- Dumped from database version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.15 (Ubuntu 14.15-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: availability_day; Type: TABLE; Schema: public; Owner: robert_feconda
--

CREATE TABLE public.availability_day (
    id integer NOT NULL,
    day_of_week text NOT NULL
);


ALTER TABLE public.availability_day OWNER TO robert_feconda;

--
-- Name: availability_day_id_seq; Type: SEQUENCE; Schema: public; Owner: robert_feconda
--

CREATE SEQUENCE public.availability_day_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.availability_day_id_seq OWNER TO robert_feconda;

--
-- Name: availability_day_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: robert_feconda
--

ALTER SEQUENCE public.availability_day_id_seq OWNED BY public.availability_day.id;


--
-- Name: availability_period; Type: TABLE; Schema: public; Owner: robert_feconda
--

CREATE TABLE public.availability_period (
    id integer NOT NULL,
    begin_period timestamp with time zone NOT NULL,
    end_period timestamp with time zone NOT NULL,
    availability_day_id integer NOT NULL,
    is_booked boolean DEFAULT false
);


ALTER TABLE public.availability_period OWNER TO robert_feconda;

--
-- Name: availability_period_id_seq; Type: SEQUENCE; Schema: public; Owner: robert_feconda
--

CREATE SEQUENCE public.availability_period_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.availability_period_id_seq OWNER TO robert_feconda;

--
-- Name: availability_period_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: robert_feconda
--

ALTER SEQUENCE public.availability_period_id_seq OWNED BY public.availability_period.id;


--
-- Name: bookings; Type: TABLE; Schema: public; Owner: robert_feconda
--

CREATE TABLE public.bookings (
    id integer NOT NULL,
    availability_period_id integer NOT NULL
);


ALTER TABLE public.bookings OWNER TO robert_feconda;

--
-- Name: bookings_id_seq; Type: SEQUENCE; Schema: public; Owner: robert_feconda
--

CREATE SEQUENCE public.bookings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.bookings_id_seq OWNER TO robert_feconda;

--
-- Name: bookings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: robert_feconda
--

ALTER SEQUENCE public.bookings_id_seq OWNED BY public.bookings.id;


--
-- Name: availability_day id; Type: DEFAULT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_day ALTER COLUMN id SET DEFAULT nextval('public.availability_day_id_seq'::regclass);


--
-- Name: availability_period id; Type: DEFAULT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_period ALTER COLUMN id SET DEFAULT nextval('public.availability_period_id_seq'::regclass);


--
-- Name: bookings id; Type: DEFAULT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.bookings ALTER COLUMN id SET DEFAULT nextval('public.bookings_id_seq'::regclass);


--
-- Name: availability_day availability_day_day_of_week_key; Type: CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_day
    ADD CONSTRAINT availability_day_day_of_week_key UNIQUE (day_of_week);


--
-- Name: availability_day availability_day_pkey; Type: CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_day
    ADD CONSTRAINT availability_day_pkey PRIMARY KEY (id);


--
-- Name: availability_period availability_period_begin_period_end_period_key; Type: CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_period
    ADD CONSTRAINT availability_period_begin_period_end_period_key UNIQUE (begin_period, end_period);


--
-- Name: availability_period availability_period_pkey; Type: CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_period
    ADD CONSTRAINT availability_period_pkey PRIMARY KEY (id);


--
-- Name: bookings bookings_availability_period_id_key; Type: CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.bookings
    ADD CONSTRAINT bookings_availability_period_id_key UNIQUE (availability_period_id);


--
-- Name: bookings bookings_pkey; Type: CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.bookings
    ADD CONSTRAINT bookings_pkey PRIMARY KEY (id);


--
-- Name: availability_period availability_period_availability_day_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.availability_period
    ADD CONSTRAINT availability_period_availability_day_id_fkey FOREIGN KEY (availability_day_id) REFERENCES public.availability_day(id);


--
-- Name: bookings bookings_availability_period_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: robert_feconda
--

ALTER TABLE ONLY public.bookings
    ADD CONSTRAINT bookings_availability_period_id_fkey FOREIGN KEY (availability_period_id) REFERENCES public.availability_period(id);


--
-- PostgreSQL database dump complete
--

