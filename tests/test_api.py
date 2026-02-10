import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

YOUR_API_KEY = os.getenv("OPENET_API_KEY")

# set your API key before making the request
header = {"Authorization": YOUR_API_KEY}

# endpoint arguments
args = {

  #last month (using 2024 data)
  "date_range": [
    "2024-10-01",
    "2024-10-31"
  ],
  "interval": "monthly",  # change to "monthly" for aggregated data
  
  #wilamette valley
  "geometry": [
    -123.0232,
    44.5646
  ],
  "model": "Ensemble",
  "variable": "ET",
  "reference_et": "gridMET",
  "units": "mm",
  "file_format": "JSON"
}

# query the api 
resp = requests.post(
    headers=header,
    json=args,
    url="https://openet-api.org/raster/timeseries/point"
)

print(resp.json())