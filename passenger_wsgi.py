# System modules
import flask
import os
import socket
import sys
import threading

# My modules
sys.path.insert(0, os.path.dirname(__file__))
import repeating_ical_events
import repeating_ical_events_flask

uid_gens = repeating_ical_events_flask.HostUidGen()
application = flask.Flask(__name__)

@application.route('/', methods=['GET', 'POST'])
def RepeatingIcalEvents():
  # Fix up path. Server interface passes '/', which is not correct. We need to
  # route '/' to get here and then fixup the path.
  flask.request.path = '/repeating_events'
  handler = repeating_ical_events_flask.RequestHandler(
    uid_gens, application, flask.request)
  return handler.Response()
