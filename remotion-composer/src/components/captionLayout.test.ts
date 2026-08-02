import { describe, expect, it } from "vitest";
import {
  chooseCaptionPlacement,
  getReservedCaptionRailHeight,
} from "./captionLayout";

describe("caption layout", () => {
  it("uses the dedicated bottom rail without intersecting protected content", () => {
    const placement = chooseCaptionPlacement({
      frameWidth: 1920,
      frameHeight: 1080,
      currentMs: 1000,
      fontSize: 42,
      wordsOnPage: 6,
      layout: {
        policy: "reserved-rail",
        preferredZone: "bottom",
        reservedRailHeightPx: 180,
        protectedRegions: [
          { id: "main-graphic", x: 0.05, y: 0.05, width: 0.9, height: 0.72 },
        ],
      },
    });

    expect(placement.zone).toBe("bottom");
    expect(placement.collisionAreaPx).toBe(0);
    expect(getReservedCaptionRailHeight({ reservedRailHeightPx: 180 }, 1080)).toBe(180);
  });

  it("moves to the top when the preferred bottom zone is protected", () => {
    const placement = chooseCaptionPlacement({
      frameWidth: 1920,
      frameHeight: 1080,
      currentMs: 2000,
      fontSize: 42,
      wordsOnPage: 6,
      layout: {
        policy: "adaptive-regions",
        preferredZone: "bottom",
        fallbackZones: ["top"],
        protectedRegions: [
          { id: "bottom-chart", x: 0, y: 0.72, width: 1, height: 0.28 },
        ],
      },
    });

    expect(placement.zone).toBe("top");
    expect(placement.collisionAreaPx).toBe(0);
  });

  it("reports collisions instead of silently covering content", () => {
    const placement = chooseCaptionPlacement({
      frameWidth: 1920,
      frameHeight: 1080,
      currentMs: 2000,
      fontSize: 42,
      wordsOnPage: 6,
      layout: {
        policy: "adaptive-regions",
        preferredZone: "bottom",
        fallbackZones: ["top"],
        protectedRegions: [
          { id: "full-frame-subject", x: 0, y: 0, width: 1, height: 1 },
        ],
      },
    });

    expect(placement.collisionAreaPx).toBeGreaterThan(0);
    expect(placement.collisionRegionIds).toContain("full-frame-subject");
  });
});
