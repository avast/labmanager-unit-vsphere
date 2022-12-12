import logging
from web.settings import Settings


logger = logging.getLogger(__name__)


def stats_increment_metric(subprefix, metric):
    if Settings.statsd_client:
        try:
            Settings.statsd_client.incr(f"{Settings.app['statsd']['prefix']}.{subprefix}.{metric}")
        except Exception as ex:
            Settings.raven.captureException(exc_info=True)
            logger.warning('stats_increment_metric failed: ', exc_info=True)


def stats_increment_metric_worker(metric):
    stats_increment_metric('worker.actions', metric)
