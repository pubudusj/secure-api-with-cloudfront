#!/usr/bin/env python3
import os

import aws_cdk as cdk

from secure_api_with_cloudfront.secure_api_with_cloudfront_stack import (
    SecureApiWithCloudfrontStack,
)


app = cdk.App()
SecureApiWithCloudfrontStack(
    app,
    "SecureApiWithCloudfrontStack",
)

app.synth()
