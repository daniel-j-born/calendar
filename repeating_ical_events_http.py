# Python module to handle flask based requests for repeating_ical_events.

import datetime
import flask
import hashlib
import os
import re
import repeating_ical_events
import threading
import traceback
import wtforms

from wtforms import (BooleanField, Field, FieldList, Form, FormField,
     HiddenField, IntegerField, StringField, TextField, validators)
from wtforms.ext.dateutil.fields import DateTimeField


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


class StaticVersions(object):
  def __init__(self, dirname, basenames):
    self._dirname = dirname
    self._version = {}
    for basename in basenames:
      with open(os.path.join(dirname, basename), 'rb') as fh:
        self._version[basename] = hashlib.sha256(fh.read()).hexdigest()[:20]

  def UrlFor(self, basename):
    if basename in self._version:
      return flask.url_for(self._dirname, filename=basename,
                           version=self._version[basename])
    return flask.url_for(self._dirname, filename=basename)


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
    min_period = datetime.timedelta(0)
    max_period = datetime.timedelta(days=1)
    d = datetime.timedelta(hours=hours, minutes=minutes)
    if d < min_period or d > max_period:
      return FieldSetError(self, 'invalid period')
    self.data = d


# Characters allowed in the event summary.
_summary_max = 100
_summary_chars = re.compile(r'[-_A-Za-z0-9.(){}\[\] ]+')

def FilterSummary(data):
  if not data:
    return data
  return ''.join(_summary_chars.findall(
    re.sub(r'[\t\n]', ' ', data.strip()[:_summary_max])))


class EventForm(wtforms.Form):
  summary = StringField(
    'Event Name',
    [validators.InputRequired(), validators.Length(min=1, max=100),
     validators.Regexp(_summary_chars)],
    default='Event', filters=(FilterSummary,))
  period = EventPeriodField(
    'Event Period (HH:MM)', [validators.InputRequired()])


# Default values for unfilled form fields.
_d = repeating_ical_events.ScheduleBuilder(None, None)


class ScheduleForm(wtforms.Form):
  # Default start_time and end_time are set to the user's local time using
  # Javascript. default= here is in case JS fails.
  start_time = DateTimeField(
    'Start Time (YYYY/MM/DD HH:MM)', [validators.InputRequired()])
  end_time = DateTimeField(
    'End Time (YYYY/MM/DD HH:MM)', [validators.InputRequired()])
  merge_overlapping = BooleanField(
    'If two events occur at the same time, merge them into a single event',
    default=_d.merge_overlap)
  event_duration_secs = SecondsField(
    'Duration of each event in seconds', [validators.InputRequired()],
    default=_d.event_duration)
  show_busy = BooleanField('Show as busy during events', default=_d.show_busy)
  set_alarms = BooleanField( """Set alarms. <b>Note:</b> many calendar programs
  will ignore alarms from imported calendars. Set the default alarm policy in
  your calendar program before importing.""", default=_d.set_alarms,
  render_kw={'onchange': 'updateAlarmInputsHidden()'})
  alarm_before_secs = SecondsField(
    'Number of seconds before the event to alarm', [validators.InputRequired()],
    default=_d.alarm_before)
  alarms_repeat = BooleanField("""Alarms repeat. <b>Note:</b> most calendar
  programs won't repeat alarms""", default=_d.alarms_repeat,
  render_kw={'onchange': 'updateAlarmInputsHidden()'})
  alarm_repetitions = IntegerField(
    'If alarms repeat, number of repetitions', [validators.InputRequired()],
    default=_d.alarm_repetitions)
  alarm_repetition_delay_secs = SecondsField(
    'If alarms repeat, number of seconds between each repetition',
    [validators.InputRequired()], default=_d.alarm_repetition_delay)
  #TODO: In JS, get number of events. Don't use a hidden field. Then create new
  #ones with the proper names.
  #num_events = HiddenField()
  #TODO: test that when JS adds and deletes and leaves holes, this will parse
  events = FieldList(FormField(EventForm), label='Events to Schedule',
                       min_entries=1, max_entries=100)

  def validate(self):
    """Override validate() to only validate fields that are used."""
    form_valid = True
    # Always validate:
    for field in (self.start_time, self.end_time, self.merge_overlapping,
                    self.event_duration_secs, self.show_busy, self.set_alarms,
                    self.events):
      if not field.validate(self):
        form_valid = False
    total_period = None
    if self.start_time.data is not None and self.end_time.data is not None:
      total_period = self.end_time.data - self.start_time.data
      if (total_period < datetime.timedelta(seconds=0) or
          total_period > datetime.timedelta(days=100)):
        form_valid = False
        self.start_time.data = None
        self.end_time.data = None
        self.end_time.errors.append(
          'invalid period between start and end times: %s' % total_period)
      else:
        # Valid total_period. Validate numbers of event repetitions.
        for event in self.events:
          if event.period.data is None:
            continue
          if event.period.data <= datetime.timedelta(0):
            num_reps = 0
          else:
            num_reps = int(total_period / event.period.data)
          if num_reps < 1 or num_reps > 1000:
            form_valid = False
            event.period.data = None
            if event.summary.data:
              summary = event.summary.data
            else:
              summary = 'event'
            event.period.errors.append(
              'invalid number of repetitions for %s: %d' % (summary, num_reps))
    if self.set_alarms.data:
      # If alarms are enabled, validate additional required fields.
      for field in (self.alarm_before_secs, self.alarms_repeat,
                      self.alarm_repetitions, self.alarm_repetition_delay_secs):
        if not field.validate(self):
          form_valid = False
      if self.alarms_repeat.data:
        # If alarm repeats are enabled, validate additional.
        for field in (self.alarm_repetition_delay_secs,
                        self.alarm_repetitions):
          if not field.validate(self):
            form_valid = False
        if (self.alarm_repetition_delay_secs.data is not None and
            self.alarm_repetitions.data is not None):
          rep_period = (self.alarm_repetition_delay_secs.data *
                          self.alarm_repetitions.data)
          if rep_period > datetime.timedelta(hours=24):
            form_valid = False
            self.alarm_repetition_delay_secs.data = None
            self.alarm_repetitions.data = None
            self.alarm_repetition_delay_secs.errors.append(
              'invalid alarm repetition duration %s' % rep_period)
    return form_valid


class RequestHandler(object):
  def __init__(self, uid_gens, static_versions, flask_app, req):
    """Give HostUidGen instance and flask.request."""
    self._uid_gens = uid_gens
    self._static_versions = static_versions
    self._flask_app = flask_app
    self._req = req

  def Response(self):
    try:
      if self._req.method == 'POST':
        return self._CalendarDownload()
      else:
        return self._CalendarForm()
    except:
      # Exceptions. Don't render any user messages.
      self._flask_app.logger.error('Unexpected exception: %s',
                                   traceback.format_exc())
      return flask.make_response(
        flask.render_template(
          'error.html',
          css_url=self._static_versions.UrlFor('style.css'),
          title='Internal Server Error',
          error_message='Internal Server Error'), 500)

  def _ErrorPage(self, form):
    """Recreate the form with user inputs and error messages."""
    return flask.make_response(
      flask.render_template('index.html', **self._IndexParams(form)), 400)

  def _IndexParams(self, form):
    return {
      'forms_js': self._static_versions.UrlFor('repeating_ical_forms.js'),
      'css_url': self._static_versions.UrlFor('style.css'),
      'form': form,
    }

  def _CalendarForm(self):
    return flask.render_template(
      'index.html', **self._IndexParams(ScheduleForm()))

  def _SetConfig(self, sched, form):
    """Set configuration data in sched from data in form.
    form should be validated."""
    sched.merge_overlap          = form.merge_overlapping.data
    sched.set_alarms             = form.set_alarms.data
    sched.alarms_repeat          = form.alarms_repeat.data
    sched.alarm_repetitions      = form.alarm_repetitions.data
    sched.alarm_repetition_delay = form.alarm_repetition_delay_secs.data
    sched.alarm_before           = form.alarm_before_secs.data
    sched.show_busy              = sched.show_busy.data
    sched.event_duration         = sched.event_duration_secs.data

  def _CalendarDownload(self):
    form = ScheduleForm(self._req.form)
    if not form.validate():
      return self._ErrorPage(form)
    sched = repeating_ical_events.ScheduleBuilder(
      form.start_time.data, form.end_time.data)
    self._SetConfig(sched, form)
    for event in form.events:
      sched.AddRepeatingEvent(event.summary.data, event.period.data)
    cal = sched.BuildCalendar(self._uid_gens.UidGen(self._req))
    return flask.Response(cal.to_ical(), mimetype='text/calendar')
