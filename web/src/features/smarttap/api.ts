import { requestJson } from "../../shared/api/http";
import type { HealthResponse, VisualizationResponse } from "./types";

export const smartTapApi = {
  health: () => requestJson<HealthResponse>("/api/health"),
  query: (query: string) =>
    requestJson<VisualizationResponse>("/api/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  followup: (followupQuery: string, pendingSpec: Record<string, unknown>, originalQuery: string) =>
    requestJson<VisualizationResponse>("/api/followup", {
      method: "POST",
      body: JSON.stringify({
        followup_query: followupQuery,
        pending_spec: pendingSpec,
        original_query: originalQuery,
      }),
    }),
  applyConfirmationEdit: (
    pendingSpec: Record<string, unknown>,
    originalQuery: string,
    field: "crop" | "location" | "time_range" | "metric",
    value: unknown,
  ) =>
    requestJson<VisualizationResponse>("/api/confirmation/edit", {
      method: "POST",
      body: JSON.stringify({
        pending_spec: pendingSpec,
        original_query: originalQuery,
        field,
        value,
      }),
    }),
  confirm: (pendingSpec: Record<string, unknown>, originalQuery: string) =>
    requestJson<VisualizationResponse>("/api/confirmation/confirm", {
      method: "POST",
      body: JSON.stringify({
        pending_spec: pendingSpec,
        original_query: originalQuery,
      }),
    }),
};
