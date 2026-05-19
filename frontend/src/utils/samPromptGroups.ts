import type { SamPrompt } from "../api/client";

export type SamInferencePlan = {
  /** 순차 `samPredict`에 넘길 프롬프트 그룹 */
  groups: SamPrompt[][];
  /** 박스가 있으면 SAM에는 박스만 보내고 점은 무시 */
  pointsIgnoredForBox: boolean;
  /** 양성 점이 2개 이상이면 음성 점은 전송하지 않음 */
  negativesIgnoredForMultiPositive: boolean;
};

function isBox(p: SamPrompt): boolean {
  return p.type === "box";
}

function isPositivePoint(p: SamPrompt): boolean {
  return p.type === "point" && p.label === "positive";
}

function clonePrompt(p: SamPrompt): SamPrompt {
  return { ...p };
}

/**
 * SAM은 “여러 양성 = 한 객체”로 해석하므로, 양성이 여러 개일 때는 점마다 별도 predict 그룹으로 나눈다.
 * 박스가 있으면 한 그룹에 박스만 보낸다(백엔드는 단일 박스 위주).
 */
export function buildSamInferencePlan(prompts: SamPrompt[]): SamInferencePlan {
  const boxes = prompts.filter(isBox);
  const positivePoints = prompts.filter(isPositivePoint);
  const negativeCount = prompts.filter((p) => p.type === "point" && p.label === "negative").length;
  const pointCount = prompts.filter((p) => p.type === "point").length;

  if (boxes.length > 0) {
    return {
      groups: [boxes.map(clonePrompt)],
      pointsIgnoredForBox: pointCount > 0,
      negativesIgnoredForMultiPositive: false,
    };
  }

  if (positivePoints.length === 0) {
    return {
      groups: [],
      pointsIgnoredForBox: false,
      negativesIgnoredForMultiPositive: false,
    };
  }

  if (positivePoints.length === 1) {
    return {
      groups: [prompts.map(clonePrompt)],
      pointsIgnoredForBox: false,
      negativesIgnoredForMultiPositive: false,
    };
  }

  return {
    groups: positivePoints.map((p) => [clonePrompt(p)]),
    pointsIgnoredForBox: false,
    negativesIgnoredForMultiPositive: negativeCount > 0,
  };
}
