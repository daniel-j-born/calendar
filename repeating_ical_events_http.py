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
  for a given request. Thread-safe."""
  def __init__(self):
    # Hostname mapped to UidGenerator.
    self._uid_gens = {}
    self._uid_gens_lock = threading.Lock()
    
  def UidGen(self, request=None):
    """Return UidGenerator for the server host. Give flask.request,
    if available."""
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
  """Generate URLs for static content. The contents of files are hashed and this
  hash is included in a version query parameter so browsers will reload
  changed files. Thread-safe."""

  class FileInfo(object):
    def __init__(self, mtime, digest):
      self.mtime = mtime
      self.digest = digest

    def Set(self, mtime, digest):
      self.mtime = mtime
      self.digest = digest

  def __init__(self, app, reload_when_mtime_changes=True):
    """":param app: Flask app object"""
    self._app = app
    self._static = 'static'  # Special endpoint name for flask
    self._reload_when_mtime_changes = reload_when_mtime_changes
    # Map basename to FileInfo instance.
    self._fi = {}
    self._lock = threading.Lock()

  def _PathFor(self, basename):
    return os.path.join(self._app.static_folder, basename)

  def _ComputeDigest(self, fh):
    return hashlib.sha256(fh.read()).hexdigest()[:32]

  def _UpdateDigest(self, basename, path, mtime):
    """Update the cached entry for basename and return the digest."""
    digest = None
    with open(path, 'rb') as fh:
      digest = self._ComputeDigest(fh)
    with self._lock:
      self._fi[basename].Set(mtime, digest)
    return digest

  def _NewDigest(self, basename):
    mtime = None
    digest = None
    path = self._PathFor(basename)
    with open(path, 'rb') as fh:
      mtime = os.fstat(fh.fileno()).st_mtime
      digest = self._ComputeDigest(fh)
    with self._lock:
      self._fi[basename] = StaticVersions.FileInfo(mtime, digest)
    return digest

  def UrlFor(self, basename):
    mtime = None
    digest = None
    with self._lock:
      fi = self._fi.get(basename, None)
      if fi:
        mtime = fi.mtime
        digest = fi.digest
    if digest:
      if not self._reload_when_mtime_changes:
        return flask.url_for(self._static, filename=basename, version=digest)
      path = self._PathFor(basename)
      latest_mtime = os.stat(path).st_mtime
      if latest_mtime == mtime:
        return flask.url_for(self._static, filename=basename, version=digest)
      digest = self._UpdateDigest(basename, path, latest_mtime)
    else:
      digest = self._NewDigest(basename)
    self._app.logger.info('New digest for static file %s: %s', basename, digest)
    return flask.url_for(self._static, filename=basename, version=digest)


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

  def __init__(self, label=None, validators=None, *args, **kw_args):
    super().__init__(label, validators, *args, **kw_args)
    self._event_wrapper_form = kw_args.get('_form', None)

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
    if self._event_wrapper_form and self._event_wrapper_form.summary.data:
      ev_name = self._event_wrapper_form.summary.data
    else:
      ev_name = 'Event'
    if not valuelist:
      return FieldSetError(self, '%s value is missing' % ev_name)
    s = valuelist[-1]
    m = re.match(r'(\d{0,2}):(\d{0,2})$', s)
    if not m:        
      return FieldSetError(self, '%s has bad time period format (HH:MM)' % ev_name)
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
      return FieldSetError(self, '%s has invalid period' % ev_name)
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
  _summary_ph = 'Your name for this event'
  summary = StringField(
    'Event Name',
    [validators.InputRequired(), validators.Length(min=1, max=100),
     validators.Regexp(_summary_chars)],
    filters=(FilterSummary,),
    render_kw={'placeholder' : _summary_ph})

  _period_ph = 'HH:MM'
  period = EventPeriodField(
    'Event Period', [validators.InputRequired()],
    render_kw={'placeholder' : _period_ph})

  # TODO: Create a Field subclass for input type="button"
  _delete_val = 'Delete Event'


# Default values for unfilled form fields.
_d = repeating_ical_events.ScheduleBuilder(None, None)


class ScheduleForm(wtforms.Form):
  # Default start_time and end_time are set to the user's local time using
  # Javascript.
  start_time = DateTimeField(
    'Start Time', [validators.InputRequired()],
    render_kw={'placeholder' : 'YYYY/MM/DD HH:MM'})
  end_time = DateTimeField(
    'End Time', [validators.InputRequired()],
    render_kw={'placeholder' : 'YYYY/MM/DD HH:MM'})
  merge_overlapping = BooleanField(
    'If two events occur at the same time, merge them into a single event',
    default=_d.merge_overlap)
  event_duration_secs = SecondsField(
    'Duration of each event in seconds', [validators.InputRequired()],
    default=_d.event_duration)
  show_busy = BooleanField('Show as busy during events', default=_d.show_busy)
  set_alarms = BooleanField( """Set alarms. <b>Note:</b> <i>many calendar programs
  will ignore alarms from imported calendars. Set the default alarm policy in
  your calendar program before importing</i>""", default=_d.set_alarms,
  render_kw={'onchange': 'updateAlarmInputsHidden()'})
  alarm_before_secs = SecondsField(
    'Number of seconds before the event to alarm', [validators.InputRequired()],
    default=_d.alarm_before)
  alarms_repeat = BooleanField("""Alarms repeat. <b>Note:</b> <i>most calendar
  programs won't repeat alarms</i>""", default=_d.alarms_repeat,
  render_kw={'onchange': 'updateAlarmInputsHidden()'})
  alarm_repetitions = IntegerField(
    'If alarms repeat, number of repetitions', [validators.InputRequired()],
    default=_d.alarm_repetitions)
  alarm_repetition_delay_secs = SecondsField(
    'If alarms repeat, number of seconds between each repetition',
    [validators.InputRequired()], default=_d.alarm_repetition_delay)
  events = FieldList(FormField(EventForm), label='',
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
            # start_time and end_time are an inclusive range, so if
            # total_period==0 [or any value < event.period.data], there is one
            # event.
            num_reps = int(total_period / event.period.data) + 1
          if num_reps > 1000:
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


del _d  # Defaults needed only for class ScheduleForm definition.


class RequestHandler(object):
  def __init__(self, uid_gens, static_versions, app, req):
    """Give HostUidGen instance and flask.request."""
    self._uid_gens = uid_gens
    self._static_versions = static_versions
    self._app = app
    self._req = req

  def Response(self):
    try:
      if self._req.method == 'POST':
        return self._CalendarDownload()
      else:
        return self._CalendarForm()
    except:
      # Exceptions. Don't render any user messages.
      self._app.logger.error('Unexpected exception: %s', traceback.format_exc())
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
      'summary_ph_in': EventForm._summary_ph,
      'period_ph_in': EventForm._period_ph,
      'delete_val_in' : EventForm._delete_val,
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
    sched.show_busy              = form.show_busy.data
    sched.event_duration         = form.event_duration_secs.data

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
    # TODO: Setting other than content-type to trigger download vs. display?
    # Have filename include start day. How is versioned static URLs working?
    # What prevents responses to mutating GETs for the same params from being
    # cached by browsers? Do GET services always return a no-cache response to
    # the browser?
    return flask.Response(cal.to_ical(), mimetype='text/calendar')
