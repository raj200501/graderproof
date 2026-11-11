import os
import sys

sys.path.insert(0, os.getcwd())


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)

CASES = [
    ("userId", "user_id"), ("HTTPServer", "http_server"), ("getHTTPResponseCode", "get_http_response_code"),
    ("version2Update", "version2_update"), ("simple", "simple"), ("ABC", "abc"), ("parseXML", "parse_xml"),
    ("Already", "already"), ("S3Bucket", "s3_bucket"), ("XMLHttpRequest", "xml_http_request"), ("aB", "a_b"),
    ("A", "a"), ("utf8Encode", "utf8_encode"), ("totalAmountUSD", "total_amount_usd"),
]

try:
    from naming import to_snake
except Exception as exc:
    fail("cannot import to_snake from naming.py: %r" % (exc,))

for name, expected in CASES:
    try:
        got = to_snake(name)
    except Exception as exc:
        fail("to_snake(%r) raised %r" % (name, exc))
    if got != expected:
        fail("to_snake(%r) = %r, expected %r" % (name, got, expected))

print("ok")
