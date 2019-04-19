#!/usr/bin/env python
#
# Deprecated in favor of the iCalendar based web app.
#
# Use Google Calendar API and oauth to write directly into Google calendar with
# the configured parameters.
#

import apiclient
import argparse
import datetime
import httplib2
import os
import pytz
import sys
import time
import tzlocal

from apiclient import discovery
from oauth2client import file
from oauth2client import client
from oauth2client import tools

GOOGLE_DATA = os.path.join(os.getenv('HOME', '.'), 'src/google')

# CLIENT_SECRETS is name of a file containing the OAuth 2.0 information for this
# application, including client_id and client_secret. You can see the Client ID
# and Client secret on the APIs page in the Cloud Console:
# <https://cloud.google.com/console#/project/271002737103/apiui>
CLIENT_SECRETS = os.path.join(GOOGLE_DATA,
    'client_secret_271002737103.apps.googleusercontent.com.json')

# Set up a Flow object to be used for authentication.
# Add one or more of the following scopes. PLEASE ONLY ADD THE SCOPES YOU
# NEED. For more information on using scopes please see
# <https://developers.google.com/+/best-practices>.
FLOW = client.flow_from_clientsecrets(CLIENT_SECRETS,
  scope=[
      'https://www.googleapis.com/auth/calendar',
      'https://www.googleapis.com/auth/calendar.readonly',
    ],
    message=tools.message_if_missing(CLIENT_SECRETS))


## Note: All datetime objects are "naive" unless specifically stated otherwise.

def TimeOfDay(dt):
  """Return a timedelta representing the time of day in a datetime."""
  return datetime.timedelta(hours=dt.hour, minutes=dt.minute,
                            seconds=dt.second, microseconds=dt.microsecond)

def DayOfTime(dt):
  """Return a new datetime with the everything after day set to zero."""
  return datetime.datetime(year=dt.year, month=dt.month, day=dt.day)


class Scheduler(object):
  def __init__(self, service, calendar, local_tz):
    self._service = service
    self._cal_name = calendar
    self._local_tz = local_tz
    # self._cal is None if the calendar doesn't exist or was deleted.
    self._cal = self._GetCal()

  def _GetCal(self):
    """Return the CalendarListEntry with summary matching self._cal_name, or """
    """None if no match."""
    for cal in self._GetCalendars():
      if cal['summary'] == self._cal_name:
        return cal
    return None

  def _CreateCal(self):
    """Create a calendar with summary matching self._cal_name and """
    """return the CalendarListEntry for it."""
    create_req = {
      'summary': self._cal_name,
    }
    create_resp = self._service.calendars().insert(body=create_req).execute()
    insert_req = {
      'id': create_resp['id'],
    }
    try:
      return self._service.calendarList().insert(body=insert_req).execute()
    except:
      # We created but failed to insert. Delete the created calendar.
      self._service.calendars().delete(create_resp['id'])
      raise

  def _GetCalendars(self):
    """Return an iterator of CalendarListEntry for all calendars in """
    """self._service."""
    page_token = None
    while True:
      calendar_page = self._service.calendarList().list(
        pageToken=page_token).execute()
      for calendar_list_entry in calendar_page['items']:
        yield calendar_list_entry
      page_token = calendar_page.get('nextPageToken')
      if not page_token:
        break

  def _EnsureCal(self):
    if self._cal is None:
      self._cal = self._CreateCal()

  def Delete(self):
    if self._cal is None:
      return
    self._service.calendarList().delete(calendarId=self._cal['id']).execute()
    self._cal = None

  def CreateDmpsAlaSchedule(self, start_day, end_day, dmps_desc, ala_desc,
                            bedtime=datetime.timedelta(hours=1),
                            waketime=datetime.timedelta(hours=10)):
    self._EnsureCal()
    dose_time = start_day + bedtime + datetime.timedelta(hours=6)
    interval = datetime.timedelta(hours=3)
    both_desc = '%s + %s' % (dmps_desc, ala_desc)
    desc = both_desc
    last_dose_time = end_day + bedtime
    while dose_time <= last_dose_time:
      time_of_day = TimeOfDay(dose_time)
      add_reminder = time_of_day <= bedtime or time_of_day > waketime
      self._AddDose(dose_time, add_reminder, desc)
      dose_time += interval
      if desc == ala_desc:
        desc = both_desc
      else:
        desc = ala_desc

  def CreateSchedule(self, start, dose_interval, end_day,
                     bedtime=datetime.timedelta(hours=1),
                     waketime=datetime.timedelta(hours=10), desc=None):
    # Round end up to nearest bed time.
    final_bedtime = DayOfTime(end_day) + bedtime
    if final_bedtime < end_day:
      final_bedtime += datetime.timedelta(days=1)
    self._CreateSchedule(start, dose_interval, final_bedtime, bedtime, waketime,
                         desc=desc)

  def _CreateSchedule(self, start, dose_interval, end, bedtime, waketime,
                      desc=None):
    self._EnsureCal()
    while start <= end:
      start_day = DayOfTime(start)
      beddatetime = start_day + bedtime
      wakedatetime = start_day + waketime
      if wakedatetime <= beddatetime:
        wakedatetime += datetime.timedelta(days=1)
      # Rely on an alarm clock when sleeping. A calendar reminder would be
      # redundant.
      add_reminder = start <= beddatetime or start > wakedatetime
      self._AddDose(start, add_reminder, desc=desc)
      start += dose_interval

  def _AddDose(self, start, add_reminder, desc='Chelate'):
    """Create a calendar event for the given dose and return it."""
    event_time = self._UtcFormatLocalized(start)
    event = {
      'summary': desc,
      'start': {
        'dateTime': event_time,
      },
      'end': {
        'dateTime': event_time,
      },
      'reminders': {
        'useDefault': False,
        'overrides': [
        ],
      },
    }
    if add_reminder:
      event['reminders']['overrides'].append(
        {'method': 'popup',
         'minutes': 1})
    # We can get transient errors where sometimes the newly created calendar is
    # not found.
    max_tries = 10
    for i in xrange(max_tries):
      try:
        return self._service.events().insert(calendarId=self._cal['id'],
                                             body=event).execute()
      except apiclient.errors.HttpError as e:
        if e.resp.status != 404 or i == max_tries:
          raise
        time.sleep(1)

  def _UtcFormatLocalized(self, dt):
    """Return a string that converts dt to a localized time (including DST)
    formatted as offset from UTC according to RFC 3339."""
    offset_secs = int(datetime.timedelta.total_seconds(
      self._local_tz.utcoffset(dt)))
    if offset_secs > 0:
      raise Exception('UTC offset secs should be negative or zero: %d' % (
        offset_secs,))
    offset_hours = offset_secs / 3600
    offset_mins = int((offset_secs - offset_hours * 3600) / 60)
    return '%s-%02d:%02d' % (dt.strftime('%Y-%m-%dT%H:%M:%S.000'),
        abs(offset_hours), abs(offset_mins))


def main(argv):
  def GetDate(datestr):
    return datetime.datetime.strptime(datestr, '%Y-%m-%d')

  def GetDelta(timestr):
    hours, mins = map(lambda intstr: int(intstr), timestr.split(':'))
    return datetime.timedelta(hours=hours, minutes=mins)

  # Specifies an end day to use if --end_day is not specified.
  default_duration = datetime.timedelta(days=3, hours=12)

  flags_parser = argparse.ArgumentParser(
    description='Generates a Google Calendar description of Cutler protocol.',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[tools.argparser])
  flags_parser.add_argument(
    '--start_day',
    help='If specified, generate schedule starting on YYYY-MM-DD',
    type=GetDate)
  flags_parser.add_argument(
    '--end_day',
    help='Last day of the round',
    type=GetDate)
  flags_parser.add_argument(
    '--start_time',
    help='Generate schedule starting on HH:MM of --start_day',
    default=datetime.timedelta(hours=10),  # 10:00am
    type=GetDelta)
  flags_parser.add_argument(
    '--interval',
    help='Time between doses in HH::MM',
    default=datetime.timedelta(hours=3),
    type=GetDelta)
  flags_parser.add_argument('--calendar',
                            help='Calendar in which to write events',
                            default='Chelation')
  flags_parser.add_argument('--desc', help='Event description')
  flags_parser.add_argument('--delete',
                            help='If true, delete the existing calendar ' +
                            'before adding new events', action='store_true')
  flags_parser.add_argument('--dmps_ala', help='Generate a DMPS+ALA schedule',
                            action='store_true')
  flags_parser.add_argument('--dmps_desc', help='When --dmps_ala, ' +
                            'describes the DMPS dose')
  flags_parser.add_argument('--ala_desc', help='When --dmps_ala, ' +
                            'describes the ALA dose')
  flags_parser.add_argument('--local_tz_name', help='Name of local timezone. ' +
                            'If unset, attempt to use the local system ' +
                            'timezone')
  flags = flags_parser.parse_args()
  if not (flags.calendar and (flags.start_day or flags.delete)):
    flags_parser.print_help()
    return 1

  # If the credentials don't exist or are invalid run through the native client
  # flow. The Storage object will ensure that if successful the good
  # credentials will get written back to the file.
  storage = file.Storage(os.path.join(GOOGLE_DATA, os.path.basename(__file__)) +
                         '.dat')
  credentials = storage.get()
  if credentials is None or credentials.invalid:
    credentials = tools.run_flow(FLOW, storage, flags)

  # Create an httplib2.Http object to handle our HTTP requests and authorize it
  # with our good Credentials.
  http = httplib2.Http()
  http = credentials.authorize(http)

  # Construct the service object for the interacting with the Calendar API.
  service = discovery.build('calendar', 'v3', http=http)

  if flags.local_tz_name:
    local_tz = pytz.timezone(local_tz_name)
  else:
    local_tz = tzlocal.get_localzone()
  sched = Scheduler(service, flags.calendar, local_tz)
  if flags.delete:
    sched.Delete()
  if flags.start_day:
    if flags.dmps_ala:
      sched.CreateDmpsAlaSchedule(flags.start_day, flags.end_day,
                                  flags.dmps_desc, flags.ala_desc)
      # We ignore flags.interval in this case, and use every 3h for ALA and
      # every 6h for DMPS. Use flags.dmps_desc and flags.ala_desc rather than
      # flags.desc.
#       interval = datetime.timedelta(hours=6)
#       sched.CreateSchedule(start, interval, end,
#                            desc=('%s + %s' % (flags.dmps_desc,
#                                               flags.ala_desc)))
#       sched.CreateSchedule(start + datetime.timedelta(hours=3), interval, end,
#                            desc=flags.ala_desc)
    else:
      start = flags.start_day + flags.start_time
      if flags.end_day:
        end = flags.end_day
      else:
        # end gets rounded up to bedtime in CreateSchedule().
        end = start + default_duration
      sched.CreateSchedule(start, flags.interval, end, desc=flags.desc)
  return 0


# For more information on the Calendar API you can visit:
#
#   https://developers.google.com/google-apps/calendar/firstapp
#
# For more information on the Calendar API Python library surface you
# can visit:
#
#   https://developers.google.com/resources/api-libraries/documentation/calendar/v3/python/latest/
#
# For information on the Python Client Library visit:
#
#   https://developers.google.com/api-client-library/python/start/get_started
if __name__ == '__main__':
  main(sys.argv)
