import logging
def formatter(module):
    logger = logging.getLogger(module)

    infoHandler= logging.StreamHandler()
    infoHandler.setLevel(logging.INFO)

    infoFormatter= logging.Formatter('%(name)s  -  %(asctime)s  -  %(message)s')

    infoHandler.setFormatter(infoFormatter)

    logger.addHandler(infoHandler)

    return logger

    # logger.warning('starts processing...')
