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

# The Python servlet environment makes the path look like '/', but the actual
# externally visible path is INSTALL_PATH. We need @application.route for both.
INSTALL_PATH = '/repeating_events'

uid_gens = repeating_ical_events_flask.HostUidGen()
application = flask.Flask(__name__)

@application.route('/', methods=['GET', 'POST'])
@application.route(INSTALL_PATH, methods=['GET', 'POST'])
def RepeatingIcalEvents():
  flask.request.path = INSTALL_PATH
  handler = repeating_ical_events_flask.RequestHandler(
    uid_gens, application, flask.request)
  return handler.Response()
