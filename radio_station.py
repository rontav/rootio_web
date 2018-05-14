import time

from rootio.radio.models import Station

from call_handler import CallHandler
from program_handler import ProgramHandler


class RadioStation(Station):

    def run(self):
        self.__program_handler.run()
        while True:
            time.sleep(1)
        return

    def stop(self):
        self.call_handler.stop()
        self.__program_handler.stop()
        pass

    def __init__(self, station_id, db, logger):
        self.__program_handler = ProgramHandler(self.db, self)
        self.call_handler = CallHandler(self)
        self.id = station_id
        self.logger = logger
        self.db = db
        self.station = self.db.query(Station).filter(Station.id == station_id).one()
        self.logger.info("Starting up station {0}".format(self.station.name))
        return
