import { describe, expect, it } from "vitest";
import { acceptEventId } from "@/hooks/use-run-events";
import { cn, displayValue, formatNumber } from "./utils";

describe("frontend foundations", () => {
  it("merges Tailwind component classes deterministically", () => {
    expect(cn("px-2", "px-4", false && "hidden")).toBe("px-4");
  });

  it("formats API table values without inventing data", () => {
    expect(displayValue(null)).toBe("—");
    expect(displayValue({ side: "buy" })).toBe('{"side":"buy"}');
    expect(formatNumber(1200.125, 2)).toBe("1,200.13");
  });

  it("rejects duplicate and stale SSE event ids", () => {
    const seen = new Set([12]);
    expect(acceptEventId(13, 12, seen)).toBe(true);
    expect(acceptEventId(12, 12, seen)).toBe(false);
    expect(acceptEventId(11, 12, seen)).toBe(false);
    expect(acceptEventId(12, 10, seen)).toBe(false);
  });
});
