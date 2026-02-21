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
YEARS = range(2015, 2026)  # 2015 through 2025

def fetch_station_data(station_id, year):
    url = "https://www.usbr.gov/pn-bin/daily.pl"
    params = {
        'list': f"{station_id} mx, {station_id} mn, {station_id} pc, {station_id} sr, {station_id} ws",
        'start': f"{year}-01-01",
        'end': f"{year}-12-31",
        'format': 'csv'
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

    print(f"Fetching {year} data for {STATIONS[station_id]} ({station_id})...")
    
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
        
        #fill missing solar/wind with 0 rather than NaN
        df = df.fillna(0)

        return df

    except Exception as e:
        print(f"Connection failed for {station_id}: {e}")
        return None

def main():
    import os
    
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    saved_files = []
    failed_fetches = []
    
    total_fetches = len(STATIONS) * len(YEARS)
    current = 0
    
    print(f"\n{'='*70}")
    print(f"Fetching data for {len(STATIONS)} stations across {len(YEARS)} years ({total_fetches} total fetches)")
    print(f"{'='*70}\n")
    
    for year in YEARS:
        print(f"\n--- Year {year} ---")
        for sid in STATIONS.keys():
            current += 1
            print(f"[{current}/{total_fetches}] ", end="")
            
            data = fetch_station_data(sid, year)
            if data is not None:
                data['location'] = STATIONS[sid]
                
                #quality checks
                precip_days = (data['daily_precip_in'] > 0).sum()
                solar_days = (data['solar_langley'] > 0).sum()
                temp_range = data['max_temp_f'].max() - data['min_temp_f'].min()
                
                #check if data valid
                if temp_range < 10:  #sus (low temperature range)
                    print(f"Warning: {STATIONS[sid]} {year} has suspicious temperature data (range: {temp_range:.1f}°F)")
                    failed_fetches.append(f"{STATIONS[sid]} {year}")
                    time.sleep(2)
                    continue
                
                #check for data coverage
                expected_days = 366 if year % 4 == 0 else 365
                if len(data) < expected_days * 0.9:  #less than 90% coverage
                    print(f"Warning: {STATIONS[sid]} {year} has incomplete data ({len(data)}/{expected_days} days)")
                    failed_fetches.append(f"{STATIONS[sid]} {year}")
                    time.sleep(2)
                    continue
                
                #save to data folder with year in filename
                location_name = STATIONS[sid].lower().replace(' ', '_')
                output_file = os.path.join(data_dir, f"{location_name}_weather_{year}.csv")
                data.to_csv(output_file, index=False)
                saved_files.append(output_file)
                
                print(f"Saved to {output_file}")
                print(f"   → {len(data)} records, {precip_days} rainy days, {solar_days} days w/ solar data")
            else:
                failed_fetches.append(f"{STATIONS[sid]} {year}")
            
            time.sleep(2)  #be nice to the server
    
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    if saved_files:
        print(f"Successfully saved {len(saved_files)}/{total_fetches} files to {data_dir}/")
        
        #group by location for summary
        by_location = {}
        for file in saved_files:
            location = file.split('/')[-1].split('_weather_')[0].replace('_', ' ').title()
            by_location[location] = by_location.get(location, 0) + 1
        
        print(f"\nFiles by location:")
        for location, count in sorted(by_location.items()):
            print(f"   {location}: {count} years")
    
    if failed_fetches:
        print(f"\nFailed or skipped: {len(failed_fetches)} fetches")
        if len(failed_fetches) <= 10:
            for fail in failed_fetches:
                print(f"   - {fail}")
        else:
            print(f"   (Too many to list individually)")
    
    if not saved_files:
        print("No valid data was collected.")
    
    if not saved_files:
        print("No valid data was collected.")

if __name__ == "__main__":
    main()