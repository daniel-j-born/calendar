# Python module to handle flask based requests for repeating_ical_events.
#
# TODO: rename module

import collections
import datetime
import flask
import re
import repeating_ical_events
import sys
import threading
import traceback
import wtforms

from wtforms import (BooleanField, Field, FieldList, Form, FormField,
     HiddenField, IntegerField, StringField, TextField, validators)
from wtforms.ext.dateutil.fields import DateTimeField

# class ErrorPageError(Exception):
#   def __init__(self, user_message=None, debug_message=None, http_code=400,
#                  error_fields=None):
#     """user_message is for users. debug_message is for the developer."""
#     messages = []
#     if user_message:
#       messages.append(user_message)
#     if debug_message:
#       messages.append(debug_message)
#     super().__init__(*messages)
#     self.user_message = user_message
#     self.debug_message = debug_message
#     self.http_code = http_code
#     self.error_fields = []
#     if error_fields:
#       self.error_fields.extend(error_fields)

      
class HostUidGen(object):
  """Get a repeating_ical_events.UidGenerator for the server hostname
  for a given request."""
  def __init__(self):
    # Hostname mapped to UidGenerator.
    self._uid_gens = {}
    self._uid_gens_lock = threading.Lock()
    
  def UidGen(self, request=None):
    """Return UidGenerator for the server host. Give flask.request, if available."""
    try:
      host = request.host.split(':')[0]
    except AttributeError:
      host = socket.getfqdn()
    with self._uid_gens_lock:
      if host in self._uid_gens:
        return self._uid_gens[host]
      else:
        uid_gen = repeating_ical_events.UidGenerator(host)
        self._uid_gens[host] = uid_gen
        return uid_gen


def FieldSetError(field, msg):
  """Set field.data=None and append message to field.process_errors."""
  field.data = None
  if field.process_errors is None:
    field.process_errors = []
  elif type(field.process_errors) == tuple:
    field.process_errors = [*field.process_errors]
  field.process_errors.append(msg)


class SecondsField(IntegerField):
  """Sets data to a timedelta. Parses and renders a duration in seconds.
  Required field. Builtin validation."""
  #def __init__(self, label='', validators=None, **kwargs):
  #  super().__init__(label=label, validators=validators, **kwargs)

  def _value(self):
    """Override _value to render raw_data if validation failed. This allows
    the user to see and correct their original input. Needs to be sanitized
    through a template system before rendering."""
    if type(self.data) == datetime.timedelta:
      return int(self.data.total_seconds())
    if self.raw_data:
      # Multiple instances are not valid. Return the last.
      return self.raw_data[-1]
    return ''

  def process_formdata(self, valuelist):
    if not valuelist:
      return FieldSetError(self, 'missing value')
    s = valuelist[-1]  # Take only last value.
    min_secs = 0
    max_secs = 24*3600
    if len(s) > len(str(max_secs)):
      return FieldSetError(self, 'too long')
    try:
      i = int(s)
    except ValueError:
      return FieldSetError(self, 'not an integer')
    if i < min_secs or i > max_secs:
      return FieldSetError(self, 'out of range')
    self.data = datetime.timedelta(seconds=i)


class EventPeriodField(StringField):
  """Encapsulate a timedelta that is parsed and rendered as HH:MM."""

  def _value(self):
    """Return raw_data is data is not set."""
    if type(self.data) == datetime.timedelta:
      s = int(self.data.total_seconds())
      h = s // 3600
      m = (s - h * 3600) // 60
      return '%02d:%02d' % (h, m)
    if self.raw_data:
      return self.raw_data[-1]
    return ''

  def process_formdata(self, valuelist):
    if not valuelist:
      return FieldSetError(self, 'missing value')
    s = valuelist[-1]
    m = re.match(r'(\d{0,2}):(\d{0,2})$', s)
    if not m:
      return FieldSetError(self, 'bad format (HH:MM)')
    if m.group(1):
      hours = int(m.group(1))
    else:
      hours = 0
    if m.group(2):
      minutes = int(m.group(2))
    else:
      minutes = 0
    max_period = datetime.timedelta(days=1)
    d = datetime.timedelta(hours=hours, minutes=minutes)
    if d > max_period:
      return FieldSetError(self, 'too long')
    self.data = d


class EventForm(wtforms.Form):
  summary = StringField('Event Name', validators=[validators.Length(max=80)],
                        default='Event')
  period = EventPeriodField('Event Period (HH:MM)', default='HH:MM')


# Default values for unfilled form fields. TODO: default param can be callable,
# but we need the submit bool. called with Field as param?: self.default()
_d = repeating_ical_events.ScheduleBuilder(None, None)


#TODO automatic default value or check raw_data truthiness?
class ScheduleForm(wtforms.Form):
  # Default start_time and end_time are set to the user's local time using
  # Javascript.
  start_time = DateTimeField('Start Time (YYYY/MM/DD HH:MM)',
                               [validators.InputRequired()])
  end_time = DateTimeField('End Time (YYYY/MM/DD HH:MM)',
                             [validators.InputRequired()])
  merge_overlapping = BooleanField(
    'If two events occur at the same time, merge them into a single event',
    default=_d.merge_overlap)
  event_duration_secs = SecondsField('Duration of each event in seconds')
  show_busy = BooleanField('Show as busy during events')
  set_alarms = BooleanField( """Set alarms. <b>Note:</b> many calendar programs
  will ignore alarms from imported calendars. Set the default alarm policy in
  your calendar program before importing.""")
  alarm_before_secs = SecondsField(
    'Number of seconds before the event to alarm')
  alarms_repeat = BooleanField("""Alarms repeat. <b>Note:</b> most calendar
  programs won't repeat alarms""")
  alarm_repetitions = IntegerField('If alarms repeat, number of repetitions',
                                     [validators.InputRequired()])
  alarm_repetition_delay_secs = SecondsField(
    'If alarms repeat, number of seconds between each repetition')
  #TODO: In JS, get number of events. Don't use a hidden field. Then create new
  #ones with the proper names.
  #num_events = HiddenField()
  events = FieldList(FormField(EventForm), label='Events to Schedule',
                       min_entries=1, max_entries=100)

  def validate(self):
    form_valid = super().validate()
    #TODO: for fields that validated (data is not None, no errors), validate
    #relative values (e.g., end_time-start_time).


def Checked(bool_val):
  """Convert bool to HTML checked boolean attribute."""
  if bool_val:
    return 'checked'
  else:
    return ''


class RequestHandler(object):
  def __init__(self, uid_gens, flask_app, req):
    """Give HostUidGen instance and flask.request."""
    self._uid_gens = uid_gens
    self._flask_app = flask_app
    self._req = req
    # Names of fields that failed input validation mapped to an error message.
    #self._bad_fields = collections.OrderedDict()
    # Event index mapped to 2-item list of unparsed summary and period. The list
    # will be renumbered when the input is rendered back into the page.
    # num_events should be largely untrusted and ignored server side.
    # events = {}
    # self._max_events = 200
    # for name, value in req.form.items():
    #   if len(self._events) >= 200:
    #     break
    #   m = re.match(r'summary_(\d+)$', name)
    #   if m:
    #     self._events.setdefault(int(m.group(1)), [value, ''])[0] = value
    #     continue
    #   m = re.match(r'period_(\d+)$', name)
    #   if m:
    #     self._events.setdefault(int(m.group(1)), ['', value])[1] = value
    # # 2-tuples of event summary and period sorted by index.
    # #TODO: use this for parsing events. render this back into HTML
    # self._events = [(x[1][0], x[1][1]) for x in sorted(events.items())]

  def Response(self):
    try:
      #TODO: form.validate() in CalendarDownload()
      #
      if self._req.method == 'POST':
        #TODO: no defaults. re-render and process whatever user submits
        return self._CalendarDownload()
      else:
        #TODO: set defaults in Form spec above
        return self._CalendarForm()
    except:
      # Exceptions. Don't render any user messages.
      self._flask_app.logger.error('Unexpected exception: %s',
                                   traceback.format_exc())
      return flask.make_response(
        flask.render_template(
          'error.html',
          css_url=flask.url_for('static', filename='style.css'),
          title='Internal Server Error',
          error_message='Internal Server Error'), 500)

  def _ErrorPage(self, err_page):
    """Recreate the form with user inputs and an error message."""
    return flask.make_response(
      flask.render_template('index.html', **self._IndexParams(True)), 400)

  def _IndexParams(self, form):
    # # Configuration defaults are rendered into the form.
    # d = repeating_ical_events.ScheduleBuilder(None, None)
    # event_config = {
    #   # Javascript is used to generate the default start and end times within
    #   # the timezone of the user.
    #   'start_time': self._req.form.get('start_time', ''),
    #   'end_time': self._req.form.get('end_time', ''),
    #   'merge_overlapping':
    #     Checked(self._ParseCheckBox('merge_overlapping') or
    #               (not submit and d.merge_overlap)),
    #   'set_alarms':
    #     Checked(self._ParseCheckBox('set_alarms') or
    #               (not submit and d.set_alarms)),
    #   'alarms_repeat':
    #     Checked(self._ParseCheckBox('alarms_repeat') or
    #               (not submit and d.alarms_repeat)),
    #   'alarm_repetitions':
    #     self._req.form.get('alarm_repetitions',
    #                        '' if submit else d.alarm_repetitions),
    #   'alarm_repetition_delay_secs':
    #     self._req.form.get(
    #       'alarm_repetition_delay_secs',
    #       '' if submit else int(d.alarm_repetition_delay.total_seconds())),
    #   'alarm_before_secs':
    #     self._req.form.get(
    #       'alarm_before_secs',
    #       '' if submit else int(d.alarm_before.total_seconds())),
    #   'show_busy':
    #     Checked(self._ParseCheckBox('show_busy') or
    #               (not submit and d.show_busy)),
    #   'event_duration_secs':
    #     self._req.form.get(
    #       'event_duration_secs',
    #       '' if submit else int(d.event_duration.total_seconds())),
    # }
    return {
      'form_action': self._req.path,
      'forms_js': flask.url_for('static', filename='repeating_ical_forms.js'),
      'css_url': flask.url_for('static', filename='style.css'),
      #'event_config': event_config,
      #'num_events': self._req.form.get('num_events', 0),
      'form': form,
    }

  def _CalendarForm(self):
    return flask.render_template(
      'index.html', **self._IndexParams(ScheduleForm()))

  # def _ParseDateTime(self, name, display_name):
  #   """Parse date and time strings of the form: YYYY/MM/DD HH:MM"""
  #   s = self._req.form.get(name, '').strip()
  #   m = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2})$', s)
  #   if not m:
  #     self._bad_fields[name] = 'Invalid %s format' % display_name
  #     return None
  #   try:
  #     return datetime.datetime(*[int(x) for x in m.groups()])
  #   except ValueError:
  #     self._bad_fields[name] = 'Invalid  value' % display_name
  #     return None

  # def _ParseCheckBox(self, name):
  #   if self._req.form.get(name, None):
  #     return True
  #   return False

  # def _ParseInt(self, name, display_name):
  #   val = self._req.form.get(name, '')
  #   val = val.strip()
  #   try:
  #     if val and len(val) <= 20 and re.match(r'\d+$', val):
  #       return int(val)
  #   except ValueError:
  #     pass
  #   self._bad_fields[name] = 'Invalid value for %s' % display_name
  #   return None

  def _ParseEventsConfig(self, sched):
    """Parse event config values from self._req.form. Set results in
    self._bad_fields and sched."""
    sched.merge_overlap = self._ParseCheckBox('merge_overlapping')
    sched.set_alarms = self._ParseCheckBox('set_alarms')
    sched.alarms_repeat = self._ParseCheckBox('alarms_repeat')
    sched.alarm_repetitions = self._ParseInt(
      'alarm_repetitions', 'alarm repetitions')
    parsed = self._ParseInt(
      'alarm_repetition_delay_secs', 'seconds between alarm repetitions')
    if parsed is not None:
      sched.alarm_repetition_delay = datetime.timedelta(seconds=parsed)
    else:
      sched.alarm_repetition_delay = None
    if (sched.alarm_repetitions is not None and
        sched.alarm_repetition_delay is not None):
      rep = sched.alarm_repetitions * sched.alarm_repetition_delay
      if rep > datetime.timedelta(hours=24):
        self._bad_fields['alarm_repetitions'] = \
          'Invalid alarm repetition %s' % rep
    parsed = self._ParseInt(
      'alarm_before_secs', 'seconds before event to alarm')
    if parsed is not None:
      sched.alarm_before = datetime.timedelta(seconds=parsed)
      if sched.alarm_before > datetime.timedelta(hours=24):
        self._bad_fields['alarm_before_secs'] = \
          'Invalid alarm warning period %s' % sched.alarm_before
    else:
      sched.alarm_before = None
    sched.show_busy = self._ParseCheckBox('show_busy')
    parsed = self._ParseInt(
      'event_duration_secs', 'events durations in seconds')
    if parsed is not None:
      sched.event_duration = datetime.timedelta(seconds=parsed)
      if sched.event_duration > datetime.timedelta(hours=24):
        self._bad_fields['event_duration_secs'] = \
          'Invalid event duration %s' % sched.event_duration
    else:
      sched.event_duration = None

  def _GetEventSummary(self, summary_name):
    """Return event summary or None. Set self._bad_fields on errors."""
    summary = self._req.form.get(summary_name, '')
    summary = summary.strip()[:100]
    if summary:
      summary = re.sub(r'[\t\n]', ' ', summary)
      summary = ''.join(re.findall(r'[-_A-Za-z0-9. ]', summary))
      if summary:
        return summary
    self._bad_fields[summary_name] = 'Invalid event name'
    return None

  def _GetEventPeriod(self, period_name, summary=None):
    """Return event period or None. Set self._bad_fields on errors."""
    if not summary:
      summary = 'event'
    period = self._req.form.get(period_name, '')
    period = period.strip()
    m = re.match(r'(\d{1,2}):(\d{1,2})$', period)
    if not m:
      self._bad_fields[period_name] = 'Invalid %s period format' % summary
      return None
    hours = int(m.group(1))
    mins = int(m.group(2))
    if hours < 0 or mins < 0:
      self._bad_fields[period_name] = 'Invalid %s period value' % summary
      return None
    return datetime.timedelta(hours=hours, minutes=mins)
      
  def _ParseEvents(self, sched):
    """Parse events from self._req.form."""
    for name in self._req.form:
      num_bad = len(self._bad_fields)
      m = re.match(r'summary_(\d+)$', name)
      if not m:
        continue
      event_num_str = m.group(1)
      period_name = 'period_' + event_num_str
      summary = self._GetEventSummary(name)
      period = self._GetEventPeriod(period_name, summary=summary)
      if not summary:
        summary = 'event'
      if period is not None:
        if period > datetime.timedelta(hours=24):
          self._bad_fields[period_name] ='Invalid %s period %s' % (
            summary, period)
        num_reps = int((sched.end_time - sched.start_time) / period)
        if num_reps > 1000:
          self._bad_fields[period_name] = \
            'Invalid number of repetitions for %s: %d' % (summary, num_reps)
      if sched.NumEvents() >= self._max_events:
        self._bad_fields[name] = 'Too many events: %d' % sched.NumEvents()
      if len(self._bad_fields) == num_bad:
        sched.AddRepeatingEvent(summary, period)

  def _CalendarDownload(self):
    form = ScheduleForm(self._req.form)
    form_valid = form.validate()
    if start_time and end_time:#TODO:make required
      total_period = end_time - start_time
      if (total_period > datetime.timedelta(days=100) or total_period <
            datetime.timedelta(seconds=0)):
        self._bad_fields['end_time'] = \
            'Invalid period between start and end times: %s' % total_period
    sched = repeating_ical_events.ScheduleBuilder(start_time, end_time)
    self._ParseEventsConfig(sched)
    if self._bad_fields:
      # Bail out on parsing the events if the config is incorrect.
      return self._ErrorPage()
    self._ParseEvents(sched)
    if self._bad_fields:
      return self._ErrorPage()
    cal = sched.BuildCalendar(self._uid_gens.UidGen(self._req))
    return flask.Response(cal.to_ical(), mimetype='text/calendar')
