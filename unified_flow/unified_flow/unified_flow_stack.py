from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_stepfunctions as sfn
)
from constructs import Construct

class UnifiedFlowStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. S3 Bucket for all assets (raw video fragments, visemes, and final mp4s)
        self.assets_bucket = s3.Bucket(
            self, "UnifiedFlowAssetsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],
                    allowed_headers=["*"]
                )
            ]
        )

        # 2. API Gateway to trigger Step Functions
        self.api = apigw.RestApi(
            self, "UnifiedFlowApi",
            rest_api_name="Unified Flow Service API",
            description="API to trigger the Unified Flow concept-to-render pipeline.",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS
            )
        )

        # We will integrate this API Gateway with Step Functions later when the State Machine is built.
        # For now, we create a placeholder resource
        self.generate_resource = self.api.root.add_resource("generate")

        # 3. Lambda Functions
        import aws_cdk.aws_lambda as _lambda
        from aws_cdk import Duration
        
        common_env = {"ASSETS_BUCKET": self.assets_bucket.bucket_name}

        orchestrator_fn = _lambda.Function(self, "OrchestratorLayer",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/orchestrator"),
            timeout=Duration.seconds(60),
            environment={
                **common_env,
                "GUARDRAIL_ID": "unified-flow-guardrail"
            }
        )


        audio_synth_fn = _lambda.Function(self, "AudioSynthLayer",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/audio_synth"),
            timeout=Duration.seconds(60),
            environment=common_env
        )

        visual_gen_fn = _lambda.Function(self, "VisualGenLayer",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/visual_gen"),
            timeout=Duration.seconds(120),
            environment=common_env
        )

        media_composer_fn = _lambda.Function(self, "MediaComposerLayer",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/media_composer"),
            timeout=Duration.seconds(300),
            memory_size=1024,
            environment=common_env
        )

        # Grant S3 Bucket permissions
        self.assets_bucket.grant_read_write(audio_synth_fn)
        self.assets_bucket.grant_read_write(visual_gen_fn)
        self.assets_bucket.grant_read_write(media_composer_fn)

        # Grant Bedrock and Polly permissions (simplified for hackathon)
        bedrock_policy = iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:StartAsyncInvoke"],
            resources=["*"]
        )
        orchestrator_fn.add_to_role_policy(bedrock_policy)
        visual_gen_fn.add_to_role_policy(bedrock_policy)
        
        polly_policy = iam.PolicyStatement(
            actions=["polly:SynthesizeSpeech"],
            resources=["*"]
        )
        audio_synth_fn.add_to_role_policy(polly_policy)

        # 4. Step Functions Definition
        import aws_cdk.aws_stepfunctions_tasks as tasks

        step_orchestrator = tasks.LambdaInvoke(self, "Generate Manifest via Claude",
            lambda_function=orchestrator_fn,
            output_path="$.Payload.body"
        )
        
        step_audio = tasks.LambdaInvoke(self, "Synthesize Audio & Visemes (Polly)",
            lambda_function=audio_synth_fn,
            output_path="$.Payload"
        )
        
        step_visual = tasks.LambdaInvoke(self, "Start Visual Gen Jobs (Titan+Nova)",
            lambda_function=visual_gen_fn,
            output_path="$.Payload"
        )
        
        step_composer = tasks.LambdaInvoke(self, "Compose Final MP4 (FFmpeg)",
            lambda_function=media_composer_fn,
            output_path="$.Payload"
        )
        
        # Parallel State
        parallel_generation = sfn.Parallel(self, "Parallel Asset Generation")
        parallel_generation.branch(step_audio)
        parallel_generation.branch(step_visual)

        # Chain states
        definition = step_orchestrator.next(parallel_generation).next(step_composer)

        self.state_machine = sfn.StateMachine(self, "UnifiedFlowPipeline",
            definition=definition,
            timeout=Duration.minutes(15)
        )

        # 5. API Gateway to Step Functions Integration
        
        # IAM Role for API Gateway to start execution
        api_sfn_role = iam.Role(self, "ApiGatewayStepFunctionsRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com")
        )
        self.state_machine.grant_start_execution(api_sfn_role)
        
        # Add the Step Functions integration
        sfn_arn = self.state_machine.state_machine_arn

        request_template = (
            '{"input": "$util.escapeJavaScript($input.json(\'$\'))",'
            ' "stateMachineArn": "' + sfn_arn + '"}'
        )

        integration_options = apigw.IntegrationOptions(
            credentials_role=api_sfn_role,
            request_templates={
                "application/json": request_template
            },
            integration_responses=[
                apigw.IntegrationResponse(
                    status_code="200",
                    response_templates={
                        "application/json": '{"status": "Pipeline started", "executionArn": "$input.path(\'$.executionArn\')"}'
                    }
                )
            ]
        )


        sfn_integration = apigw.AwsIntegration(
            service="states",
            action="StartExecution",
            integration_http_method="POST",
            options=integration_options
        )

        self.generate_resource.add_method(
            "POST", 
            sfn_integration,
            method_responses=[apigw.MethodResponse(status_code="200")]
        )

        # 6. Status Poller Lambda + /status GET endpoint
        status_poller_fn = _lambda.Function(self, "StatusPollerLayer",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="app.lambda_handler",
            code=_lambda.Code.from_asset("lambda_functions/status_poller"),
            timeout=Duration.seconds(10),
            environment=common_env
        )

        # Grant the poller permission to describe executions
        self.state_machine.grant(status_poller_fn, "states:DescribeExecution")

        status_resource = self.api.root.add_resource("status")
        status_resource.add_method(
            "GET",
            apigw.LambdaIntegration(status_poller_fn),
            method_responses=[apigw.MethodResponse(status_code="200")]
        )

