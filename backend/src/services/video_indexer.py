"""" 
Connector between Python and Azure video indexer
"""

import os
import time
import logging
import requests
import yt_dlp

from azure.identity import DefaultAzureCredential

logger=logging.getLogger("video-indexer")


class VideoIndexerService:
    def __init__(self):
        self.account_id = os.getenv("AZURE_VI_ACCOUNT_ID")
        self.location=os.getenv("AZURE_VI_LOCATION")
        self.subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group=os.getenv("AZURE_RESOURCE_GROUP")
        self.vi_name=os.getenv("AZURE_VI_NAME","porject-brand-guardian")
        self.credentials=DefaultAzureCredential()


    def get_access_token(self):
        """
        Generates an ARM Access Token
        """

        try:
            token_object=self.credentials.get_token("https://management.azure.com/.default")
            return token_object.token
        except Exception as e:
            logger.error(f'Failed to generate token: {e}')
            raise

    def get_account_token(self,arm_access_token):
        url=(
        f"https://management.azure.com/subscriptions/{self.subscription_id}"
        f"/resourceGroups/{self.resource_group}"
        f"/providers/Microsoft.VideoIndexer/accounts/{self.vi_name}"
        f"/generateAccessToken?api-version=2024-01-01")

        header={"Authorization": f"Bearer {arm_access_token}"}
        payload = {"permissionType": "Contributor","scope":"Account"}
        response=requests.post(url,headers=header,json=payload)
        if response.status_code !=200:
            raise Exception(f"Failed to get VI account token: {response.text}")
        return response.json().get("accessToken")

    #Function to download youtube video
    def download_youtube_video(self,url,output_path="temp_video.mp4"):

        logger.info(f"Downloading the Youtube video: {url}")

        ydl_opts = {
            "format": 'best',
            "outtmpl": output_path,
            "quiet": True,
            "overwrites": True,
            "no_warnings": False,

            "extractor_args": {"youtube":{"player_client":["android","web"]}},
            "http_headers":{
                "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            },
            "socket_timeout": 15,
        }

        try: 
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Download complete")
            return output_path
        except Exception as e:
            raise Exception(f"Youtube video download failed {e}")

    def upload_video(self,video_path,video_name):
        arm_token =self.get_access_token()
        vi_token=self.get_account_token(arm_token)

        api_url=f"https://api.videoindexer.ai/{self.location}/{self.account_id}/Videos"

        params={
            "accessToken": vi_token,
            "name": video_name,
            "privacy":"Private",
            "indexingPreset":"Default"
        }

        logger.info(f"Uploading file {video_path} to Azure")

        with open(video_path,"rb") as video_file:
            files = {"file":video_file}
            response=requests.post(api_url,params=params,files=files)
        if response.status_code !=200:
            raise Exception(f"Azure upload failed: {response.text}")
        return response.json().get("id")

    def wait_for_processing(self,video_id):
        logger.info(f"Waiting for the video to process {video_id}")
        while True:
            arm_token=self.get_access_token()
            vi_token=self.get_account_token(arm_token)

            url=f"https://api.videoindexer.ai/{self.location}/{self.account_id}/Videos/{video_id}/Index"
            params={"accessToken":vi_token}
            response=requests.get(url,params=params)
            data=response.json()

            state=data.get("state")
            if state=="Processed":
                return data
            elif state=="Failed":
                raise Exception("Video Indexing Failed in Azure")
            elif state=="Quarantined":
                raise Exception("Video Quarantined (Copyright / Content Policy Violation)")
            logger.info(f"Status {state} waiting for 30 seconds ....")
            time.sleep(30)

    def extract_data(self,vi_json):
        '''parses JSON into our state'''
        transcript_lines=[]
        for v in vi_json.get("videos",[]):
            for insight in v.get("insights",{}).get("transcript",[]):
                transcript_lines.append(insight.get("text"))

        ocr_lines=[]
        for v in vi_json.get("videos",[]):
            for insight in v.get("insights",{}).get("ocr",[]):
                ocr_lines.append(insight.get("text"))

        return {
            "transcript": " ".join(transcript_lines),
            "ocr_text": ocr_lines,
            "video_metadata": {
                "duration":vi_json.get("summarizedInsights",{}).get("duration",{}).get("seconds"),
                "platform":"youtube",
            }
        }
