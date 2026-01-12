import pandas as pd
import requests
import io
import time

#CRVO = Corvallis (OSU), HERO = Hermiston (Eastern Oregon)
STATIONS = {
    "crvo": "Corvallis",
    "hero": "Hermiston"
}

#param list
# mx=MaxTemp, mn=MinTemp, pc=Precip, sr=Solar, ws=Wind
PARAMS = "mx,mn,pc,sr,ws"
YEAR = "2024"

def fetch_station_data(station_id):
    url = "https://www.usbr.gov/pn-bin/daily.pl"
    params = {
        'list': f"{station_id} mx, {station_id} mn, {station_id} pc, {station_id} sr, {station_id} ws",
        'start': f"{YEAR}-01-01",
        'end': f"{YEAR}-12-31",
        'format': 'csv'
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

    print(f"Fetching 2024 data for {STATIONS[station_id]} ({station_id})...")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=40)
        response.raise_for_status()
        
        if "DateTime" not in response.text:
            print(f"Error for {station_id}: Server returned invalid format.")
            return None

        df = pd.read_csv(io.StringIO(response.text))
        
        #strip station prefix (crvo_mx -> mx)
        df.columns = [col.replace(f'{station_id}_', '').strip() for col in df.columns]
        
        #rename
        mapping = {
            'DateTime': 'date',
            'mx': 'max_temp_f',
            'mn': 'min_temp_f',
            'pc': 'cum_precip_in',
            'sr': 'solar_langley',
            'ws': 'wind_speed_mph'
        }
        df.rename(columns=mapping, inplace=True)

        #calculate daily rainfall from cumulative rainfall
        df['daily_precip_in'] = df['cum_precip_in'].diff()
        #handle the reset (if diff is negative, use the raw value)
        df.loc[df['daily_precip_in'] < 0, 'daily_precip_in'] = df['cum_precip_in']
        df['daily_precip_in'] = df['daily_precip_in'].fillna(0).round(2)
        
        #fill missing solar/wind with 0 rather than NaN for the LLM
        df = df.fillna(0)

        return df

    except Exception as e:
        print(f"Connection failed for {station_id}: {e}")
        return None

def main():
    saved_files = []
    
    for sid in STATIONS.keys():
        data = fetch_station_data(sid)
        if data is not None:
            data['location'] = STATIONS[sid] #tag the data
            
            #save to separate file for each location
            location_name = STATIONS[sid].lower().replace(' ', '_')
            output_file = f"{location_name}_weather_2024.csv"
            data.to_csv(output_file, index=False)
            saved_files.append(output_file)
            
            print(f"Saved {STATIONS[sid]} data to {output_file}")
            print(f"   → {len(data)} records")
            
            time.sleep(3)
            
    if saved_files:
        print(f"\nCreated {len(saved_files)} separate files:")
        for file in saved_files:
            print(f"   📄 {file}")
    else:
        print("No data was collected.")

if __name__ == "__main__":
    main()