import logging


class CompactFormatter(logging.Formatter):
    def format(self, record):
        # Use custom formatting based on log level and extra fields
        if record.levelno == logging.DEBUG:
            # Expect a 'test_stage' field for debug messages
            test_stage = getattr(record, "test_stage", "Unknown Stage")
            return f"[*] - {test_stage} - {record.getMessage()}"

        elif record.levelno == logging.INFO:
            # If extra info is provided, treat as a pass message
            if all(
                hasattr(record, attr) for attr in ("microservice", "expected", "real")
            ):
                return f"[+] - PASS - {record.microservice} - {record.expected}:{record.real}"
            else:
                # Otherwise, simply format the message
                return f"[+] - {record.getMessage()}"

        elif record.levelno == logging.ERROR:
            # If extra info is provided, treat as a fail message
            if all(
                hasattr(record, attr) for attr in ("microservice", "expected", "real")
            ):
                return f"[!] - FAIL - {record.microservice} - {record.expected}:{record.real}"
            else:
                return f"[!] - {record.getMessage()}"

        else:
            return record.getMessage()


def setup_logger(name=None, level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Remove any existing handlers
    logger.handlers = []
    handler = logging.StreamHandler()
    handler.setFormatter(CompactFormatter())
    logger.addHandler(handler)
    return logger
