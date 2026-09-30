import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(levelname)s [%(name)s] %(message)s",
        force=True,
    )
