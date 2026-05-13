import { render, screen } from "@testing-library/react";

import { ChartRenderer } from "./ChartRenderer";

describe("ChartRenderer", () => {
  test("renders line charts from normalized chart models", () => {
    render(
      <ChartRenderer
        chartModel={{
          kind: "line",
          title: "Trend",
          rows: [
            { datetime: "2024-01-01", ETa: 1.2, PPT: 0.4 },
            { datetime: "2024-02-01", ETa: 1.5, PPT: 0.1 },
          ],
          x_key: "datetime",
          series: [
            { key: "ETa", label: "ETa", color: "#4c78a8" },
            { key: "PPT", label: "PPT", color: "#f58518" },
          ],
        }}
      />,
    );

    expect(screen.getByTestId("smarttap-chart")).toBeInTheDocument();
  });

  test("renders bar charts from normalized chart models", () => {
    render(
      <ChartRenderer
        chartModel={{
          kind: "bar",
          title: "Grouped Summary",
          rows: [
            { group: "North", ETa: 1.2, PPT: 0.4 },
            { group: "South", ETa: 1.5, PPT: 0.1 },
          ],
          x_key: "group",
          series: [
            { key: "ETa", label: "ETa", color: "#4c78a8" },
            { key: "PPT", label: "PPT", color: "#f58518" },
          ],
          stacked: false,
        }}
      />,
    );

    expect(screen.getByTestId("smarttap-chart")).toBeInTheDocument();
  });

  test("renders pie and donut charts from normalized chart models", () => {
    const { rerender } = render(
      <ChartRenderer
        chartModel={{
          kind: "pie",
          title: "Crop Mix",
          rows: [
            { Group: "Hay", "Field Count": 10 },
            { Group: "Grain", "Field Count": 5 },
          ],
          x_key: "Group",
          series: [{ key: "Field Count", label: "Fields", color: "#4c78a8" }],
        }}
      />,
    );

    expect(screen.getByTestId("smarttap-chart")).toBeInTheDocument();

    rerender(
      <ChartRenderer
        chartModel={{
          kind: "donut",
          title: "Crop Mix",
          rows: [
            { Group: "Hay", "Field Count": 10 },
            { Group: "Grain", "Field Count": 5 },
          ],
          x_key: "Group",
          series: [{ key: "Field Count", label: "Fields", color: "#4c78a8" }],
        }}
      />,
    );

    expect(screen.getByTestId("smarttap-chart")).toBeInTheDocument();
  });
});
