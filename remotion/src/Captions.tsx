import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill,
  continueRender,
  delayRender,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { TOKENS, displayFont, primaryFont, safeInsets } from "./design-tokens";
import type { CaptionPreset, CaptionWord, RenderInput } from "./types";

const punctuationOnly = /^\p{P}+$/u;

export const captionPages = (words: CaptionWord[], maxWords: number) => {
  const pages: CaptionWord[][] = [];
  let page: CaptionWord[] = [];
  for (const word of words) {
    if (punctuationOnly.test(word.text) && page.length >= maxWords) {
      const previous = page.pop();
      if (page.length > 0) pages.push(page);
      page = previous ? [previous, word] : [word];
      continue;
    }
    if (page.length >= maxWords) {
      pages.push(page);
      page = [];
    }
    page.push(word);
  }
  if (page.length > 0) pages.push(page);
  return pages;
};

export const DesignFontLoader: React.FC<{
  font: RenderInput["design"]["font"];
}> = ({ font }) => {
  const [handle] = useState(() =>
    delayRender("Loading the bundled Urdu caption font"),
  );
  useEffect(() => {
    let active = true;
    const finish = () => {
      if (active) continueRender(handle);
    };
    if (font.path === null) {
      finish();
      return () => {
        active = false;
      };
    }
    loadFont({
      family: font.family,
      url: staticFile(font.path),
      display: "swap",
      weight: "400 900",
    }).then(finish, finish);
    return () => {
      active = false;
      continueRender(handle);
    };
  }, [font.family, font.path, handle]);
  return null;
};

type CaptionViewProps = {
  activeId: string | null;
  fontFamily: string;
  fontSize: number;
  maxLines: number;
  page: CaptionWord[];
};

const wordsView = (
  props: CaptionViewProps,
  options: {
    activeColor?: string;
    direction?: "ltr" | "rtl";
    script?: boolean;
    transform?: CSSProperties["textTransform"];
  } = {},
) => (
  <div
    dir={options.direction}
    style={{
      direction: options.direction,
      display: "flex",
      flexWrap: "wrap",
      fontFamily: props.fontFamily,
      fontSize: props.fontSize,
      fontWeight: options.script ? 700 : 850,
      gap: options.script ? "0 0.2em" : "0 0.28em",
      justifyContent: "center",
      lineHeight: options.script ? 1.42 : 1.15,
      maxHeight: `${props.maxLines * (options.script ? 1.42 : 1.15)}em`,
      overflow: "hidden",
      textAlign: "center",
      textShadow: TOKENS.shadow.text,
      textTransform: options.transform,
    }}
  >
    {props.page.map((word) => (
      <span
        key={word.id}
        style={{
          color:
            word.id === props.activeId
              ? (options.activeColor ?? TOKENS.color.highlight)
              : word.emphasis
                ? TOKENS.color.accent
                : TOKENS.color.ink,
        }}
      >
        {options.script ? (word.scriptText ?? word.text) : word.text}
      </span>
    ))}
  </div>
);

const RomanWordHighlightCaption: React.FC<CaptionViewProps> = (props) => (
  <div
    style={{
      backgroundColor: "rgba(4, 8, 16, 0.78)",
      borderRadius: TOKENS.radius.medium,
      maxWidth: "90%",
      padding: "0.3em 0.5em",
    }}
  >
    {wordsView(props, { transform: "uppercase" })}
  </div>
);

const CleanTwoLineCaption: React.FC<CaptionViewProps> = (props) => (
  <div style={{ maxWidth: "88%", padding: "0.2em 0.35em" }}>
    {wordsView(props, { activeColor: TOKENS.color.ink })}
  </div>
);

const HookCaption: React.FC<CaptionViewProps> = (props) => (
  <div
    style={{
      background:
        "linear-gradient(110deg, rgba(7,16,31,0.96), rgba(8,47,73,0.9))",
      border: `2px solid ${TOKENS.color.accent}99`,
      borderRadius: TOKENS.radius.large,
      boxShadow: TOKENS.shadow.panel,
      maxWidth: "88%",
      padding: "0.45em 0.6em",
    }}
  >
    {wordsView(
      { ...props, fontSize: props.fontSize * 1.12 },
      { transform: "uppercase" },
    )}
  </div>
);

const DefinitionCaption: React.FC<CaptionViewProps> = (props) => (
  <div
    style={{
      background: TOKENS.color.panel,
      borderLeft: `8px solid ${TOKENS.color.accent}`,
      borderRadius: TOKENS.radius.medium,
      maxWidth: "86%",
      padding: "0.32em 0.55em",
    }}
  >
    <div
      style={{
        color: TOKENS.color.accent,
        fontFamily: props.fontFamily,
        fontSize: "0.9em",
        fontWeight: 900,
        letterSpacing: "0.08em",
      }}
    >
      DEFINITION
    </div>
    {wordsView(props)}
  </div>
);

const QuestionCaption: React.FC<CaptionViewProps> = (props) => (
  <div
    style={{
      background: "rgba(30, 41, 59, 0.92)",
      border: `2px solid ${TOKENS.color.highlight}aa`,
      borderRadius: TOKENS.radius.pill,
      maxWidth: "90%",
      padding: "0.34em 0.62em",
    }}
  >
    {wordsView(props, { activeColor: TOKENS.color.highlight })}
  </div>
);

const ViralPunchCaption: React.FC<CaptionViewProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        alignItems: "center",
        display: "flex",
        flexWrap: "wrap",
        gap: "0.08em 0.36em",
        justifyContent: "center",
        maxWidth: "92%",
        textAlign: "center",
      }}
    >
      {props.page.map((word) => {
        const startFrame = Math.round(word.start * fps);
        const enter = interpolate(
          frame,
          [startFrame, startFrame + Math.max(4, Math.round(fps * 0.18))],
          [0, 1],
          {
            easing: Easing.bezier(0.34, 1.35, 0.64, 1),
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        );
        const active = word.id === props.activeId;
        return (
          <span
            key={word.id}
            style={{
              color: active
                ? TOKENS.color.socialYellow
                : word.emphasis
                  ? TOKENS.color.ink
                  : "#e2e8f0",
              display: "inline-block",
              filter: `blur(${interpolate(enter, [0, 1], [7, 0])}px)`,
              fontFamily: props.fontFamily,
              fontSize: props.fontSize * (active ? 1.14 : 1.02),
              fontWeight: 950,
              letterSpacing: "-0.045em",
              lineHeight: 0.98,
              marginInline: "0.06em",
              opacity: enter,
              scale: `${interpolate(enter, [0, 1], [1.32, 1])}`,
              textShadow: "0 4px 0 #050505, 0 8px 22px rgba(0,0,0,0.88)",
              textTransform: "uppercase",
              translate: `0 ${interpolate(enter, [0, 1], [18, 0])}px`,
              WebkitTextStroke: `${Math.max(2, Math.round(props.fontSize * 0.045))}px #050505`,
            }}
          >
            {word.text}
          </span>
        );
      })}
    </div>
  );
};

const BoxedKeywordCaption: React.FC<CaptionViewProps> = (props) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seconds = frame / fps;
  const word =
    props.page.find((candidate) => candidate.id === props.activeId) ??
    [...props.page].reverse().find((candidate) => candidate.start <= seconds) ??
    props.page[0];
  if (!word) return null;
  const startFrame = Math.round(word.start * fps);
  const enter = interpolate(
    frame,
    [startFrame, startFrame + Math.max(4, Math.round(fps * 0.16))],
    [0, 1],
    {
      easing: Easing.bezier(0.16, 1, 0.3, 1),
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );
  return (
    <div
      style={{
        background: "rgba(3, 7, 18, 0.9)",
        border: "2px solid rgba(255,255,255,0.2)",
        borderRadius: TOKENS.radius.medium,
        boxShadow: "0 14px 34px rgba(0,0,0,0.42)",
        color: word.emphasis ? TOKENS.color.socialYellow : TOKENS.color.ink,
        filter: `blur(${interpolate(enter, [0, 1], [5, 0])}px)`,
        fontFamily: props.fontFamily,
        fontSize: props.fontSize * 1.08,
        fontWeight: 900,
        letterSpacing: "-0.035em",
        lineHeight: 1,
        opacity: enter,
        padding: "0.24em 0.46em 0.3em",
        scale: `${interpolate(enter, [0, 1], [0.88, 1])}`,
        textShadow: TOKENS.shadow.text,
        translate: `0 ${interpolate(enter, [0, 1], [12, 0])}px`,
      }}
    >
      {word.text}
    </div>
  );
};

const UrduScriptCaption: React.FC<CaptionViewProps> = (props) => (
  <div
    style={{
      backgroundColor: "rgba(4, 8, 16, 0.82)",
      borderRadius: TOKENS.radius.medium,
      maxWidth: "90%",
      padding: "0.22em 0.58em 0.35em",
    }}
  >
    {wordsView(
      { ...props, fontSize: props.fontSize * 1.08 },
      { direction: "rtl", script: true },
    )}
  </div>
);

const COMPONENTS: Record<CaptionPreset, React.FC<CaptionViewProps>> = {
  "roman-word-highlight": RomanWordHighlightCaption,
  "clean-two-line": CleanTwoLineCaption,
  hook: HookCaption,
  definition: DefinitionCaption,
  question: QuestionCaption,
  "viral-punch": ViralPunchCaption,
  "boxed-keyword": BoxedKeywordCaption,
  "urdu-script": UrduScriptCaption,
};

export const Captions: React.FC<Pick<RenderInput, "captions" | "design">> = ({
  captions,
  design,
}) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const seconds = frame / fps;
  const pages = useMemo(
    () => captionPages(captions.words, captions.wordsPerPage.max),
    [captions.words, captions.wordsPerPage.max],
  );
  const page = pages.find(
    (candidate) =>
      seconds >= candidate[0].start &&
      seconds < candidate[candidate.length - 1].end,
  );
  if (!page) return null;
  const portrait = height > width;
  const insets = safeInsets(captions.safeZone, portrait);
  const active = page.find(
    (word) => seconds >= word.start && seconds < word.end,
  );
  const CaptionComponent = COMPONENTS[captions.preset] ?? CleanTwoLineCaption;
  const pageStartFrame = Math.round(page[0].start * fps);
  const entrance = interpolate(
    frame,
    [pageStartFrame, pageStartFrame + Math.max(1, fps * TOKENS.timing.fast)],
    [0.94, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent:
          captions.preset === "hook"
            ? "flex-start"
            : captions.preset === "boxed-keyword"
              ? "center"
              : "flex-end",
        padding: `${insets.top} ${insets.horizontal} ${insets.bottom}`,
        scale: `${entrance}`,
      }}
    >
      <CaptionComponent
        activeId={active?.id ?? null}
        fontFamily={
          captions.preset === "viral-punch" ||
          captions.preset === "boxed-keyword"
            ? displayFont(design)
            : primaryFont(design)
        }
        fontSize={Math.round(
          Math.min(width, height) *
            (portrait
              ? TOKENS.type.captionPortrait
              : TOKENS.type.captionLandscape),
        )}
        maxLines={captions.maxLines}
        page={page}
      />
    </AbsoluteFill>
  );
};
