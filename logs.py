import logging

logger = logging.getLogger('CREST')

infoHandler= logging.StreamHandler()
infoHandler.setLevel(logging.INFO)

infoFormatter= logging.Formatter('%(name)s  -  %(asctime)s  -  %(message)s')

infoHandler.setFormatter(infoFormatter)

logger.addHandler(infoHandler)

logger.warning('starts processing...')
