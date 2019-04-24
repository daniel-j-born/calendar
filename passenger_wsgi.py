# System modules
import flask
import os
import socket
import sys
import threading

# My modules
sys.path.insert(0, os.path.dirname(__file__))
import repeating_ical_events_http

# The Python servlet environment makes the path look like '/', but the actual
# externally visible path is INSTALL_PATH. We need @application.route for both.
INSTALL_PATH = '/repeating_events'

uid_gens = repeating_ical_events_http.HostUidGen()
application = flask.Flask(repeating_ical_events_http.__name__)

# Cache hashes of static content (which must be in './static/' directory).
static_versions = repeating_ical_events_http.StaticVersions(application)

@application.route('/', methods=['GET', 'POST'])
@application.route(INSTALL_PATH, methods=['GET', 'POST'])
def RepeatingEvents():
  """Used as main entry point via url_for(<method_name>) in templates."""
  flask.request.path = INSTALL_PATH
  handler = repeating_ical_events_http.RequestHandler(
    uid_gens, static_versions, application, flask.request)
  return handler.Response()
