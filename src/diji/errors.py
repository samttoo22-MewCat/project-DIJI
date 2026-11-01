"""Correlate failures without publishing provider payloads or exception text."""
import logging
import uuid


def report_error(error,operation):
    error_id=uuid.uuid4().hex
    logging.getLogger('diji.errors').warning('%s failed; error_id=%s error_type=%s',operation,error_id,type(error).__name__)
    return error_id
