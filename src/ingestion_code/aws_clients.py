import boto3
from config import settings

if settings.LOCAL:
    session = boto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
        region_name=settings.AWS_REGION,
    )
else:
    session = boto3.Session()
s3 = session.client("s3")
textract = session.client("textract")
bedrock = session.client("bedrock-runtime")
