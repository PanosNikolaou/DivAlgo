import schemathesis
import pytest

# Load the OpenAPI schema from your API docs URL.
schema = schemathesis.from_uri("http://127.0.0.1:5000/apispec_1.json")

# This decorator will automatically generate test cases for all endpoints defined in the schema.
@schema.parametrize()
def test_api(case):
    # This call_and_validate() method makes a request using the generated test case
    # and validates that the response conforms to the schema.
    case.call_and_validate()
