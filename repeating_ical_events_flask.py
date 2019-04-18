# Python module to handle flask based requests for repeating_ical_events.

import datetime
import flask
import repeating_ical_events
import sys

class ErrorPageError(Exception):
  def __init__(self, user_message=None, debug_message=None):
    """user_message is for users. debug_message is for the developer."""
    messages = []
    if user_message:
      messages.append(user_message)
    if debug_message:
      messages.append(debug_message)
    super().__init__(*messages)
    self.user_message = user_message
    self.debug_message = debug_message

class HostUidGen(object):
  def __init__(self):
    # Hostname mapped to UidGenerator.
    self._uid_gens = {}
    self._uid_gens_lock = threading.Lock()
    
  def UidGen(request=None):
    """Return UidGenerator for the server host. Give flask.request, if available."""
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


def Checked(bool_val):
  if bool_val:
    return 'checked'
  else:
    return ''


class RequestHandler(object):
  def __init__(self, uid_gens, req):
    """Give HostUidGen instance and flask.request."""
    self._uid_gens = uid_gens
    self._req = req

  def Response(self):
    try:
      if self._req.method == 'POST':
        return self._CalendarDownload()
      else:
        return self._CalendarForm()
    except ErrorPageError as err_page:
      return self._ErrorPage(err_page)#TODO renders error code and
                                      #err_page.user_message
    except:
      # Other kinds of exceptions. No user message.
      #TODO: log something
      return self._ErrorPage(ErrorPageError(user_message='Uknown error'))

  def _IndexParams(self):
    not_used = datetime.datetime.now()
    # Configuration defaults are rendered into the form.
    d = repeating_ical_events.ScheduleBuilder(not_used, not_used)
    event_config = {
      'merge_overlapping': Checked(d.merge_overlap),
      'set_alarms': Checked(d.set_alarms),
      'alarms_repeat': Checked(d.alarms_repeat),
      'alarm_repititions': d.alarm_repititions,
      'alarm_repitition_delay_secs':
        int(d.alarm_repitition_delay.total_seconds()),
      'alarm_before_secs': int(d.alarm_before.total_seconds()),
      'show_busy': Checked(d.show_busy),
      'event_duration': int(d.event_duration.total_seconds()),
    }
    return {
      'form_action': self._req.path,
      'forms_js': flask.url_for('static', filename='repeating_ical_forms.js'),
      'css_url': flask.url_for('static', filename='style.css'),
      'event_config': event_config,
      }

  def _CalendarForm(self):
    return flask.render_template('index.html', **self._IndexParams())

  def _CalendarDownload(self):
    start_time = self._ParseStartTime()#TODO: parse or raise
    end_time = self._ParseEndTime()#TODO
    total_period = end_time - start_time
    if (total_period > datetime.timedelta(days=100) or total_period <
        datetime.timedelta(seconds=0)):
      raise ErrorPageError(user_message='Invalid period between start and end times: %s' %
          total_period)

    sched = repeating_ical_events.ScheduleBuilder(start_time, end_time)
    self._ParseEventConfig(sched)#TODO: parse event config from the form and set
                                 #in sched. raise on error.
    #TODO: validate various ranges. Set a max number of events. Set a max (start,
    #    end) timedelta.
    pass#TODO


