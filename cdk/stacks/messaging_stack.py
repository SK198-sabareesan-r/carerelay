"""Messaging layer: the SNS topic AWS End User Messaging publishes to.

The WhatsApp Business Account (WABA) event destination is pointed at this
topic. All inbound patient messages (card photo, voice note, text, button
taps) land here and fan out to the webhook_receiver Lambda.
"""
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_sns as sns,
)
from constructs import Construct


class MessagingStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.inbound_topic = sns.Topic(
            self,
            "InboundTopic",
            display_name="CareRelay inbound patient intake events",
        )

        CfnOutput(
            self,
            "InboundTopicArn",
            value=self.inbound_topic.topic_arn,
            description="Set this as the WABA event destination SNS topic.",
        )
