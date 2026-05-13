export type JsonRecord = Record<string, unknown>;

export type MetricOption = {
  code: string;
  label: string;
};

export type HealthResponse = {
  status: "ok";
  app: string;
  metric_options: MetricOption[];
};

export type DataFramePayload = {
  columns: string[];
  records: JsonRecord[];
};

export type ChartSeries = {
  key: string;
  label: string;
  color: string | null;
};

export type ChartModel = {
  kind: "line" | "bar" | "pie" | "donut";
  title: string;
  rows: JsonRecord[];
  x_key: string;
  x_label?: string | null;
  y_label?: string | null;
  series: ChartSeries[];
  stacked?: boolean;
  horizontal?: boolean;
  value_format?: string | null;
  legend_title?: string | null;
};

export type SecondaryViewPayload = {
  caption: string;
  chart_image_url: string | null;
  chart_model: ChartModel | null;
  vega_spec: JsonRecord | null;
  data_preview: DataFramePayload | null;
  files: Record<string, string>;
};

export type VisualizationResponse = {
  success: boolean;
  needs_clarification: boolean;
  needs_confirmation: boolean;
  error: string | null;
  spec: JsonRecord | null;
  summary: JsonRecord;
  explanation: string;
  data_preview: DataFramePayload | null;
  data: DataFramePayload | null;
  chart_image_url: string | null;
  chart_model: ChartModel | null;
  vega_spec: JsonRecord | null;
  secondary_views: SecondaryViewPayload[];
  files: Record<string, string>;
  validation_report: JsonRecord | null;
  clarification_prompt: string | null;
  confirmation_prompt: string | null;
  clarification_fields: string[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type UiStatus = "idle" | "loading" | "clarification" | "confirmation" | "success" | "error";
