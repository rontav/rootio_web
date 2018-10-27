import json
from datetime import timedelta, datetime
from sets import Set

from apscheduler.scheduler import Scheduler

from rootio.radio.models import Person


class PhoneStatus:
    REJECTING = 1
    QUEUING = 2
    ANSWERING = 3
    CONFERENCING = 4
    IVR = 5
    RINGING = 6


class OutcallAction:

    def __init__(self, host_id, start_time, duration, program):
        self.__host_id = host_id
        self.start_time = start_time
        self.duration = duration
        self.program = program
        self.__scheduler = Scheduler()
        self.__available_calls = dict()
        self.__in_talkshow_setup = False
        self.__host = None
        self.__community_call_UUIDs = dict()
        self.__call_handler = self.program.radio_station.call_handler
        self.__phone_status = PhoneStatus.QUEUING
        self.__interested_participants = Set([])

    def start(self):
        try:
            self.__in_talkshow_setup = True
            self.__host = self.__get_host(self.__host_id)
            if self.__host is None or self.__host.phone is None:
                self.stop(False)
                return
            # self.program.set_running_action(self)
            self.__scheduler.start()
            self.__call_handler.register_for_incoming_calls(self)
            self.__call_handler.register_for_incoming_dtmf(self, str(self.__host.phone.raw_number))
            self.__call_handler.register_for_host_call(self, str(self.__host.phone.raw_number))
            self.request_host_call()
        except Exception as e:
            print e

    def stop(self, graceful=True, call_info=None):
        self.hangup_call()
        # Stop scheduler
        self.__scheduler.shutdown()
        # deregister from any triggers
        self.__call_handler.deregister_for_incoming_calls(self)
        self.__call_handler.deregister_for_incoming_dtmf(str(self.__host.phone.raw_number))
        self.program.notify_program_action_stopped(graceful, call_info)

    def __get_host(self, host_id):
        host = self.program.radio_station.db.query(Person).filter(Person.id == host_id).first()
        return host

    def request_host_call(self):
        self.__in_talkshow_setup = True
        result = self.__call_handler.call(self, self.__host.phone.raw_number, None, False,
                                          15)  # call ends in 15 mins max
        self.program.log_program_activity("result of host call is " + str(result))
        if not result[0]:
            self.stop(False)

    def __request_station_call(self):  # call the number specified thru plivo
        if self.program.radio_station.station.is_high_bandwidth:
            result = self.__call_station_via_sip()
            if result is None or not result[0]:  # Now try calling the SIM (ideally do primary, then secondary)
                result = self.__call_station_via_goip()
        else:
            result = self.__call_station_via_goip()
        if result is None or not result[0]:
            self.stop(False)

    def __call_station_via_sip(self):
        result = None
        # Try a high bandwidth call first
        sip_info = self.__get_sip_info()
        if sip_info is not None and 'sip_username' in sip_info:
            result = self.__call_handler.call(self, sip_info['sip_username'], self.__host.phone.raw_number, True,
                                              self.duration)
            self.program.log_program_activity("result of station call via SIP is " + str(result))
        return result

    def __call_station_via_goip(self):
        result = None
        if self.program.radio_station.station.primary_transmitter_phone is not None:
            result = self.__call_handler.call(self, self.program.radio_station.station.primary_transmitter_phone.raw_number,
                                          self.__host.phone.raw_number, False,
                                          self.duration)
            self.program.log_program_activity("result of station call (primary) via GoIP is " + str(result))
            if not result[0] and self.program.radio_station.station.secondary_transmitter_phone is not None:  # Go for the secondary line of the station, if duo SIM phone
                result = self.__call_handler.call(self,
                                              self.program.radio_station.station.secondary_transmitter_phone.raw_number,
                                              self.__host.phone.raw_number, False,
                                              self.duration)
                self.program.log_program_activity("result of station call (secondary) via GoIP is " + str(result))
        return result

    def __get_sip_info(self):
        try:
            sip_info = json.loads(self.program.radio_station.station.sip_settings)
            return sip_info
        except ValueError:
            return None

    def notify_call_answered(self, answer_info):
        if self.__host.phone.raw_number not in self.__available_calls:
            self.__available_calls[answer_info['Caller-Destination-Number'][-9:]] = answer_info
            self.__inquire_host_readiness()
            self.program.log_program_activity("host call has been answered")
        else:  # This notification is from answering the host call
            self.__available_calls[answer_info['Caller-Destination-Number'][-9:]] = answer_info
            # result1 = self.__schedule_warning()
            # result2 = self.__schedule_hangup()
        self.__call_handler.register_for_call_hangup(self, answer_info['Caller-Destination-Number'][-9:])

    def warn_number(self):
        seconds = self.duration - self.__warning_time
        if self.__host.phone.raw_number in self.__available_calls and 'Channel-Call-UUID' in self.__available_calls[
            self.__host.phone.raw_number]:
            result = self.__call_handler.speak(
                'Your call will end in ' + str(seconds) + 'seconds',
                self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])
            self.program.log_program_activity("result of warning is " + result)

    def __pause_call(self):  # hangup and schedule to call later
        self.__schedule_host_callback()
        self.hangup_call()

    def notify_call_hangup(self, event_json):
        if 'Caller-Destination-Number' in event_json:
            if event_json[
                'Caller-Destination-Number'] in self.__community_call_UUIDs:  # a community caller is hanging up
                del self.__community_call_UUIDs[event_json['Caller-Destination-Number']]
                self.__call_handler.deregister_for_call_hangup(event_json['Caller-Destination-Number'])
            else:  # It is a hangup by the station or the host
                self.program.log_program_activity(
                    "Program terminated because {0} hangup".format(event_json['Caller-Destination-Number']))
                self.stop(True)

    def __inquire_host_readiness(self):
        self.__call_handler.speak(
            'You are scheduled to host a talk show at this time. If you are ready, press one, if not ready, press two',
            self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])
        self.program.log_program_activity("Asking if host is ready")

    def hangup_call(self):  # hangup the ongoing call
        for available_call in self.__available_calls:
            self.__call_handler.deregister_for_call_hangup(available_call)
            self.__call_handler.hangup(self.__available_calls[available_call]['Channel-Call-UUID'])
        self.__available_calls = dict()  # empty available calls. they all are hung up

    def notify_incoming_dtmf(self, dtmf_info):
        dtmf_json = dtmf_info
        dtmf_digit = dtmf_json["DTMF-Digit"]
        if dtmf_digit == "1" and self.__in_talkshow_setup:
            self.program.log_program_activity("Host is ready, we are calling the station")
            self.__request_station_call()
            self.__in_talkshow_setup = False

        elif dtmf_digit == "2" and self.__in_talkshow_setup:  # stop the music, put this live on air
            self.program.log_program_activity("Host is not ready. We will hangup Arghhh!")
            self.hangup_call()
            self.__in_talkshow_setup = False

        elif dtmf_digit == "3":  # put the station =in auto_answer
            if self.__phone_status != PhoneStatus.ANSWERING:
                self.__phone_status = PhoneStatus.ANSWERING
                self.__call_handler.speak('All incoming calls will be automatically answered', self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])
            else:
                self.__phone_status = PhoneStatus.REJECTING
                self.__call_handler.speak('All incoming calls will be rejected',self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])

        elif dtmf_digit == "4":  # disable auto answer, reject and record all incoming calls
            if self.__phone_status != PhoneStatus.QUEUING:
                self.__phone_status = PhoneStatus.QUEUING
                self.__call_handler.speak(
                    'All incoming calls will be queued for call back',
                    self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])
            else:
                self.__phone_status = PhoneStatus.REJECTING
                self.__call_handler.speak(
                    'All incoming calls will be rejected',
                    self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])

        elif dtmf_digit == "5":  # dequeue and call from queue of calls that were queued
            for caller in self.__interested_participants:
                result = self.__call_handler.call(self, caller, None, None, self.duration)
                self.program.log_program_activity("result of participant call is {0}".format(str(result)))
                self.__community_call_UUIDs[caller] = result[1]
                self.__call_handler.register_for_call_hangup(self, caller)
                self.__interested_participants.discard(caller)
                return

        elif dtmf_digit == "6":  # terminate the current caller
            for community_call_UUID in self.__community_call_UUIDs:
                self.__call_handler.hangup(self.__community_call_UUIDs[community_call_UUID])
            pass

        elif dtmf_digit == "7":  # Take a 5 min music break
            self.__call_handler.speak('You will be called back in 5 minutes',self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])
            self.program.log_program_activity("Host is taking a break")
            self.__pause_call()

    def notify_host_call(self, call_info):
        # hangup the call
        self.__call_handler.hangup(call_info['Channel-Call-UUID'])
        # reset program
        # self.stop()
        # restart program
        self.start()

    def notify_incoming_call(self, call_info):
        if self.__phone_status == PhoneStatus.ANSWERING:  # answer the phone call, join it to the conference
            if len(self.__community_call_UUIDs) == 0:
                self.__call_handler.bridge_incoming_call(call_info['Channel-Call-UUID'], "{0}_{1}".format(self.program.id, self.program.radio_station.id))
                self.__call_handler.register_for_call_hangup(self, call_info['Caller-Destination-Number'])
                self.__community_call_UUIDs[call_info['Caller-Destination-Number']] = call_info['Channel-Call-UUID']
                self.program.log_program_activity(
                    "Call from community caller {0} was auto-answered".format(call_info['Caller-Destination-Number']))
        elif self.__phone_status == PhoneStatus.QUEUING:  # Hangup the phone, call back later
            self.__interested_participants.add(call_info['Caller-ANI'])
            self.__call_handler.speak(
                'You have a new caller on the line',
                self.__available_calls[self.__host.phone.raw_number]['Channel-Call-UUID'])
            self.__call_handler.hangup(call_info['Channel-Call-UUID'])
            self.program.log_program_activity(
                "Call from community caller {0} was queued".format(call_info['Caller-Destination-Number']))

        elif self.__phone_status == PhoneStatus.REJECTING:  # Hangup the call
            self.__call_handler.hangup(call_info['Channel-Call-UUID']);
            self.program.log_program_activity(
                "Call from community caller {0} was rejected".format(call_info['Caller-Destination-Number']))

    def __schedule_host_callback(self):
        time_delta = timedelta(seconds=30)  # one minutes
        now = datetime.now()
        callback_time = now + time_delta 
        self.__scheduler.add_date_job(getattr(self, 'request_host_call'), callback_time)

    def __schedule_warning(self):
        time_delta = timedelta(seconds=self.__warning_time)
        now = datetime.utcnow()
        warning_time = now + time_delta
        self.__scheduler.add_date_job(getattr(self, 'warn_number'), warning_time)

    def __schedule_hangup(self):
        time_delta = timedelta(seconds=self.duration)
        now = datetime.utcnow()
        hangup_time = now + time_delta
        self.__scheduler.add_date_job(getattr(self, 'hangup_call'), hangup_time)

    def __deregister_listeners(self):
        for available_call in self.__available_calls:
            self.__call_handler.deregister_for_call_hangup(available_call)
        self.__call_handler.deregister_for_incoming_calls(self)
        self.__call_handler.deregister_for_incoming_dtmf(str(self.__host.phone.raw_number))
