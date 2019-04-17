#!/usr/bin/env python3

import datetime
import icalendar
import random
import sys
import string
import threading


DOMAIN = 'danborn.net'


class UidGenerator(object):
  def __init__(self):
    self._domain = ''.join([random.choice(string.ascii_letters + string.digits)
                          for n in range(32)]) + '.' + DOMAIN
    self._next_id = 1
    self._lock = threading.Lock()

  def GetUid(self):
    with self._lock:
      next_id = self._next_id
      self._next_id += 1
    return '%d@%s' % (next_id, self._domain)


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
    self.add('prodid', '-//' + DOMAIN + '//repeating_ical_events v1.0//EN')

  def AddEvent(self):
    """Return an EventBuilder for a vevent to be added."""
    ev = EventBuilder(self._uid_gen.GetUid(), datetime.datetime.utcnow())
    self.add_component(ev)
    return ev


def main(argv):
  builder = CalendarBuilder(UidGenerator())
  # Note: No rrule property for compatibility. Most programs don't support
  # hourly rules in the UI, and shouldn't be trusted to parse such rules
  # correctly.
  ev = builder.AddEvent()

  # TODO: generate schedule. now + 2m for testing
  ev.add('dtstart', datetime.datetime.now() +
           datetime.timedelta(seconds=180))

  # Non-zero duration for compatibility.
  ev.add('duration', datetime.timedelta(seconds=60))

  # Takes no 'busy' time.
  ev.add('transp', 'TRANSPARENT')

  # TODO: description property is for multi-line text. summary is one line.
  # This should be from UI
  summary = 'Event summary goes here'
  ev.add('summary', summary)

  # TODO: warning time should be configurable in UI
  al = ev.AddDisplayAlarm(summary, -datetime.timedelta(seconds=60))

  # TODO: not sure what this does. make configurable in the UI
  al.add('duration', datetime.timedelta(seconds=5))
  al.add('repeat', 60)

  # TODO: duplicate alarm?
  #al = ev.AddAudioAlarm(-datetime.timedelta(seconds=60))
  #al.add('duration', datetime.timedelta(seconds=5))
  #al.add('repeat', 60)
  
  # Must be written as binary, not Unicode, as sys.stdout requires.
  with open('/dev/stdout', 'wb') as outf:
    outf.write(builder.to_ical())


if __name__ == '__main__':
  main(sys.argv)
