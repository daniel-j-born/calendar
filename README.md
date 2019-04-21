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

Install files as they are arranged in the project. Something like:

```
chelation_calendar.py
passenger_wsgi.py
repeating_ical_events_flask.py
repeating_ical_events.py
static/repeating_ical_forms.js
static/style.css
templates/error.html
templates/index.html
```

# TODO

* Maybe some kind of border in the form table so the labels line up with the
  inputs.
* Change the orientation so the inputs are to the left of labels.
* Make repository public.
