import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  chooseCaptionPlacement,
  getReservedCaptionRailHeight,
  normalizeCaptionLayout,
  type CaptionLayoutConfig,
} from "./captionLayout";

export interface WordCaption {
  word: string;
  startMs: number;
  endMs: number;
}

export type CaptionVisualTreatment =
  | "integrated-field"
  | "local-pill"
  | "surface";

interface CaptionOverlayProps {
  words: WordCaption[];
  wordsPerPage?: number;
  fontSize?: number;
  color?: string;
  highlightColor?: string;
  backgroundColor?: string;
  fontFamily?: string;
  layout?: CaptionLayoutConfig;
  visualTreatment?: CaptionVisualTreatment;
  fullWidthBackground?: boolean;
}

interface CaptionPage {
  words: WordCaption[];
  startMs: number;
  endMs: number;
}

export function buildCaptionPages(
  words: WordCaption[],
  wordsPerPage: number,
): CaptionPage[] {
  const pages: CaptionPage[] = [];
  for (let i = 0; i < words.length; i += wordsPerPage) {
    const pageWords = words.slice(i, i + wordsPerPage);
    if (pageWords.length === 0) continue;
    pages.push({
      words: pageWords,
      startMs: pageWords[0].startMs,
      endMs: pageWords[pageWords.length - 1].endMs,
    });
  }
  return pages;
}

const PageRenderer: React.FC<{
  page: CaptionPage;
  fontSize: number;
  color: string;
  highlightColor: string;
  backgroundColor: string;
  fontFamily: string;
  layout?: CaptionLayoutConfig;
  visualTreatment: CaptionVisualTreatment;
}> = ({
  page,
  fontSize,
  color,
  highlightColor,
  backgroundColor,
  fontFamily,
  layout,
  visualTreatment,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const currentMs = page.startMs + (frame / fps) * 1000;
  const placement = chooseCaptionPlacement({
    frameWidth: width,
    frameHeight: height,
    currentMs,
    fontSize,
    wordsOnPage: page.words.length,
    layout,
  });

  if (placement.collisionAreaPx > 0) {
    throw new Error(
      `Caption collision at ${Math.round(currentMs)}ms in ${placement.zone} zone: ` +
        placement.collisionRegionIds.join(", "),
    );
  }

  const entrance = spring({
    frame,
    fps,
    config: {damping: 20, stiffness: 130, mass: 0.8},
  });
  const usesLocalBacking = visualTreatment === "local-pill";

  return (
    <AbsoluteFill data-caption-zone={placement.zone} style={{pointerEvents: "none"}}>
      <div
        style={{
          position: "absolute",
          left: placement.rect.x,
          top: placement.rect.y,
          width: placement.rect.width,
          minHeight: placement.rect.height,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <div
          data-caption-treatment={visualTreatment}
          style={{
            opacity: entrance,
            transform: `translateY(${interpolate(entrance, [0, 1], [10, 0])}px)`,
            backgroundColor: usesLocalBacking ? backgroundColor : "transparent",
            borderRadius: usesLocalBacking ? 14 : 0,
            padding: usesLocalBacking ? "12px 24px" : "8px 20px",
            maxWidth: "86%",
            textAlign: "center",
          }}
        >
          <span
            style={{
              fontSize,
              fontWeight: 650,
              fontFamily,
              letterSpacing: "-0.018em",
              lineHeight: 1.3,
              whiteSpace: "pre-wrap",
              textWrap: "balance",
            }}
          >
            {page.words.map((word, index) => {
              const isActive = word.startMs <= currentMs && word.endMs > currentMs;
              const isPast = word.endMs <= currentMs;
              return (
                <span
                  key={`${word.startMs}-${index}`}
                  style={{
                    color: isActive ? highlightColor : isPast ? color : `${color}B8`,
                    textShadow: isActive
                      ? `0 0 18px ${highlightColor}4D, 0 2px 12px rgba(0,0,0,0.72)`
                      : "0 2px 12px rgba(0,0,0,0.72)",
                  }}
                >
                  {word.word}{index < page.words.length - 1 ? " " : ""}
                </span>
              );
            })}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const CaptionOverlay: React.FC<CaptionOverlayProps> = ({
  words,
  wordsPerPage = 7,
  fontSize = 40,
  color = "#F8FAFC",
  highlightColor = "#67E8F9",
  backgroundColor = "rgba(5, 12, 20, 0.72)",
  fontFamily = "Inter, ui-sans-serif, system-ui, sans-serif",
  layout,
  visualTreatment = "integrated-field",
  fullWidthBackground = false,
}) => {
  const {fps, height} = useVideoConfig();
  const pages = buildCaptionPages(words, wordsPerPage);
  const resolvedLayout = normalizeCaptionLayout(layout);
  const railHeight = getReservedCaptionRailHeight(resolvedLayout, height);
  const drawSurface =
    visualTreatment === "surface" &&
    fullWidthBackground &&
    resolvedLayout.policy === "reserved-rail";

  return (
    <AbsoluteFill style={{zIndex: 100, pointerEvents: "none"}}>
      {drawSurface ? (
        <div
          data-caption-surface="true"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: resolvedLayout.preferredZone === "bottom" ? 0 : undefined,
            top: resolvedLayout.preferredZone === "top" ? 0 : undefined,
            height: railHeight,
            background: backgroundColor,
          }}
        />
      ) : null}
      {pages.map((page, index) => {
        const fromFrame = Math.round((page.startMs / 1000) * fps);
        const nextStart = pages[index + 1]?.startMs ?? page.endMs + 500;
        const duration = Math.max(
          1,
          Math.round(((nextStart - page.startMs) / 1000) * fps),
        );

        return (
          <Sequence key={index} from={fromFrame} durationInFrames={duration}>
            <PageRenderer
              page={page}
              fontSize={fontSize}
              color={color}
              highlightColor={highlightColor}
              backgroundColor={backgroundColor}
              fontFamily={fontFamily}
              layout={resolvedLayout}
              visualTreatment={visualTreatment}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export type {CaptionLayoutConfig, NormalizedRect} from "./captionLayout";
