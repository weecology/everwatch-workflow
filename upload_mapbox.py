import os
import requests
import boto3
from botocore.exceptions import NoCredentialsError
import sys
import tomli


class MapboxUploader:

    def __init__(self, access_token, username):
        self.access_token = access_token
        self.username = username
        self.base_url = f"https://api.mapbox.com/uploads/v1/{self.username}"

    def request_s3_credentials(self):
        credentials_url = f"{self.base_url}/credentials?access_token={self.access_token}"
        response = requests.post(credentials_url)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to retrieve S3 credentials. Status code: {response.status_code}")

    def upload_to_s3(self, file_path, s3_credentials):
        s3_client = boto3.client(
            's3',
            aws_access_key_id=s3_credentials['accessKeyId'],
            aws_secret_access_key=s3_credentials['secretAccessKey'],
            aws_session_token=s3_credentials['sessionToken'],
            region_name='us-east-1'  # Use the appropriate AWS region
        )
        try:
            s3_client.upload_file(file_path, s3_credentials['bucket'], s3_credentials['key'])
        except NoCredentialsError:
            print("Credentials not available.")
            raise

    def create_upload(self, s3_credentials, tileset_id):
        upload_url = f"{self.base_url}?access_token={self.access_token}"
        headers = {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}
        data = {"url": s3_credentials['url'], "tileset": f"{self.username}.{tileset_id}"}
        response = requests.post(upload_url, json=data, headers=headers)
        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"Failed to create upload. Status code: {response.status_code}")

    def retrieve_upload_status(self, upload_id):
        status_url = f"{self.base_url}/{upload_id}?access_token={self.access_token}"
        response = requests.get(status_url)
        if response.status_code in {200, 201}:
            return response.json()
        else:
            raise Exception(f"Failed to retrieve upload status. Status code: {response.status_code}")


def get_credentials():
    """Get credentials from mapbox.ini"""
    with open("/blue/ewhite/everglades/mapbox.ini", "rb") as f:
        toml_dict = tomli.load(f)
        access_token = toml_dict['mapbox']['access-token']
    return access_token


if __name__ == "__main__":
    file_path = sys.argv[1]
    access_token = get_credentials()
    username = 'bweinstein'
    uploader = MapboxUploader(access_token, username)
    # Step 1: Request S3 credentials
    s3_credentials = uploader.request_s3_credentials()

    # Step 2: Upload to Mapbox's S3 staging bucket
    uploader.upload_to_s3(file_path, s3_credentials)
    filename_without_extension = os.path.splitext(os.path.basename(file_path))[0]
    tileset_id = filename_without_extension

    # Step 3: Create an upload to matbox
    upload_data = uploader.create_upload(s3_credentials, tileset_id)
    upload_id = upload_data['id']
    upload_status = uploader.retrieve_upload_status(upload_id)
    print(f"Upload status: {upload_status}")
