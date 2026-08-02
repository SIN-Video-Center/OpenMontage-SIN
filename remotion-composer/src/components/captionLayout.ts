export type CaptionZone = "top" | "bottom";
export type CaptionLayoutPolicy = "reserved-rail" | "adaptive-regions";

export interface NormalizedRect {
  id?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  startMs?: number;
  endMs?: number;
}

export interface CaptionLayoutConfig {
  policy?: CaptionLayoutPolicy;
  preferredZone?: CaptionZone;
  fallbackZones?: CaptionZone[];
  safeMarginPx?: number;
  reservedRailHeightPx?: number;
  reservedRailHeightRatio?: number;
  protectedRegions?: NormalizedRect[];
}

export interface PixelRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CaptionPlacement {
  zone: CaptionZone;
  rect: PixelRect;
  collisionAreaPx: number;
  collisionRegionIds: string[];
}

export const DEFAULT_CAPTION_LAYOUT: Required<
  Omit<CaptionLayoutConfig, "protectedRegions">
> & { protectedRegions: NormalizedRect[] } = {
  policy: "reserved-rail",
  preferredZone: "bottom",
  fallbackZones: ["top"],
  safeMarginPx: 48,
  reservedRailHeightPx: 180,
  reservedRailHeightRatio: 1 / 6,
  protectedRegions: [],
};

const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

export const normalizeCaptionLayout = (
  layout?: CaptionLayoutConfig,
): typeof DEFAULT_CAPTION_LAYOUT => ({
  ...DEFAULT_CAPTION_LAYOUT,
  ...layout,
  fallbackZones: layout?.fallbackZones ?? DEFAULT_CAPTION_LAYOUT.fallbackZones,
  protectedRegions: layout?.protectedRegions ?? DEFAULT_CAPTION_LAYOUT.protectedRegions,
});

export const getReservedCaptionRailHeight = (
  layout: CaptionLayoutConfig | undefined,
  frameHeight: number,
): number => {
  const resolved = normalizeCaptionLayout(layout);
  if (resolved.policy !== "reserved-rail") return 0;
  const requested = layout?.reservedRailHeightRatio !== undefined
    ? frameHeight * layout.reservedRailHeightRatio
    : resolved.reservedRailHeightPx;
  return Math.max(120, Math.min(frameHeight * 0.28, requested));
};

const toPixelRect = (
  region: NormalizedRect,
  frameWidth: number,
  frameHeight: number,
): PixelRect => ({
  x: clamp01(region.x) * frameWidth,
  y: clamp01(region.y) * frameHeight,
  width: clamp01(region.width) * frameWidth,
  height: clamp01(region.height) * frameHeight,
});

const intersectionArea = (a: PixelRect, b: PixelRect): number => {
  const width = Math.max(
    0,
    Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x),
  );
  const height = Math.max(
    0,
    Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y),
  );
  return width * height;
};

const regionIsActive = (region: NormalizedRect, currentMs: number): boolean =>
  (region.startMs === undefined || currentMs >= region.startMs) &&
  (region.endMs === undefined || currentMs <= region.endMs);

const estimateCaptionHeight = (
  fontSize: number,
  wordsOnPage: number,
  frameWidth: number,
): number => {
  const estimatedCharacters = Math.max(12, wordsOnPage * 8);
  const usableWidth = frameWidth * 0.78;
  const approximateCharactersPerLine = Math.max(
    14,
    Math.floor(usableWidth / Math.max(1, fontSize * 0.56)),
  );
  const lines = Math.max(1, Math.min(3, Math.ceil(estimatedCharacters / approximateCharactersPerLine)));
  return Math.ceil(lines * fontSize * 1.35 + 32);
};

const rectForZone = (
  zone: CaptionZone,
  frameWidth: number,
  frameHeight: number,
  fontSize: number,
  wordsOnPage: number,
  layout: ReturnType<typeof normalizeCaptionLayout>,
): PixelRect => {
  const margin = layout.safeMarginPx;
  const captionHeight = estimateCaptionHeight(fontSize, wordsOnPage, frameWidth);
  const width = Math.max(1, frameWidth - margin * 2);

  if (layout.policy === "reserved-rail") {
    const railHeight = getReservedCaptionRailHeight(layout, frameHeight);
    const y = zone === "bottom"
      ? frameHeight - railHeight + Math.max(0, (railHeight - captionHeight) / 2)
      : Math.max(0, (railHeight - captionHeight) / 2);
    return { x: margin, y, width, height: captionHeight };
  }

  return {
    x: margin,
    y: zone === "bottom"
      ? frameHeight - margin - captionHeight
      : margin,
    width,
    height: captionHeight,
  };
};

export const chooseCaptionPlacement = (args: {
  frameWidth: number;
  frameHeight: number;
  currentMs: number;
  fontSize: number;
  wordsOnPage: number;
  layout?: CaptionLayoutConfig;
}): CaptionPlacement => {
  const layout = normalizeCaptionLayout(args.layout);
  const zoneOrder = Array.from(
    new Set<CaptionZone>([
      layout.preferredZone,
      ...layout.fallbackZones,
      layout.preferredZone === "bottom" ? "top" : "bottom",
    ]),
  );
  const activeRegions = layout.protectedRegions.filter((region) =>
    regionIsActive(region, args.currentMs),
  );

  const candidates = zoneOrder.map((zone): CaptionPlacement => {
    const rect = rectForZone(
      zone,
      args.frameWidth,
      args.frameHeight,
      args.fontSize,
      args.wordsOnPage,
      layout,
    );
    const collisions = activeRegions
      .map((region) => ({
        id: region.id ?? "protected-region",
        area: intersectionArea(
          rect,
          toPixelRect(region, args.frameWidth, args.frameHeight),
        ),
      }))
      .filter((collision) => collision.area > 0);

    return {
      zone,
      rect,
      collisionAreaPx: collisions.reduce((sum, collision) => sum + collision.area, 0),
      collisionRegionIds: collisions.map((collision) => collision.id),
    };
  });

  return candidates.reduce((best, candidate) =>
    candidate.collisionAreaPx < best.collisionAreaPx ? candidate : best,
  );
};
