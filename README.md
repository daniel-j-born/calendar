# Repeating iCalendar Events Generator

Most calendar applications do not support hourly or other granularities of
repeating events of less than a day. This project contains a web application
that will generate an iCalendar ([RFC
5545](https://tools.ietf.org/html/rfc5545), .ics files) file for the given
scheduling specifications. This .ics file can be imported into calendar
applications.

# Requirements

* Python3.6 or later

* Python modules:
  - flask
  - icalendar

# Installation

Install files as they are arranged in the project. Something like:

```
js/repeating_ical_forms.js
templates/index.html
chelation_calendar.py
passenger_wsgi.py
repeating_ical_events.py
```
