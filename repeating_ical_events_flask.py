# Python module to handle flask based requests for repeating_ical_events.

import datetime
import flask
import re
import repeating_ical_events
import sys
import threading
import traceback

class ErrorPageError(Exception):
  def __init__(self, user_message=None, debug_message=None, http_code=400):
    """user_message is for users. debug_message is for the developer."""
    messages = []
    if user_message:
      messages.append(user_message)
    if debug_message:
      messages.append(debug_message)
    super().__init__(*messages)
    self.user_message = user_message
    self.debug_message = debug_message
    self.http_code = http_code

class HostUidGen(object):
  def __init__(self):
    # Hostname mapped to UidGenerator.
    self._uid_gens = {}
    self._uid_gens_lock = threading.Lock()
    
  def UidGen(self, request=None):
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
  """Convert bool to HTML checked boolean attribute."""
  if bool_val:
    return 'checked'
  else:
    return ''

def ParseDateTime(s):
  """Parse date and time strings of the form:
  YYYY/MM/DD HH:MM """
  s = s.strip()
  m = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2})$', s)
  if not m:
    raise ErrorPageError(user_message='Invalid date-time format')
  try:
    return datetime.datetime(*[int(x) for x in m.groups()])
  except ValueError:
    raise ErrorPageError(user_message='Invalid date-time value')


class RequestHandler(object):
  def __init__(self, uid_gens, flask_app, req):
    """Give HostUidGen instance and flask.request."""
    self._uid_gens = uid_gens
    self._flask_app = flask_app
    self._req = req

  def Response(self):
    try:
      if self._req.method == 'POST':
        return self._CalendarDownload()
      else:
        return self._CalendarForm()
    except ErrorPageError as err_page:
      self._flask_app.logger.info('Error page rendered with message "%s". Debug: %s',
                                    err_page.user_message, err_page.debug_message)
      return self._ErrorPage(err_page)
    except:
      # Other kinds of exceptions. No user message.
      self._flask_app.logger.error('Unexpected exception: %s',
                                   traceback.format_exc())
      return self._ErrorPage(ErrorPageError(
        user_message='Internal error', http_code=500))

  def _ErrorPage(self, err_page):
    """Render an error message for the user."""
    if err_page.user_message:
      user_message = err_page.user_message
    else:
      user_message = 'Unknown error'
    if err_page.http_code >= 400 and err_page.http_code < 500:
      title = 'Bad Request'
    else:
      title = 'Internal Server Error'
    return flask.make_response(
      flask.render_template('error.html',
                            css_url=flask.url_for('static', filename='style.css'),
                            title=title,
                            user_message=user_message),
      err_page.http_code)

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
      'event_duration_secs': int(d.event_duration.total_seconds()),
    }
    return {
      'form_action': self._req.path,
      'forms_js': flask.url_for('static', filename='repeating_ical_forms.js'),
      'css_url': flask.url_for('static', filename='style.css'),
      'event_config': event_config,
      }

  def _CalendarForm(self):
    return flask.render_template('index.html', **self._IndexParams())

  def _ParseStartTime(self):
    try:
      return ParseDateTime(self._req.form['start_time'])
    except ErrorPageError as err:
      raise ErrorPageError(user_message='Bad start time: %s' % err.user_message)

  def _ParseEndTime(self):
    try:
      return ParseDateTime(self._req.form['end_time'])
    except ErrorPageError as err:
      raise ErrorPageError(user_message='Bad end time: %s' % err.user_message)

  def _ParseCheckBox(self, name):
    if self._req.form.get(name, None):
      return True
    return False

  def _ParseInt(self, name):
    val = self._req.form.get(name, '')
    val = val.strip()
    try:
      if val and len(val) <= 20 and re.match(r'\d+$', val):
        return int(val)
    except ValueError:
      pass
    raise ErrorPageError(user_message='Invalid value for %s' % name)

  def _ParseEventsConfig(self, sched):
    sched.merge_overlap = self._ParseCheckBox('merge_overlapping')
    sched.set_alarms = self._ParseCheckBox('set_alarms')
    sched.alarms_repeat = self._ParseCheckBox('alarms_repeat')
    sched.alarm_repititions = self._ParseInt('alarm_repititions')
    sched.alarm_repitition_delay = datetime.timedelta(
      seconds=self._ParseInt('alarm_repitition_delay_secs'))
    rep = sched.alarm_repititions * sched.alarm_repitition_delay
    if rep > datetime.timedelta(hours=24):
      raise ErrorPageError(user_message='Invalid alarm repitition %s' % rep)
    sched.alarm_before = datetime.timedelta(
      seconds=self._ParseInt('alarm_before_secs'))
    if sched.alarm_before > datetime.timedelta(hours=24):
      raise ErrorPageError(
        user_message='Invalid alarm warning period %s' % sched.alarm_before)
    sched.show_busy = self._ParseCheckBox('show_busy')
    sched.event_duration = datetime.timedelta(
      seconds=self._ParseInt('event_duration_secs'))
    if sched.event_duration > datetime.timedelta(hours=24):
      raise ErrorPageError(
        user_message='Invalid event duration %s' % sched.event_duration)

  def _ParseEventSummary(self, summary_name):
    summary = self._req.form.get(summary_name, '')
    summary = summary.strip()[:100]
    if summary:
      summary = re.sub(r'[\t\n]', ' ', summary)
      summary = ''.join(re.findall(r'[-_A-Za-z0-9. ]', summary))
      if summary:
        return summary
    raise ErrorPageError(user_message='Invalid event name')

  def _ParseEventPeriod(self, period_name):
    period = self._req.form.get(period_name, '')
    period = period.strip()
    m = re.match(r'(\d{1,2}):(\d{1,2})$', period)
    if not m:
      raise ErrorPageError(user_message='Invalid event period format')
    hours = int(m.group(1))
    mins = int(m.group(2))
    if hours < 0 or mins < 0:
      raise ErrorPageError(user_message='Invalid event period value')
    return datetime.timedelta(hours=hours, minutes=mins)
      
  def _ParseEvents(self, sched):
    max_events = 200
    for name in self._req.form:
      m = re.match(r'summary_(\d+)$', name)
      if not m:
        continue
      event_num_str = m.group(1)
      period_name = 'period_' + event_num_str
      summary = self._ParseEventSummary(name)
      try:
        period = self._ParseEventPeriod(period_name)
      except ErrorPageError as err:
        raise ErrorPageError(user_message='Period for event %s: %s' % (
          summary, err.user_message))
      if period > datetime.timedelta(hours=24):
        raise ErrorPageError(user_message='Invalid event period %s' % period)
      num_reps = int((sched.end_time - sched.start_time) / period)
      if num_reps > 1000:
        raise ErrorPageError(user_message='Invalid number of repititions for %s: %d' % (
          summary, num_reps))
      if sched.NumEvents() >= max_events:
        raise ErrorPageError(
          user_message='Too many events: %d' % sched.NumEvents())
      sched.AddRepeatingEvent(summary, period)

  def _CalendarDownload(self):
    start_time = self._ParseStartTime()
    end_time = self._ParseEndTime()
    total_period = end_time - start_time
    if (total_period > datetime.timedelta(days=100) or total_period <
        datetime.timedelta(seconds=0)):
      raise ErrorPageError(user_message='Invalid period between start and end times: %s' %
          total_period)
    sched = repeating_ical_events.ScheduleBuilder(start_time, end_time)
    self._ParseEventsConfig(sched)
    self._ParseEvents(sched)
    cal = sched.BuildCalendar(self._uid_gens.UidGen(self._req))
    return flask.Response(cal.to_ical(), mimetype='text/calendar')
