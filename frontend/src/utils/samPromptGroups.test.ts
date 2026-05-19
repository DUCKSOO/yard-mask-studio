import { describe, expect, it } from "vitest";
import type { SamPrompt } from "../api/client";
import { buildSamInferencePlan } from "./samPromptGroups";

describe("buildSamInferencePlan", () => {
  it("returns no groups when only negative points", () => {
    const prompts: SamPrompt[] = [
      { type: "point", x: 1, y: 2, label: "negative" },
    ];
    const plan = buildSamInferencePlan(prompts);
    expect(plan.groups).toEqual([]);
    expect(plan.pointsIgnoredForBox).toBe(false);
    expect(plan.negativesIgnoredForMultiPositive).toBe(false);
  });

  it("returns no groups when empty", () => {
    const plan = buildSamInferencePlan([]);
    expect(plan.groups).toEqual([]);
  });

  it("single positive: one group with full prompt list", () => {
    const prompts: SamPrompt[] = [
      { type: "point", x: 10, y: 20, label: "positive" },
      { type: "point", x: 30, y: 40, label: "negative" },
    ];
    const plan = buildSamInferencePlan(prompts);
    expect(plan.groups).toHaveLength(1);
    expect(plan.groups[0]).toEqual(prompts);
    expect(plan.negativesIgnoredForMultiPositive).toBe(false);
  });

  it("two positives: separate single-point groups", () => {
    const prompts: SamPrompt[] = [
      { type: "point", x: 1, y: 1, label: "positive" },
      { type: "point", x: 99, y: 99, label: "positive" },
    ];
    const plan = buildSamInferencePlan(prompts);
    expect(plan.groups).toEqual([
      [{ type: "point", x: 1, y: 1, label: "positive" }],
      [{ type: "point", x: 99, y: 99, label: "positive" }],
    ]);
    expect(plan.negativesIgnoredForMultiPositive).toBe(false);
  });

  it("two positives + negative: negatives not sent to SAM (flag)", () => {
    const prompts: SamPrompt[] = [
      { type: "point", x: 1, y: 1, label: "positive" },
      { type: "point", x: 5, y: 5, label: "negative" },
      { type: "point", x: 99, y: 99, label: "positive" },
    ];
    const plan = buildSamInferencePlan(prompts);
    expect(plan.groups).toHaveLength(2);
    expect(plan.groups[0]).toEqual([{ type: "point", x: 1, y: 1, label: "positive" }]);
    expect(plan.groups[1]).toEqual([{ type: "point", x: 99, y: 99, label: "positive" }]);
    expect(plan.negativesIgnoredForMultiPositive).toBe(true);
  });

  it("box present: single group of boxes only; points ignored flag", () => {
    const prompts: SamPrompt[] = [
      { type: "point", x: 1, y: 1, label: "positive" },
      { type: "box", x1: 0, y1: 0, x2: 10, y2: 10 },
    ];
    const plan = buildSamInferencePlan(prompts);
    expect(plan.groups).toEqual([[{ type: "box", x1: 0, y1: 0, x2: 10, y2: 10 }]]);
    expect(plan.pointsIgnoredForBox).toBe(true);
  });

  it("box only: one group", () => {
    const prompts: SamPrompt[] = [{ type: "box", x1: 1, y1: 2, x2: 8, y2: 9 }];
    const plan = buildSamInferencePlan(prompts);
    expect(plan.groups).toEqual([[{ type: "box", x1: 1, y1: 2, x2: 8, y2: 9 }]]);
    expect(plan.pointsIgnoredForBox).toBe(false);
  });
});
