import logging


def configure_logging(verbose: bool = False) -> None:
    """
    Configure root logging for the AnyScrape CLI.

    By default logs at INFO level with a simple time-stamped format.
    When verbose=True, DEBUG logs are also shown.
    """
    level = logging.DEBUG if verbose else logging.INFO
    # basicConfig is a no-op if logging is already configured, which is fine
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger for internal modules.
    """
    return logging.getLogger(name)


