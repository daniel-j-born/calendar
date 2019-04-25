# System modules
import flask
import logging.config
import os
import sys

logging.config.dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

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
  application.logger.info('Handling request %s', flask.request)
  resp = ['--begin--']
  for handler in application.logger.handlers:
    resp.append(str(handler))
  resp.append('--end--')
  return '<br />'.join(resp)
  handler = repeating_ical_events_http.RequestHandler(
    uid_gens, static_versions, application, flask.request)
  return handler.Response()
