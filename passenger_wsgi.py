# System modules
import flask
import os
import sys

# My modules
sys.path.insert(0, os.path.dirname(__file__))
import repeating_ical_events_http

# The Python servlet environment makes the path look like '/', but the actual
# externally visible path is APP_PATH. We need @application.route for both.
APP_PATH = '/repeating_events'

uid_gens = repeating_ical_events_http.HostUidGen()
application = flask.Flask(repeating_ical_events_http.__name__)

# Cache hashes of static content (which must be in './static/' directory).
static_versions = repeating_ical_events_http.StaticVersions(application)

@application.route('/', methods=['GET', 'POST'])
@application.route(APP_PATH, methods=['GET', 'POST'])
def RepeatingEvents():
  flask.request.path = APP_PATH
  handler = repeating_ical_events_http.RequestHandler(
    uid_gens, static_versions, application, flask.request)
  return handler.Response()
