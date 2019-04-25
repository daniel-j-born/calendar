# System modules
import flask
import os
import sys

# My modules
sys.path.insert(0, os.path.dirname(__file__))
import repeating_ical_events_http

uid_gens = repeating_ical_events_http.HostUidGen()
application = flask.Flask(repeating_ical_events_http.__name__)

# Cache hashes of static content (which must be in './static/' directory).
static_versions = repeating_ical_events_http.StaticVersions(application)

# The Python servlet environment makes the path look like '/', but the actual
# externally visible path is url_for('RepeatingEvents'),
# currently '/repeating_events/'.
@application.route('/', methods=['GET', 'POST'])
def RepeatingEvents():
  handler = repeating_ical_events_http.RequestHandler(
    uid_gens, static_versions, application, flask.request)
  return handler.Response()
