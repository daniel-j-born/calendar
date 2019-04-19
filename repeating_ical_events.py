#!/usr/bin/env python3

import datetime
import icalendar
import random
import sys
import string
import threading


class UidGenerator(object):
  def __init__(self, base_domain):
    self._base_domain = base_domain
    self._domain = ''.join([random.choice(string.ascii_letters + string.digits)
                          for n in range(32)]) + '.' + base_domain
    self._next_id = 1
    self._lock = threading.Lock()

  def Domain(self): return self._domain

  def BaseDomain(self): return self._base_domain

  def GetUid(self):
    with self._lock:
      next_id = self._next_id
      self._next_id += 1
    return '%d@%s' % (next_id, self.Domain())


class DisplayAlarmBuilder(icalendar.Alarm):
  def __init__(self, description, trigger):
    super().__init__()
    # Required properties for valarm.
    self.add('action', 'DISPLAY')
    self.add('description', description)
    self.add('trigger', trigger)

  
class AudioAlarmBuilder(icalendar.Alarm):
  def __init__(self, trigger):
    super().__init__()
    # Required properties for valarm.
    self.add('action', 'AUDIO')
    self.add('trigger', trigger)

  
class EventBuilder(icalendar.Event):
  def __init__(self, uid, dtstamp):
    super().__init__()
    # uid and dtstamp are required properties of vevent.
    self.add('uid', uid)
    self.add('dtstamp', dtstamp)

  def AddDisplayAlarm(self, description, trigger):
    al = DisplayAlarmBuilder(description, trigger)
    self.add_component(al)
    return al

  def AddAudioAlarm(self, trigger):
    al = AudioAlarmBuilder(trigger)
    self.add_component(al)
    return al
  

class CalendarBuilder(icalendar.Calendar):
  def __init__(self, uid_gen):
    super().__init__()
    self._uid_gen = uid_gen
    # prodid and version are required properties of vcalendar.
    self.add('version', '1.0')
    self.add('prodid', '-//' + uid_gen.BaseDomain() +
               '//repeating_ical_events v1.0//EN')

  def AddEvent(self):
    """Return an EventBuilder for a vevent to be added."""
    ev = EventBuilder(self._uid_gen.GetUid(), datetime.datetime.utcnow())
    self.add_component(ev)
    return ev


class ScheduleBuilder(object):
  def __init__(self, start_time, end_time):
    """start_time and end_time are an inclusive range: events can occur
    at these precise times."""
    self.start_time = start_time
    self.end_time = end_time
    # List of (summary, datetime.timedelta).
    self._repeating_events = []
    self.SetDefaults()

  def SetDefaults(self):
    """Configurable attributes."""
    self.merge_overlap = True
    self.set_alarms = True
    self.alarms_repeat = True
    self.alarm_repititions = 60
    self.alarm_repitition_delay = datetime.timedelta(seconds=5)
    # Note: change to negative value in iCalendar objects.
    self.alarm_before = datetime.timedelta(seconds=60)
    self.show_busy = False
    self.event_duration = datetime.timedelta(seconds=60)

  def AddRepeatingEvent(self, summary, period):
    """Summary should be a short, single line of text."""
    self._repeating_events.append((summary, period))
    return self

  def BuildCalendar(self, uid_gen):
    """Return a icalendar.Calendar object for the schedule. RRULEs of
    hourly granularity or smaller are not supported in the UI of most
    calendar programs, so create separate entries rather than an
    RRULE."""
    # Map datetime to list of EventBuilder.
    events = {}
    cal = CalendarBuilder(uid_gen)
    for summary, period in self._repeating_events:
      next_event_time = self.start_time
      while next_event_time <= self.end_time:
        next_event_time_events = events.setdefault(next_event_time, [])
        if self.merge_overlap and next_event_time_events:
          ev_summary = next_event_time_events[0].get('summary')
          if ev_summary:
            ev_summary = ev_summary + ' ' + summary
          else:
            ev_summary = summary
          next_event_time_events[0]['summary'] = ev_summary
        else:
          next_event_time_events.append(self._AddEvent(
            cal, summary, next_event_time))
        next_event_time += period
    return cal

  def _AddEvent(self, cal, summary, event_time):
    ev = cal.AddEvent()
    ev.add('dtstart', event_time)
    ev.add('duration', self.event_duration)
    if self.show_busy:
      transp = 'OPAQUE'
    else:
      transp = 'TRANSPARENT'
    ev.add('transp', transp)
    ev.add('summary', summary)
    if self.set_alarms:
      al = ev.AddDisplayAlarm(summary, -self.alarm_before)
      if self.alarms_repeat:
        al.add('duration', self.alarm_repitition_delay)
        al.add('repeat', self.alarm_repititions)
    return ev


def main(argv):
  start_time = datetime.datetime(year=2019, month=4, day=25, hour=7, minute=0,
                                  second=0)
  end_time = datetime.datetime(year=2019, month=4, day=29, hour=1, minute=0,
                                  second=0)
  scheduler = ScheduleBuilder(start_time, end_time)
  scheduler.AddRepeatingEvent('Event Type 1', datetime.timedelta(hours=6))
  scheduler.AddRepeatingEvent('Event Type 2', datetime.timedelta(hours=2))
  cal = scheduler.BuildCalendar(UidGenerator('example.com'))

  # Must be written as binary, not Unicode, as sys.stdout requires.
  with open('/dev/stdout', 'wb') as outf:
    outf.write(cal.to_ical())


if __name__ == '__main__':
  main(sys.argv)
