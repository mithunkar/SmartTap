import json
from core.visualizer import png_bytes, vega_spec

PAYLOAD_FILE = "fixtures/test_payload.json"

def main():
    with open(PAYLOAD_FILE, "r") as f:
        payload = json.load(f)

    # 1) save PNG
    img = png_bytes(payload)
    with open("chart.png", "wb") as f:
        f.write(img)
    print("✅ Wrote chart.png")

    # 2) save Vega-Lite spec
    spec = vega_spec(payload)
    with open("chart_vega.json", "w") as f:
        json.dump(spec, f, indent=2)
    print("✅ Wrote chart_vega.json")

    print("\nNext:")
    print("- Open chart.png to view the static plot")
    print("- Paste chart_vega.json into https://vega.github.io/editor/ to view interactive plot")

if __name__ == "__main__":
    main()
