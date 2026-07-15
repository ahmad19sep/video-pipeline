import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { TOKENS, primaryFont, safeInsets } from "./design-tokens";
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
  "urdu-script": UrduScriptCaption,
};

export const Captions: React.FC<Pick<RenderInput, "captions" | "design">> = ({
  captions,
  design,
}) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const seconds = frame / fps;
  const page = captionPages(captions.words, captions.wordsPerPage.max).find(
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
  const entrance = interpolate(
    frame,
    [0, Math.max(1, fps * TOKENS.timing.fast)],
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
        justifyContent: captions.preset === "hook" ? "flex-start" : "flex-end",
        padding: `${insets.top} ${insets.horizontal} ${insets.bottom}`,
        scale: `${entrance}`,
      }}
    >
      <CaptionComponent
        activeId={active?.id ?? null}
        fontFamily={primaryFont(design)}
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
