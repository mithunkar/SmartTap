import ollama
import json
from datetime import date

def get_task_specification(user_query):

    today = date.today().strftime("%Y-%m-%d")

    system_prompt = f"""
    You are the Smart-TAP Query Parser. Convert user questions into JSON.
    Today's Date: {today}

    STRICT MAPPING RULES:
    1. Locations: ONLY use 'corvallis' or 'madras'. If the user doesn't specify one, default to 'corvallis'.
    2. Datasets: 
    - Use 'openet' if the user asks for 'evapotranspiration' or 'ET'.
    - Use 'agrimet' for everything else.
    3. Variables: 
    - OBM (Air Temp), PC (Precipitation), TU (Humidity), ET (Evapotranspiration).
    - If a requested variable is NOT in this list, set "task": "error".
    4. Chart Type: ONLY 'line' or 'bar'. If the user asks for anything else (like pie), use 'line'.

    JSON FORMAT:
    {{
    "task": "visualize_timeseries" | "error",
    "dataset": "agrimet" | "openet",
    "location": "corvallis" | "madras",
    "variables": ["CODE1", "CODE2"],
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "interval": "hourly" | "daily" | "monthly" | "auto",
    "chart_type": "line" | "bar",
    "error_message": string (only if task is error)
    }}
    """

    #using json format to force structured output
    response = ollama.chat(
        model='gemma3', 
        format='json',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_query},
        ]
    )
    
    raw_content = response['message']['content']
    
    try:
        return json.loads(raw_content)
    except Exception as e:
        return {"error": "Parsing Error", "details": str(e), "raw": raw_content}


queries = ["Show me a pie chart of the rain in Portland and Madras.",
           "Show me the temperature in Corvallis from Jan 1 to Jan 5 2024.",
           "Can I see a rainfall chart for Madras for the month of July 2024?",
           "Compare the air temp and humidity in Corvallis for the last two weeks of 2024.",
           "I want to see rain, temperature, and evapotranspiration for Corvallis last summer.",
           "Show me the weather for yesterday.",
           "What was the temperature trend over the last 7 days?",
           "Show me Corvallis data for the current month so far.",
           "How much rain did we get in Madras in 2024?",
           "Show me the temp spikes from this morning.",
           "Show me the soil health in Portland.",
           "Show me the wind speed.",
           "Make a pie chart of the rain."]

for query in queries:
    print(f"User Query: {query}")
    print(json.dumps(get_task_specification(query), indent=2))