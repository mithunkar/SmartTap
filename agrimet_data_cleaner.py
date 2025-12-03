import pandas as pd
from datetime import datetime

DATA_FILE = "data/12012024-12012025.txt"

def load_agrimet_data(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    data_start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "BEGIN DATA":
            data_start_idx = i
            break
    
    if data_start_idx is None:
        raise ValueError("Couldn't find 'BEGIN DATA' marker in file")
    
    header_line = lines[data_start_idx + 1]
    
    #parse column names
    columns = ['DATE', 'TIME']
    parts = header_line.split(',')
    for part in parts[1:]:
        param = part.strip().split()[-1]
        if param:
            columns.append(param)
    
    #extract data lines
    data_lines = []
    for line in lines[data_start_idx + 2:]:
        if line.strip() == "END DATA":
            break
        if line.strip():
            data_lines.append(line)
    
    data = []
    for line in data_lines:
        parts = line.split(',')
        datetime_part = parts[0].strip()
        date_time = datetime_part.split()
        
        row = {
            'DATE': date_time[0],
            'TIME': date_time[1]
        }
        
        for i, value in enumerate(parts[1:], start=2):
            if i < len(columns):
                cleaned_value = value.strip()
                try:
                    row[columns[i]] = float(cleaned_value) if cleaned_value else None
                except ValueError:
                    row[columns[i]] = cleaned_value if cleaned_value else None
        
        data.append(row)
    
    df = pd.DataFrame(data)
    df['DATETIME'] = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
    df = df.drop(['DATE', 'TIME'], axis=1)
    
    cols = ['DATETIME'] + [col for col in df.columns if col != 'DATETIME']
    df = df[cols]
    df = df.set_index('DATETIME')
    
    return df


def get_data_summary(df):
    print(f"Data Range: {df.index.min()} to {df.index.max()}")
    print(f"Total Records: {len(df)}")
    print(f"\nColumns: {', '.join(df.columns)}")
    print(f"\nData Info:")
    print(df.info())
    print(f"\nStatistical Summary:")
    print(df.describe())


def get_column_data(df, column_name, start_date=None, end_date=None):
    data = df[column_name]
    
    if start_date:
        data = data[data.index >= start_date]
    if end_date:
        data = data[data.index <= end_date]
    
    return data


if __name__ == "__main__":
    print("Loading AgriMet data...")
    df = load_agrimet_data(DATA_FILE)
    
    print("\n" + "="*60)
    print("DATA LOADED SUCCESSFULLY")
    print("="*60)
    
    get_data_summary(df)
    
    print("\n" + "="*60)
    print("SAMPLE DATA (First 10 rows)")
    print("="*60)
    print(df.head(10))
    
    print("\n" + "="*60)
    print("SAMPLE DATA (Last 10 rows)")
    print("="*60)
    print(df.tail(10))
    
    print("\n" + "="*60)
    print("TEMPERATURE (OBM) DATA - First 10 values")
    print("="*60)
    temp_data = get_column_data(df, 'OBM')
    print(temp_data.head(10))
