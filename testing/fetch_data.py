import pandas as pd
import requests
import io
import time

# Oregon AgriMet Stations with verified data
# CRVO = Corvallis (Willamette Valley)
# PNGO = Pendleton (Eastern Oregon)
# HRMO = Hood River (Columbia Gorge)
# KFLO = Klamath Falls (Southern Oregon)
# ONTO = Ontario (Eastern Oregon)
STATIONS = {
    "crvo": "Corvallis",
    "pngo": "Pendleton",
    "hrmo": "Hood_River",
    "kflo": "Klamath_Falls",
    "onto": "Ontario"
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
    import os
    
    # Create data directory if it doesn't exist
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    saved_files = []
    failed_stations = []
    
    for sid in STATIONS.keys():
        data = fetch_station_data(sid)
        if data is not None:
            data['location'] = STATIONS[sid]
            
            # Quality checks
            precip_days = (data['daily_precip_in'] > 0).sum()
            solar_days = (data['solar_langley'] > 0).sum()
            temp_range = data['max_temp_f'].max() - data['min_temp_f'].min()
            
            # Check if data is valid
            if temp_range < 10:  # Suspiciously low temperature range
                print(f"⚠️  Warning: {STATIONS[sid]} has suspicious temperature data (range: {temp_range:.1f}°F)")
                failed_stations.append(STATIONS[sid])
                time.sleep(3)
                continue
            
            # Save to data folder
            location_name = STATIONS[sid].lower().replace(' ', '_')
            output_file = os.path.join(data_dir, f"{location_name}_weather_2024.csv")
            data.to_csv(output_file, index=False)
            saved_files.append(output_file)
            
            print(f"✅ Saved {STATIONS[sid]} data to {output_file}")
            print(f"   → {len(data)} records, {precip_days} rainy days, {solar_days} days w/ solar data")
            
            time.sleep(3)
    
    print(f"\n{'='*70}")
    if saved_files:
        print(f"Successfully saved {len(saved_files)} files to {data_dir}/:")
        for file in saved_files:
            print(f"   📄 {file}")
    
    if failed_stations:
        print(f"\n⚠️  Failed or skipped stations: {', '.join(failed_stations)}")
        print("These stations may have incomplete or invalid data.")
    
    if not saved_files:
        print("❌ No valid data was collected.")

if __name__ == "__main__":
    main()