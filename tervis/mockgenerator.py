import time
import json
import random
import logging
import itertools
import functools

from collections import defaultdict

from ._compat import text_type


logger = logging.getLogger(__name__)


PROJECT_POOL_INITIAL_SIZE = 10
SESSION_POOL_INITIAL_SIZE = 10

SESSION_CREATION_PROBABILITY = 0.007
SESSION_CLOSE_PROBABILITY = 0.002
SESSION_FALSE_CLOSE_PROBABILITY = 0.001
SESSION_DROP_PROBABILITY = 0.005

TICK_DURATION = 0.1
TICK_PROBABILITY = 0.1


def generate(random, timestamp):
    projects = range(1, PROJECT_POOL_INITIAL_SIZE + 1)

    session_sequences = defaultdict(lambda: itertools.count(1))
    sessions = defaultdict(lambda: itertools.count(0))

    # Initialize the session pool.
    for project in projects:
        for session in range(1, SESSION_POOL_INITIAL_SIZE + 1):
            sid = next(session_sequences[project])
            sessions[(project, sid)]  # touch

    logger.debug('Initialized session pool, %s sessions '
                 'currently active.', len(sessions))

    def create_session():
        project = random.choice(projects)
        sid = next(session_sequences[project])
        key = (project, sid)
        sessions[key]  # touch
        logger.debug('Created session %r, %s sessions currently '
                     'active.', key, len(sessions))
        return key

    while True:
        if random.random() <= TICK_PROBABILITY:
            timestamp = timestamp + TICK_DURATION

        if random.random() <= SESSION_CREATION_PROBABILITY:
            key = create_session()
        else:
            try:
                key = random.sample(sessions.keys(), 1)[0]
            except ValueError:
                key = create_session()

        project, sid = key

        # TODO: Skip or generate out-of-order operation IDs.
        oid = next(sessions[key])

        ty = 'op'

        if random.random() <= SESSION_FALSE_CLOSE_PROBABILITY:
            ty = 'cl'
        if random.random() <= SESSION_CLOSE_PROBABILITY:
            del sessions[key]
            logger.debug('Deleted session %r, %s sessions currently '
                         'active.', key, len(sessions))
            ty = 'cl'
        elif random.random() <= SESSION_DROP_PROBABILITY:
            del sessions[key]
            logger.debug('Dropped session %r, %s sessions currently '
                         'active.', key, len(sessions))

        yield timestamp, project, {
            'sid': sid,
            'oid': oid,
            'ts': timestamp + random.triangular(-5 * 60, 10 * 60, 0),
            'ty': ty,
        }


class MockGenerator(object):

    def __init__(self, env, seed=None, epoch=None):
        self.env = env
        self.producer = env.connector.get_kafka_producer()

        if epoch is None:
            epoch = time.time()
        if seed is None:
            seed = time.time()

        self.epoch = epoch
        self.seed = seed
        self.random = random.Random(seed)

    def run(self, count=None):
        logger.info('Using random seed: {}'.format(self.seed))

        events = generate(self.random, self.epoch)
        if count is not None:
            events = itertools.islice(events, count)

        start = time.time()

        i = 0
        try:
            for i, (timestamp, project, event) in enumerate(events, 1):
                produce = functools.partial(
                    self.producer.produce, 'events',
                    json.dumps([project, event]).encode('utf-8'),
                    key=text_type(project).encode('utf-8'))
                try:
                    produce()
                except BufferError as e:
                    logger.info(
                        'Caught %r, waiting for %s events to be produced...',
                        e,
                        len(self.producer),
                    )
                    self.producer.flush()  # wait for buffer to empty
                    logger.info('Done waiting, continue to generate events...')
                    produce()

                if i % 1000 == 0:
                    logger.info('%s events produced, current timestamp is %s.',
                                i, timestamp)
        except KeyboardInterrupt:
            logger.info(
                'Waiting for producer to flush %s events before exiting...',
                len(self.producer),
            )

        self.producer.flush()

        stop = time.time()
        duration = stop - start
        logger.info('%s total events produced in %0.2f seconds '
                    '(%0.2f events/sec.)', i, duration, (i / duration))
