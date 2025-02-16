from rootio.config import *
import json
from rootio.content.models import ContentTrack


class AdvertisementAction:

    def __init__(self, track_id, start_time, duration, program):
        self.__track_id = track_id
        self.__track = None
        self.__is_valid = True
        self.start_time = start_time
        self.duration = duration
        self.program = program
        self.__media_expected_to_stop = False
        self.__call_answer_info = None
        self.__call_handler = self.program.radio_station.call_handler
        self.program.log_program_activity("Done initing ads action for program {0}".format(self.program.name))

    def start(self):
        self.program.set_running_action(self)
        try:
            self.__load_track()
            if self.__track is not None and len(self.__track.files) > 0:
                call_result = self.__request_station_call()
                if not call_result[0]:  # !!
                    self.stop(False)
            else:  # Track exists but contains no content
                self.stop(False)
        except Exception as e:
            self.stop(False)
            self.program.radio_station.logger.error("error {err} in ads_action.__start".format(err=e.message))

    def stop(self, graceful=True, call_info=None):
        if call_info is not None:
            self.__stop_media(call_info)
        elif self.__call_answer_info is not None:
            self.__stop_media(self.__call_answer_info)
        self.__deregister_listeners()
        self.program.notify_program_action_stopped(graceful, call_info)

    def notify_call_answered(self, answer_info):
        self.program.log_program_activity(
            "Received call answer notification for ads action of {0} program".format(self.program.name))
        self.__call_answer_info = answer_info
        self.__call_handler.register_for_call_hangup(self, answer_info['Caller-Destination-Number'][-11:])
        self.__play_media(self.__call_answer_info)

    def __load_track(self):  # load the media to be played
        self.__track = self.program.radio_station.db.query(ContentTrack).filter(ContentTrack.id == self.__track_id).first()

    def __request_station_call(self):  # call the number specified thru plivo
        # Check if the call exists, start with the least likely number to be called
        if self.program.radio_station.station.secondary_transmitter_phone is not None and self.__call_handler.call_exists(
                self.program.radio_station.station.secondary_transmitter_phone.raw_number):
            result = self.__call_handler.call(self,
                                              self.program.radio_station.station.secondary_transmitter_phone.raw_number,
                                              self.program.name, False, self.duration)
            return result
        elif self.program.radio_station.station.primary_transmitter_phone is not None and self.__call_handler.call_exists(
                self.program.radio_station.station.primary_transmitter_phone.raw_number):
            result = self.__call_handler.call(self,
                                              self.program.radio_station.station.primary_transmitter_phone.raw_number,
                                              self.program.name, False, self.duration)
            return result
        elif self.program.radio_station.station.sip_username is not None and self.__call_handler.call_exists(
                self.program.radio_station.station.sip_username):
            result = self.__call_handler.call(self, self.program.radio_station.station.sip_username, self.program.name,
                                              True, self.duration)
            self.program.log_program_activity("result of station call via SIP is " + str(result))
            return result

        # At this point we are sure that no call to the station exists. We will try to initiate a new call
        if self.program.radio_station.station.is_high_bandwidth:
            result = self.__call_station_via_sip()
            if result is None or not result[0]:  # Now try calling the SIM (ideally do primary, then secondary)
                result = self.__call_station_via_goip()
        else:
            result = self.__call_station_via_goip()
        return result

    def __call_station_via_sip(self):
        # Try a high bandwidth call first
        if self.program.radio_station.station.sip_username is not None:
            result = self.__call_handler.call(self, self.program.radio_station.station.sip_username, self.program.name, True,
                                              self.duration)
            self.program.log_program_activity("result of station call via SIP is " + str(result))
            return result

    def __call_station_via_goip(self):
        result = None
        if self.program.radio_station.station.primary_transmitter_phone is not None:
            result = self.__call_handler.call(self, self.program.radio_station.station.primary_transmitter_phone.raw_number,
                                              self.program.name, False,
                                          self.duration)
            self.program.log_program_activity("result of station call (primary) via GoIP is " + str(result))
            if not result[0] and self.program.radio_station.station.secondary_transmitter_phone is not None:  # Go for the secondary line of the station, if duo SIM phone
                result = self.__call_handler.call(self,
                                              self.program.radio_station.station.secondary_transmitter_phone.raw_number,
                                                  self.program.name, False,
                                              self.duration)
                self.program.log_program_activity("result of station call (secondary) via GoIP is " + str(result))
        return result

    def __play_media(self, call_info):  # play the media in the array
        #self.__load_track()
        self.program.log_program_activity(
            "Playing media {0}".format(self.__track.files[len(self.__track.files) - 1].name))
        self.__listen_for_media_play_stop()

        # Always play the last file for ads
        result = self.__call_handler.play(call_info['Channel-Call-UUID'], os.path.join(DefaultConfig.CONTENT_DIR,
                                                                                       self.__track.files[len(
                                                                                           self.__track.files) - 1].uri))
        self.program.log_program_activity('result of play is ' + result)
        if result.split(" ")[0] != "+OK":
            self.stop(False, call_info)

    def __stop_media(self, event_json):  # stop the media being played by the player
        try:
            self.program.log_program_activity(
                "Deregistered, all good, about to order hangup for {0}".format(self.program.name))
            self.__call_handler.deregister_for_call_hangup(event_json['Caller-Destination-Number'][-11:])
            result = self.__call_handler.stop_play(self.__call_answer_info['Channel-Call-UUID'], self.__track.id)
            self.program.log_program_activity('result of stop play is ' + result)
        except Exception as e:
            self.program.radio_station.logger.error("error {err} in ads_action.__stop_media".format(err=e.message))
            return

    def notify_call_hangup(self, event_json):
        self.program.log_program_activity('Call hangup before end of program!')
        #self.stop(False, event_json)
        self.__request_station_call()

    def notify_media_play_stop(self, event_json):
        self.program.radio_station.logger.info(
            "Played all media, stopping media play in Media action for {0}".format(self.program.name))
        #if event_json["Media-Bug-Target"] == os.path.join(DefaultConfig.CONTENT_DIR, self.__track.files[
         #   len(self.__track.files) - 1].uri):
        self.stop(True, event_json)  # program.notify_program_action_stopped(self)
        self.__is_valid = False

    def __listen_for_media_play_stop(self):
        self.__call_handler.register_for_media_playback_stop(self, self.__call_answer_info['Caller-Destination-Number'])

    def __deregister_listeners(self):
        if self.__call_answer_info is not None:
            self.__call_handler.deregister_for_media_playback_stop(self.__call_answer_info['Caller-Destination-Number'][-11:])
            self.__call_handler.deregister_for_call_hangup(self.__call_answer_info['Caller-Destination-Number'][-11:])