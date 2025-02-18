from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    custom_resources as cr,
)
import aws_cdk.aws_scheduler_alpha as scheduler
import aws_cdk.aws_scheduler_targets_alpha as targets
from constructs import Construct
from config import Config


class SecureApiWithCloudfrontStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Load config
        config = Config()

        custom_header_key = "token-from-cloudfront"

        # Import ssm parameter
        secure_parameter = ssm.StringParameter.from_secure_string_parameter_attributes(
            self,
            "SecureParameter",
            parameter_name=config.ssm_secure_parameter_name,
        )

        # API proxy lambda function
        backend_function = _lambda.Function(
            self,
            "BackendFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("src/backend_function"),
            timeout=Duration.seconds(2),
        )

        # Custom authorizer lambda function
        custom_authorizer = _lambda.Function(
            self,
            "BackendLambdaFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("src/custom_authorizer"),
            timeout=Duration.seconds(2),
            environment={
                "SSM_PARAMETER_NAME": secure_parameter.parameter_name,
                "CUSTOM_HEADER_KEY": custom_header_key,
            },
        )

        custom_authorizer.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[secure_parameter.parameter_arn],
            )
        )

        # API endpoint
        rest_api = apigateway.RestApi(
            self,
            "MyRestApi",
            rest_api_name="MyRestApi",
            description="My Rest Api",
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
            ),
        )

        apigw_lambda_execution_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            description="Role for Lambda execution.",
            inline_policies={
                "LambdaExecutionPermissions": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[backend_function.function_arn],
                        ),
                    ]
                ),
            },
        )

        # Create Lambda Authorizer
        authorizer = apigateway.RequestAuthorizer(
            self,
            "LambdaHeaderAuthorizer",
            handler=custom_authorizer,
            identity_sources=[apigateway.IdentitySource.header(custom_header_key)],
            results_cache_ttl=Duration.seconds(30),
        )

        # add method to /hello api
        rest_api.root.add_resource("hello").add_method(
            "GET",
            apigateway.LambdaIntegration(
                backend_function,
                proxy=True,
                credentials_role=apigw_lambda_execution_role,
            ),
            method_responses=[apigateway.MethodResponse(status_code="200")],
            authorization_type=apigateway.AuthorizationType.CUSTOM,
            authorizer=authorizer,
        )

        # Create a cloudfront distribution to host the frontend
        cloudfront_distribution = cloudfront.Distribution(
            self,
            "MyCloudfrontDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.RestApiOrigin(
                    rest_api,
                    origin_path="/prod",
                    custom_headers={custom_header_key: "test"},
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_200,
        )

        # Update cloudfront distribution with the secure header
        update_secure_header = _lambda.Function(
            self,
            "UpdateSecureHeaderFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.lambda_handler",
            code=_lambda.Code.from_asset("src/update_secure_header"),
            timeout=Duration.seconds(5),
            environment={
                "SSM_PARAMETER_NAME": secure_parameter.parameter_name,
                "CLOUDFRONT_DISTRIBUTION_ID": cloudfront_distribution.distribution_id,
                "APIGATEWAY_URL": rest_api.url,
                "CUSTOM_HEADER_KEY": custom_header_key,
            },
        )

        update_secure_header.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:PutParameter"],
                resources=[secure_parameter.parameter_arn],
            )
        )

        update_secure_header.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudfront:GetDistributionConfig",
                    "cloudfront:UpdateDistribution",
                ],
                resources=[cloudfront_distribution.distribution_arn],
            )
        )

        # IAM Role for the S3 deployment
        custom_resource_role = iam.Role(
            scope=self,
            id="CustomResourceRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        custom_resource_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[update_secure_header.function_arn],
            )
        )

        # Custom resource to update the secure header on stack create
        cr.AwsCustomResource(
            self,
            "UpdateSecureHeaderOnCreateCustomResource",
            on_update=cr.AwsSdkCall(
                service="lambda",
                action="Invoke",
                physical_resource_id=cr.PhysicalResourceId.of(
                    "UpdateSecureHeaderOnCreateCustomResource"
                ),
                parameters={
                    "FunctionName": update_secure_header.function_name,
                    "InvocationType": "Event",
                    "Payload": '{"RequestType": "Create"}',
                },
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
            role=custom_resource_role,
        )

        # AWS EventBridge scheduler to update the secure header every 24 hours
        scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
        )

        scheduler_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[update_secure_header.function_arn],
            )
        )

        scheduler.Schedule(
            self,
            "Schedule",
            schedule=scheduler.ScheduleExpression.rate(Duration.hours(6)),
            target=targets.LambdaInvoke(update_secure_header, role=scheduler_role),
            description="Schedule to trigger update header lambda function every hour.",
        )
        # Output
        CfnOutput(self, "CloudfrontUrl", value=cloudfront_distribution.domain_name)
