import ollama
import json
from datetime import date
from .config import get_model_name

def get_task_specification(user_query):

    today = date.today().strftime("%Y-%m-%d")

    system_prompt = f"""You are a JSON converter for weather data queries. Today: {today}

STEP 1: Identify the variable
- If query mentions "ET", "evapotranspiration" → Variable is ETa
- If query mentions "precip", "rain", "rainfall" → Variable is PC  
- If query mentions "temp", "temperature" (no max/min specified) → Variable is OBM
- If query mentions "max temp", "high temp" → Variable is MX
- If query mentions "min temp", "low temp" → Variable is MN

STEP 2: Choose dataset based on variable
- If variable is ETa → dataset = "openet"
- Otherwise → dataset = "agrimet"

STEP 3: Extract location (default: corvallis)
Valid: corvallis, pendleton, hood river, klamath falls, ontario

STEP 4: Extract dates
Parse start_date and end_date from query. If just year given, use Jan 1 to Dec 31.
If "last year", use {int(today.split('-')[0])-1}.

STEP 5: Build JSON
If dataset is "agrimet":
{{"task": "visualize_timeseries", "dataset": "agrimet", "location": "<location>", "variables": ["<VAR>"], "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "interval": "daily", "chart_type": "line"}}

If dataset is "openet" AND location is "klamath falls":
{{"task": "visualize_timeseries", "dataset": "openet", "openet_geo": "huc8", "huc8_code": "18010204", "variables": ["ETa"], "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "interval": "monthly", "chart_type": "line"}}

Output ONLY valid JSON. No explanations."""

    # Get configured model (defaults to gemma2:2b)
    model_name = get_model_name()
    
    #using json format to force structured output
    response = ollama.chat(
        model=model_name, 
        format='json',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_query},
        ]
    )
    
    raw_content = response.message.content
    
    try:
        parsed = json.loads(raw_content)
        return parsed
    except json.JSONDecodeError as e:
        return {"error": "JSON Parsing Error", "details": str(e), "raw": raw_content}
    except Exception as e:
        return {"error": "Unexpected Error", "details": str(e), "raw": raw_content}


if __name__ == "__main__":
    #test queries
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