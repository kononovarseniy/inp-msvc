import csv
import logging
from concurrent.futures.thread import ThreadPoolExecutor

from gui.worker import Worker

LOGGER = logging.getLogger('data_logger')


class DataLogger:
    def __init__(self, filename):
        self._file = open(filename, 'a', 1)  # One line buffering
        self._writer = csv.writer(self._file)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='DataLogger')
        LOGGER.info('Data logger started')

    def add_worker(self, worker: Worker):
        worker.connect(Worker.CELL_UPDATED, self._cell_updated)

    def _cell_updated(self, worker: Worker, index: int):
        state = worker.get_cell_state(index)
        row = (
            worker.get_device_address().name,
            index,
            state.enabled.actual,
            '%.1f' % state.voltage_set.actual,
            '%.1f' % state.voltage_measured,
            '%.1f' % state.current_measured,
            '%.1f' % state.current_limit.actual,
            state.ramp_down_speed.actual,
            state.ramp_up_speed.actual
        )
        # TODO: add exception handling inside done_callback
        self._executor.submit(self._writer.writerow, row)
