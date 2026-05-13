import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "../../app-shell/App";

function createResponse(payload: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("SmartTapWorkspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("renders a successful query with chart, explanation, and data preview", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/health") {
        return createResponse({
          status: "ok",
          app: "smarttap-api",
          metric_options: [{ code: "OBM", label: "Average Temperature (deg F)" }],
        });
      }
      if (url === "/api/query" && init?.method === "POST") {
        return createResponse({
          success: true,
          needs_clarification: false,
          needs_confirmation: false,
          error: null,
          spec: { task: "visualize_timeseries", location: "Corvallis", variables: ["OBM"] },
          summary: { location: "Corvallis", variable_labels: ["Average Temperature (deg F)"], row_count: 2 },
          explanation: "Temperatures increased slightly during July.",
          data_preview: {
            columns: ["datetime", "OBM"],
            records: [
              { datetime: "2024-07-01", OBM: 72 },
              { datetime: "2024-07-02", OBM: 74 },
            ],
          },
          data: {
            columns: ["datetime", "OBM"],
            records: [
              { datetime: "2024-07-01", OBM: 72 },
              { datetime: "2024-07-02", OBM: 74 },
            ],
          },
          chart_model: {
            kind: "line",
            title: "Temperature trend",
            rows: [
              { datetime: "2024-07-01", "Average Temperature (deg F)": 72 },
              { datetime: "2024-07-02", "Average Temperature (deg F)": 74 },
            ],
            x_key: "datetime",
            series: [{ key: "Average Temperature (deg F)", label: "Average Temperature (deg F)", color: "#4c78a8" }],
          },
          chart_image_url: "data:image/png;base64,ZmFrZQ==",
          vega_spec: { mark: "line" },
          secondary_views: [],
          files: { png: "outputs/chart.png" },
          validation_report: { status: "ok" },
          clarification_prompt: null,
          confirmation_prompt: null,
          clarification_fields: [],
        });
      }
      return Promise.reject(new Error(`Unhandled fetch for ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.type(
      screen.getByPlaceholderText("Ask about Oregon weather, water, or crop patterns..."),
      "Show temperature in Corvallis for July 2024",
    );
    await userEvent.click(screen.getByRole("button", { name: "Run Query" }));

    expect(await screen.findByTestId("smarttap-chart")).toBeInTheDocument();
    expect(await screen.findByText("Temperatures increased slightly during July.")).toBeInTheDocument();
    expect(screen.getAllByText("Data Preview").length).toBeGreaterThan(0);
    expect(screen.getByText("2024-07-01")).toBeInTheDocument();
    expect(screen.getByText("What SmartTap Does")).toBeInTheDocument();
    expect(screen.getByText("Result Details")).toBeInTheDocument();
  });

  test("supports confirmation and deterministic edit flow", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/health") {
        return createResponse({
          status: "ok",
          app: "smarttap-api",
          metric_options: [
            { code: "OBM", label: "Average Temperature (deg F)" },
            { code: "ETa", label: "ETa" },
          ],
        });
      }
      if (url === "/api/query") {
        return createResponse({
          success: false,
          needs_clarification: false,
          needs_confirmation: true,
          error: null,
          spec: {
            task: "visualize_timeseries",
            location: "Corvallis",
            display_location: "Corvallis",
            variables: ["OBM"],
            start_date: "2024-01-01",
            end_date: "2024-12-31",
          },
          summary: { status: "confirmation_needed" },
          explanation: "",
          data_preview: null,
          data: null,
          chart_model: null,
          chart_image_url: null,
          vega_spec: null,
          secondary_views: [],
          files: {},
          validation_report: null,
          clarification_prompt: null,
          confirmation_prompt: "Please confirm the request.",
          clarification_fields: [],
        });
      }
      if (url === "/api/confirmation/edit") {
        return createResponse({
          success: false,
          needs_clarification: false,
          needs_confirmation: true,
          error: null,
          spec: {
            task: "visualize_timeseries",
            location: "Salem",
            display_location: "Salem",
            variables: ["OBM"],
            start_date: "2024-01-01",
            end_date: "2024-12-31",
          },
          summary: { status: "confirmation_needed" },
          explanation: "",
          data_preview: null,
          data: null,
          chart_model: null,
          chart_image_url: null,
          vega_spec: null,
          secondary_views: [],
          files: {},
          validation_report: null,
          clarification_prompt: null,
          confirmation_prompt: "Please confirm the updated request.",
          clarification_fields: [],
        });
      }
      return Promise.reject(new Error(`Unhandled fetch for ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.type(
      screen.getByPlaceholderText("Ask about Oregon weather, water, or crop patterns..."),
      "Show temperature in Corvallis for 2024",
    );
    await userEvent.click(screen.getByRole("button", { name: "Run Query" }));

    expect(await screen.findByText("Confirmation required before SmartTap runs this request.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Edit Request" }));
    await userEvent.selectOptions(screen.getByLabelText("Field"), "location");
    const locationInput = screen.getByLabelText("Location");
    await userEvent.clear(locationInput);
    await userEvent.type(locationInput, "Salem");
    await userEvent.click(screen.getByRole("button", { name: "Apply Change" }));

    expect((await screen.findAllByText("Please confirm the updated request.")).length).toBeGreaterThan(0);
    expect(screen.getByText("Salem")).toBeInTheDocument();
  });

  test("shows loading state and surfaces request errors", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/health") {
        return createResponse({
          status: "ok",
          app: "smarttap-api",
          metric_options: [],
        });
      }
      if (url === "/api/query" && init?.method === "POST") {
        return Promise.reject(new Error("Backend unavailable"));
      }
      return Promise.reject(new Error(`Unhandled fetch for ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.type(
      screen.getByPlaceholderText("Ask about Oregon weather, water, or crop patterns..."),
      "Show ETa in Corvallis",
    );
    await userEvent.click(screen.getByRole("button", { name: "Run Query" }));

    await waitFor(() => {
      expect(screen.getByText("Error: Backend unavailable")).toBeInTheDocument();
    });
  });

  test("falls back to image rendering when chart_model is absent", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/health") {
        return createResponse({
          status: "ok",
          app: "smarttap-api",
          metric_options: [{ code: "OBM", label: "Average Temperature (deg F)" }],
        });
      }
      if (url === "/api/query" && init?.method === "POST") {
        return createResponse({
          success: true,
          needs_clarification: false,
          needs_confirmation: false,
          error: null,
          spec: { task: "visualize_timeseries", location: "Corvallis", variables: ["OBM"] },
          summary: { location: "Corvallis", variable_labels: ["Average Temperature (deg F)"], row_count: 2 },
          explanation: "Temperatures increased slightly during July.",
          data_preview: {
            columns: ["datetime", "OBM"],
            records: [
              { datetime: "2024-07-01", OBM: 72 },
              { datetime: "2024-07-02", OBM: 74 },
            ],
          },
          data: {
            columns: ["datetime", "OBM"],
            records: [
              { datetime: "2024-07-01", OBM: 72 },
              { datetime: "2024-07-02", OBM: 74 },
            ],
          },
          chart_model: null,
          chart_image_url: "data:image/png;base64,ZmFrZQ==",
          vega_spec: { mark: "line" },
          secondary_views: [],
          files: { png: "outputs/chart.png" },
          validation_report: { status: "ok" },
          clarification_prompt: null,
          confirmation_prompt: null,
          clarification_fields: [],
        });
      }
      return Promise.reject(new Error(`Unhandled fetch for ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await userEvent.type(
      screen.getByPlaceholderText("Ask about Oregon weather, water, or crop patterns..."),
      "Show temperature in Corvallis for July 2024",
    );
    await userEvent.click(screen.getByRole("button", { name: "Run Query" }));

    expect(await screen.findByAltText("SmartTap chart")).toBeInTheDocument();
  });
});
