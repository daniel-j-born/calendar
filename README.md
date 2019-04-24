# Repeating iCalendar Events Generator

Most calendar applications do not support hourly or other granularities for
repeating events of less than a day. This project contains a web application
that will generate an iCalendar ([RFC
5545](https://tools.ietf.org/html/rfc5545), .ics files) file to the given
scheduling specifications. This .ics file can be imported into calendar
applications like Google Calendar.

# Requirements

* Python 3.6 or later
* Python modules
  - icalendar
  - flask
  - wtforms

# Installation

`passenger_wsgi.py` defines the `application` object. Run it from your Python
server engine.
