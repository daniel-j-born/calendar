# System modules
import flask
import os
import socket
import sys
import threading

# My modules
sys.path.insert(0, os.path.dirname(__file__))
import repeating_ical_events


class HostUidGen(object):
  def __init__(self):
    # Hostname mapped to UidGenerator.
    self._uid_gens = {}
    self._uid_gens_lock = threading.Lock()
    
  def UidGen(request=None):
    """Give flask.request, if available."""
    #if flask.request and flask.request.host:
    if request and request.host:
      host = request.host.split(':')[0]
    else:
      host = socket.getfqdn()
    with self._uid_gens_lock:
      if host in self._uid_gens:
        return self._uid_gens[host]
      else:
        uid_gen = repeating_ical_events.UidGenerator(host)
        self._uid_gens[host] = uid_gen
        return uid_gen


uid_gens = HostUidGen()
application = flask.Flask(__name__)

@application.route('/testing/repeating_ical_events', methods=['GET', 'POST'])
def RepeatingIcalEvents():
  if flask.request.method == 'POST':
    return CalendarDownload()
  else:
    # Bounds checking. Set max number of events to generate. Set max time delta.
    return CalendarForm()
  #return ('socket.gethostname(): ' + socket.gethostname() + ', request host: ' +
  #          flask.request.host + ', request host_url: ' + flask.request.host_url)


def IndexParams():
  #TODO: prefill start and end times with current datetime. set min and max
  #attributes on datetime-local fields (start and end times).
  return {
    'form_action': flask.request.path,
    'forms_js': flask.url_for('static', filename='repeating_ical_forms.js'),
    'css_url': flask.url_for('static', filename='style.css'),
    }


def CalendarForm():
  return flask.render_template('index.html', **IndexParams())
  
  
# def application(environ, start_response):
#   start_response('200 OK', [('Content-Type', 'text/plain')])
#   message = 'It works!\n'
#   version = 'Python %s\n' % sys.version.split()[0]
#   response = '\n'.join([message, version])
#   return [response.encode()]
