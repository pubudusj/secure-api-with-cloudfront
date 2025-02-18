import os
import boto3

ssm = boto3.client("ssm")
SSM_PARAMETER_NAME = os.environ["SSM_PARAMETER_NAME"]
CUSTOM_HEADER_KEY = os.environ["CUSTOM_HEADER_KEY"]

def fetch_header_value():
    response = ssm.get_parameter(Name=SSM_PARAMETER_NAME, WithDecryption=True)
    return response["Parameter"]["Value"]


def lambda_handler(event, context):
    headers = event.get("headers", {})
    api_key = headers.get(CUSTOM_HEADER_KEY, None)
    expected_key = fetch_header_value()

    effect = "Deny"
    if api_key == expected_key:
        effect = "Allow"

    return {
        "principalId": "custom_authorizer",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": event["methodArn"],
                }
            ],
        },
    }
