import boto3
import os
import secrets
from urllib.parse import urlparse

ssm = boto3.client("ssm")
cloudfront = boto3.client("cloudfront")
SSM_PARAMETER_NAME = os.environ["SSM_PARAMETER_NAME"]
CLOUDFRONT_DISTRIBUTION_ID = os.environ["CLOUDFRONT_DISTRIBUTION_ID"]
CUSTOM_HEADER_KEY = os.environ["CUSTOM_HEADER_KEY"]
APIGATEWAY_URL = os.environ["APIGATEWAY_URL"]
parsed_url = urlparse(APIGATEWAY_URL)
APIGATEWAY_DOMAIN = parsed_url.netloc
SECRET_LENGTH = 32


def update_cloudfront_header(secret):
    # Get the current distribution configuration and its ETag
    cloudfront_distribution_config = cloudfront.get_distribution_config(
        Id=CLOUDFRONT_DISTRIBUTION_ID
    )
    distribution_config = cloudfront_distribution_config["DistributionConfig"]
    etag = cloudfront_distribution_config["ETag"]

    # Update the custom headers for the API Gateway origin
    for origin in distribution_config["Origins"]["Items"]:
        if origin["DomainName"] == APIGATEWAY_DOMAIN:
            custom_headers = origin.get("CustomHeaders", {"Quantity": 0, "Items": []})
            for header in custom_headers.get("Items", []):
                if header["HeaderName"].lower() == CUSTOM_HEADER_KEY:
                    header["HeaderValue"] = secret
                    break

            # Update the origin's custom headers field
            origin["CustomHeaders"] = custom_headers
            break

    # Update the distribution with the new configuration
    update_response = cloudfront.update_distribution(
        Id=CLOUDFRONT_DISTRIBUTION_ID,
        DistributionConfig=distribution_config,
        IfMatch=etag,
    )

    print("Update initiated. New ETag:", update_response["ETag"])


def update_parameter(secret):
    ssm.put_parameter(
        Name=SSM_PARAMETER_NAME,
        Value=secret,
        Overwrite=True,
    )


def lambda_handler(event, context):
    # Update the secure header value with random value
    secret = secrets.token_urlsafe(SECRET_LENGTH)
    update_cloudfront_header(secret)
    update_parameter(secret)
