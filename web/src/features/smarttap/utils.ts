import type { DataFramePayload, JsonRecord, VisualizationResponse } from "./types";

const hiddenSpecKeys = new Set([
  "notes",
  "confirmed_fields",
  "confirmation_status",
  "openet_geo",
  "openet_id",
  "huc8_code",
  "secondary_variables",
  "chart_package",
  "source_datasets",
  "display_location",
]);

export function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ");
  }
  return String(value);
}

export function displaySpec(spec: JsonRecord | null): [string, unknown][] {
  if (!spec) {
    return [];
  }
  return Object.entries(spec).filter((entry) => {
    const [key, value] = entry;
    if (hiddenSpecKeys.has(key)) {
      return false;
    }
    if (value === null || value === "" || value === undefined) {
      return false;
    }
    if (Array.isArray(value) && value.length === 0) {
      return false;
    }
    if (typeof value === "object" && !Array.isArray(value) && Object.keys(value as JsonRecord).length === 0) {
      return false;
    }
    return true;
  });
}

export function resultSnapshot(summary: JsonRecord): [string, unknown][] {
  const orderedKeys = [
    "location",
    "variable_labels",
    "date_range",
    "row_count",
    "total_fields",
    "total_crops",
    "groups",
    "group_count",
  ];
  return orderedKeys
    .map((key) => [key, summary[key]] as [string, unknown])
    .filter(([, value]) => value !== null && value !== undefined && value !== "");
}

export function resolvedRequestItems(spec: JsonRecord | null): [string, unknown][] {
  const display = Object.fromEntries(displaySpec(spec));
  const orderedKeys = [
    "task",
    "dataset",
    "location",
    "location_type",
    "variables",
    "crop_filter",
    "start_date",
    "end_date",
    "year",
    "interval",
    "aggregation",
    "compare_by",
    "split_by",
    "group_by",
    "station_id",
    "chart_type",
    "evidence_pattern",
  ];
  return orderedKeys
    .map((key) => [key, display[key]] as [string, unknown])
    .filter(([, value]) => value !== null && value !== undefined && value !== "");
}

export function assistantMessageForResult(query: string, result: VisualizationResponse): string {
  if (result.success && result.spec?.task) {
    return `Generated a \`${String(result.spec.task)}\` result for: ${query}`;
  }
  if (result.needs_confirmation) {
    return result.confirmation_prompt ?? "Confirmation required.";
  }
  if (result.needs_clarification) {
    return result.clarification_prompt ?? "Clarification required.";
  }
  return `Error: ${result.error ?? "Unknown error."}`;
}

export function nextStatus(result: VisualizationResponse) {
  if (result.success) {
    return "success" as const;
  }
  if (result.needs_confirmation) {
    return "confirmation" as const;
  }
  if (result.needs_clarification) {
    return "clarification" as const;
  }
  return "error" as const;
}

function escapeCsv(value: unknown): string {
  const stringValue = value == null ? "" : String(value);
  if (/[",\n]/.test(stringValue)) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }
  return stringValue;
}

export function dataframeToCsv(frame: DataFramePayload | null): string {
  if (!frame) {
    return "";
  }
  const header = frame.columns.map(escapeCsv).join(",");
  const rows = frame.records.map((record) =>
    frame.columns.map((column) => escapeCsv(record[column])).join(","),
  );
  return [header, ...rows].join("\n");
}

export function downloadTextFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
