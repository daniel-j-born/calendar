"""Python module to handle flask based requests for repeating_ical_events."""

import datetime
import flask
import hashlib
import logging
import logging.handlers
import os
import re
import repeating_ical_events
import threading
import traceback
import wtforms

from wtforms import (BooleanField, Field, FieldList, Form, FormField,
                     HiddenField, IntegerField, StringField, validators)
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
      uid_gen = self._uid_gens.get(host, None)
      if uid_gen is not None:
        return uid_gen
      uid_gen = repeating_ical_events.UidGenerator(host)
      self._uid_gens[host] = uid_gen
      return uid_gen


def SetupLogging(dirname, app, level):
  dir_perms = 0o700
  os.makedirs(dirname, mode=dir_perms, exist_ok=True)
  os.chmod(dirname, dir_perms)
  # Remove old log files.
  max_old_files = 100
  # list of 2-tuples (path, mtime)
  file_mtime = []
  for basename in os.listdir(dirname):
    path = os.path.join(dirname, basename)
    try:
      file_mtime.append((path, os.stat(path).st_mtime))
    except FileNotFoundError:
      pass  # Some other instance of this deleted it already?
  if len(file_mtime) > max_old_files:
    file_mtime.sort(key=lambda x: x[1])
    for path, _ in file_mtime[:len(file_mtime) - max_old_files]:
      try:
        os.unlink(path)
      except FileNotFoundError:
        pass  # Some other instance of this deleted it already?
  stemname = '%s.%d' % (__name__, os.getpid())
  path = os.path.join(dirname, '%s.log' % stemname)
  handler = logging.handlers.RotatingFileHandler(
    path, maxBytes=2**20, backupCount=9, delay=True)
  handler.set_name(stemname)
  # Same as flask format.
  handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))
  # Replace open method with a method that sets permissions. This is the same
  # as the FileHandler._open method, but with a custom opener to set the
  # permissions on new files.
  handler._open = lambda: open(
    handler.baseFilename, handler.mode, encoding=handler.encoding,
    opener=lambda path, flags: os.open(path, flags, mode=0o600))
  app.logger.handlers.append(handler)
  app.logger.setLevel(level)


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
    """":param app: Flask app object
        :param reload_when_mtime_changes: If true, check mtime on disk and
         reload when it changes."""
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

  def _UpdateDigest(self, basename, path, mtime=None):
    """Update the cached entry for basename and return the digest."""
    with open(path, 'rb') as fh:
      if mtime is None:
        mtime = os.fstat(fh.fileno()).st_mtime
      digest = self._ComputeDigest(fh)
    with self._lock:
      fi = self._fi.get(basename, None)
      if fi:
        fi.Set(mtime, digest)
      else:
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
      path = self._PathFor(basename)
      digest = self._UpdateDigest(basename, path)
    self._app.logger.info('New digest for static file %s=%s', path, digest)
    return flask.url_for(self._static, filename=basename, v=digest)


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
      return FieldSetError(self, 'Missing value')
    s = valuelist[-1]  # Take only last value.
    min_secs = 0
    max_secs = 24*3600
    if len(s) > len(str(max_secs)):
      return FieldSetError(self, 'Invalid format')
    try:
      i = int(s)
    except ValueError:
      return FieldSetError(self, 'Not an integer')
    if i < min_secs or i > max_secs:
      return FieldSetError(self, 'Out of range')
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

  # TODO: Create a Field subclass for input type="button". This is mostly
  # implemented in the HTML template and JS for now.
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
  had_errors = HiddenField()

  def validate(self):
    """Override validate() to only validate fields that are used according to
      user specified configuration. Perform additional validation that applies
      to relationships among multiple fields. For example, the timedelta between
      end_time and start_time."""
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
          'Invalid period between start and end times: %s' % total_period)
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
              'Invalid number of repetitions for %s: %d' % (summary, num_reps))
    if self.set_alarms.data:
      # If alarms are enabled, validate additional required fields.
      for field in (self.alarm_before_secs, self.alarms_repeat):
        if not field.validate(self):
          form_valid = False
      if self.alarms_repeat.data:
        # If alarm repeats are enabled, validate additional.
        repeats_valid = True
        for field in (self.alarm_repetition_delay_secs,
                        self.alarm_repetitions):
          if not field.validate(self):
            repeats_valid = False
            form_valid = False
        if (repeats_valid and self.alarm_repetition_delay_secs.data is not None
            and self.alarm_repetitions.data is not None):
          rep_period = (self.alarm_repetition_delay_secs.data *
                          self.alarm_repetitions.data)
          if rep_period > datetime.timedelta(hours=24):
            form_valid = False
            self.alarm_repetition_delay_secs.data = None
            self.alarm_repetitions.data = None
            self.alarm_repetition_delay_secs.errors.append(
              'Invalid alarm repetition duration %s' % rep_period)
    return form_valid

  def IsHidden(self, field):
    """Return true if field should be hidden. Used to hide irrelevant fields.
    E.g, alarm duration if alarms are diabled. JS will be used to hide/unhide
    dynamically clientside. This is for the initial view before JS loads and
    runs.
    :param field: a field of ScheduleForm."""
    alarm_fields = [self.alarm_before_secs, self.alarms_repeat]
    alarms_repeat_fields = [self.alarm_repetitions,
                              self.alarm_repetition_delay_secs]
    if field in alarm_fields:
      return not self.set_alarms.data
    if field in alarms_repeat_fields:
      return not self.set_alarms.data or not self.alarms_repeat.data
    return False


del _d  # Defaults needed only for class ScheduleForm definition.


class RequestHandler(object):
  def __init__(self, uid_gens, static_versions, app, req):
    """Give HostUidGen instance and flask.request."""
    self._uid_gens = uid_gens
    self._static_versions = static_versions
    self._app = app
    self._req = req

  def Response(self):
    """Return the response to the request given in __init__."""
    try:
      if self._req.method == 'POST':
        rv = self._ValidateForm()
      else:
        rv = self._NewForm()
    except:
      # Exceptions. Don't render any user messages.
      self._app.logger.error('Unexpected exception %s', traceback.format_exc())
      rv = flask.make_response(
        flask.render_template('error.html',
            resources=self._static_versions,
            title='Internal Server Error',
            error_message='Internal Server Error'), 500)
    finally:
      self._app.logger.info(
        'method=%s path=%s remote=%s result=%s',
        self._req.method, self._req.path, self._req.remote_addr, rv.status_code)
      return rv

  def _IndexParams(self, form, autosubmit):
    return {
      'resources': self._static_versions,
      'summary_ph_in': EventForm._summary_ph,
      'period_ph_in': EventForm._period_ph,
      'delete_val_in' : EventForm._delete_val,
      'form': form,
      'autosubmit': 'true' if autosubmit else 'false',  # JS code
    }

  def _SendForm(self, form, autosubmit, response_code):
    return flask.make_response(
      flask.render_template('index.html',
                            **self._IndexParams(form, autosubmit)),
      response_code)

  def _NewForm(self):
    """Send the initial form."""
    return self._SendForm(ScheduleForm(), False, 200)

  def _BadRequestForm(self, form):
    """Recreate the form with user inputs and error messages."""
    form.had_errors.data = 'true'
    return self._SendForm(form, False, 400)

  def _ClearErrorsForm(self, form):
    """Send a form with error messages removed in response to a user fixing
    validation errors, then trigger an onload form.submit(). The ideal situation
    would be if browsers could accept multipart responses. Then, we'd send
    an inline HTML response and a text/calendar attachment in the same
    response. Instead, we must make the browser issue multiple requests."""
    form.had_errors.data = None
    return self._SendForm(form, True, 200)

  def _SetConfig(self, sched, form):
    """Set configuration data in sched from data in form.
    form should have been validated."""
    sched.merge_overlap          = form.merge_overlapping.data
    sched.set_alarms             = form.set_alarms.data
    sched.alarms_repeat          = form.alarms_repeat.data
    sched.alarm_repetitions      = form.alarm_repetitions.data
    sched.alarm_repetition_delay = form.alarm_repetition_delay_secs.data
    sched.alarm_before           = form.alarm_before_secs.data
    sched.show_busy              = form.show_busy.data
    sched.event_duration         = form.event_duration_secs.data

  def _ValidateForm(self):
    """Validate form data. If not valid, display form with error messages.
    If form data is valid, but was previously displayed with errors,
    redisplay without errors, then trigger a download by calling form.submit()
    from JS onload. Finally, if valid, and no errors were displayed previously,
    just respond with form data (fewest request-response round trips)."""
    form = ScheduleForm(self._req.form)
    if not form.validate():
      return self._BadRequestForm(form)
    if form.had_errors.data:
      return self._ClearErrorsForm(form)
    sched = repeating_ical_events.ScheduleBuilder(
      form.start_time.data, form.end_time.data)
    self._SetConfig(sched, form)
    for event in form.events:
      sched.AddRepeatingEvent(event.summary.data, event.period.data)
    cal = sched.BuildCalendar(self._uid_gens.UidGen(self._req))
    # TODO: Directly responding to form post with this text/calendar attachment
    # triggers a browser debug console warning "Resource interpreted as
    # Document". Setting target="_blank" would fix this in chrome, but we only
    # know that _blank is the correct target after successful validation. We
    # want the form and form with error messages to render to _self. We could
    # force multiple round-trips every time to get rid of this warning. As it
    # is now, the no-errors case is the optimal case in terms of round-trips.
    # The extra round trip to clean up the errors displayed is a nice UI
    # improvement. In firefox, _blank triggers popup blocking.
    resp = flask.Response(cal.to_ical(), mimetype='text/calendar')
    resp.headers.add('Content-Disposition', 'attachment',
        filename='repeating_events_%s.ics' % sched.start_time.strftime(
          '%Y_%m_%d'))
    return resp
