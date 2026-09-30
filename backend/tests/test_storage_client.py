import pytest
from unittest.mock import patch, MagicMock
from app.services.storage_client import StorageClient, StorageUploadError
import os

@pytest.fixture
def temp_file(tmp_path):
    file_path = tmp_path / "test_video.mp4"
    file_path.write_text("dummy content")
    return str(file_path)

@patch("app.services.storage_client.settings")
def test_fallback_local_url(mock_settings, temp_file):
    # No S3 bucket configured, empty base_url returns relative path
    mock_settings.s3_bucket_name = None
    mock_settings.base_url = ""
    
    client = StorageClient()
    assert not client.is_configured()
    
    url = client.upload_video("job1", temp_file)
    assert url == "/assets/test_video.mp4"

@patch("app.services.storage_client.settings")
def test_fallback_with_base_url(mock_settings, temp_file):
    mock_settings.s3_bucket_name = None
    mock_settings.base_url = "http://localhost:8000"
    
    client = StorageClient()
    url = client.upload_video("job1", temp_file)
    assert url == "http://localhost:8000/assets/test_video.mp4"

@patch("app.services.storage_client.settings")
@patch("app.services.storage_client.boto3.client")
def test_upload_to_s3_success(mock_boto_client, mock_settings, temp_file):
    mock_settings.s3_bucket_name = "test-bucket"
    mock_settings.aws_region = "us-west-2"
    mock_settings.s3_endpoint_url = None
    mock_settings.aws_access_key_id = "test_id"
    mock_settings.aws_secret_access_key = "test_key"
    
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    
    client = StorageClient()
    assert client.is_configured()
    
    url = client.upload_video("job1", temp_file)
    
    mock_s3.upload_file.assert_called_once_with(
        temp_file, "test-bucket", "test_video.mp4", ExtraArgs={'ContentType': 'video/mp4'}
    )
    assert url == "https://test-bucket.s3.us-west-2.amazonaws.com/test_video.mp4"

@patch("app.services.storage_client.settings")
@patch("app.services.storage_client.boto3.client")
def test_upload_custom_endpoint(mock_boto_client, mock_settings, temp_file):
    mock_settings.s3_bucket_name = "test-bucket"
    mock_settings.s3_endpoint_url = "https://custom.endpoint"
    mock_settings.aws_region = "us-east-1"
    
    mock_s3 = MagicMock()
    mock_boto_client.return_value = mock_s3
    
    client = StorageClient()
    
    url = client.upload_video("job1", temp_file)
    assert url == "https://custom.endpoint/test-bucket/test_video.mp4"

@patch("app.services.storage_client.settings")
@patch("app.services.storage_client.boto3.client")
def test_upload_failure(mock_boto_client, mock_settings, temp_file):
    mock_settings.s3_bucket_name = "test-bucket"
    mock_settings.s3_endpoint_url = None
    
    mock_s3 = MagicMock()
    from botocore.exceptions import ClientError
    mock_s3.upload_file.side_effect = ClientError({"Error": {"Code": "500", "Message": "Error"}}, "upload_file")
    mock_boto_client.return_value = mock_s3
    
    client = StorageClient()
    
    with pytest.raises(StorageUploadError):
        client.upload_video("job1", temp_file)
