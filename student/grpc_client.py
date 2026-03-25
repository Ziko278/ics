import grpc
import sys
import os

sys.path.insert(0, '/var/www/ics')

import fingerprint_pb2
import fingerprint_pb2_grpc

_channel = None
_stub = None

def get_stub():
    global _channel, _stub
    if _stub is None:
        _channel = grpc.insecure_channel('localhost:4134')
        _stub = fingerprint_pb2_grpc.FingerPrintStub(_channel)
    return _stub

def enroll_fmd(raw_fmds: list) -> str:
    """Takes list of raw FMD strings, returns single enrolled FMD string."""
    stub = get_stub()
    request = fingerprint_pb2.EnrollmentRequest(
        fmdCandidates=[
            fingerprint_pb2.PreEnrolledFMD(base64PreEnrolledFMD=f)
            for f in raw_fmds
        ]
    )
    response = stub.EnrollFingerprint(request)
    return response.base64EnrolledFMD

def verify_fmd(probe_fmd: str, enrolled_fmd: str) -> bool:
    """Compare a raw probe FMD against one enrolled FMD."""
    stub = get_stub()
    request = fingerprint_pb2.VerificationRequest(
        targetFMD=fingerprint_pb2.PreEnrolledFMD(base64PreEnrolledFMD=probe_fmd),
        fmdCandidates=[fingerprint_pb2.EnrolledFMD(base64EnrolledFMD=enrolled_fmd)]
    )
    response = stub.VerifyFingerprint(request)
    return response.match