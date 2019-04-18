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

@application.route('/testing/repeating_ical_events', methods=['GET', 'POST'])
def RepeatingIcalEvents():
  handler = repeating_ical_events_flask.RequestHandler(uid_gens, flask.request)
  return handler.Response()

# def application(environ, start_response):
#   start_response('200 OK', [('Content-Type', 'text/plain')])
#   message = 'It works!\n'
#   version = 'Python %s\n' % sys.version.split()[0]
#   response = '\n'.join([message, version])
#   return [response.encode()]
