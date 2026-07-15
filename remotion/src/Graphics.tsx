import {
  AbsoluteFill,
  Easing,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { CSSProperties, ReactNode } from "react";
import { TOKENS, displayFont, panelStyle, primaryFont } from "./design-tokens";
import type { Graphic, RenderInput, Scene } from "./types";

const frameAt = (seconds: number, fps: number) => Math.round(seconds * fps);

const stringProp = (graphic: Graphic, key: string, fallback = "") => {
  const value = graphic.props[key];
  return typeof value === "string" ? value : fallback;
};

const numberProp = (graphic: Graphic, key: string, fallback = 0) => {
  const value = graphic.props[key];
  return typeof value === "number" ? value : fallback;
};

const listProp = (graphic: Graphic, key: string) => {
  const value = graphic.props[key];
  return Array.isArray(value) ? value : [];
};

const Stack: React.FC<{ children: ReactNode; style?: CSSProperties }> = ({
  children,
  style,
}) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: TOKENS.spacing.sm,
      ...style,
    }}
  >
    {children}
  </div>
);

const Title: React.FC<{ children: ReactNode; accent?: boolean }> = ({
  children,
  accent,
}) => (
  <div
    style={{
      color: accent ? TOKENS.color.accent : TOKENS.color.ink,
      fontSize: "2.5em",
      fontWeight: 900,
      lineHeight: 1.06,
    }}
  >
    {children}
  </div>
);

const Body: React.FC<{ children: ReactNode }> = ({ children }) => (
  <div
    style={{
      color: TOKENS.color.muted,
      fontSize: "1.3em",
      fontWeight: 650,
      lineHeight: 1.3,
    }}
  >
    {children}
  </div>
);

const List: React.FC<{ items: string[]; ordered?: boolean }> = ({
  items,
  ordered,
}) => (
  <Stack style={{ fontSize: "1.15em", fontWeight: 700 }}>
    {items.slice(0, 8).map((item, index) => (
      <div
        key={`${item}-${index}`}
        style={{ display: "flex", gap: TOKENS.spacing.sm }}
      >
        <span style={{ color: TOKENS.color.accent }}>
          {ordered ? `${index + 1}.` : "✓"}
        </span>
        <span>{item}</span>
      </div>
    ))}
  </Stack>
);

const BrowserChrome: React.FC<{
  address: string;
  children: ReactNode;
  title: string;
}> = ({ address, children, title }) => (
  <div
    style={{
      background: "#e2e8f0",
      borderRadius: TOKENS.radius.medium,
      color: "#0f172a",
      overflow: "hidden",
      width: "100%",
    }}
  >
    <div
      style={{
        alignItems: "center",
        background: "#cbd5e1",
        display: "flex",
        gap: 10,
        padding: "0.7em 0.9em",
      }}
    >
      <span style={{ color: "#ef4444" }}>●</span>
      <span style={{ color: "#eab308" }}>●</span>
      <span style={{ color: "#22c55e" }}>●</span>
      <div
        style={{
          background: "white",
          borderRadius: TOKENS.radius.pill,
          flex: 1,
          fontSize: "0.7em",
          marginLeft: 10,
          overflow: "hidden",
          padding: "0.45em 0.8em",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {address || "local.app"}
      </div>
    </div>
    <Stack style={{ padding: "1em 1.2em" }}>
      <Title>{title}</Title>
      {children}
    </Stack>
  </div>
);

const MobileChrome: React.FC<{ items: string[]; title: string }> = ({
  items,
  title,
}) => {
  const frame = useCurrentFrame();
  const typed = title.slice(0, Math.max(0, Math.floor(frame / 1.5)));
  return (
    <div
      style={{
        background: "#17191f",
        border: "9px solid #090a0d",
        borderRadius: 48,
        boxShadow: "0 0 0 2px #64748b, 0 28px 70px rgba(0,0,0,0.55)",
        color: "#f8fafc",
        maxHeight: "100%",
        minHeight: "34em",
        overflow: "hidden",
        padding: "0.8em 0.72em 1em",
        width: "82%",
      }}
    >
      <div
        style={{
          background: "#050608",
          borderRadius: TOKENS.radius.pill,
          height: 16,
          margin: "0 auto 0.9em",
          width: "34%",
        }}
      />
      <div
        style={{
          alignItems: "center",
          background: "#252832",
          border: "2px solid #3b4150",
          borderRadius: TOKENS.radius.pill,
          display: "flex",
          fontSize: "1.05em",
          fontWeight: 750,
          gap: 10,
          minHeight: "2.8em",
          padding: "0.58em 0.8em",
        }}
      >
        <span style={{ color: TOKENS.color.muted }}>⌕</span>
        <span style={{ flex: 1 }}>{typed}</span>
        <span
          style={{
            background: TOKENS.color.accent,
            borderRadius: "50%",
            color: "#07101f",
            display: "grid",
            height: 30,
            placeItems: "center",
            width: 30,
          }}
        >
          →
        </span>
      </div>
      <Stack style={{ gap: 4, marginTop: "0.75em" }}>
        {items.slice(0, 6).map((item, index) => {
          const reveal = interpolate(
            frame,
            [8 + index * 3, 14 + index * 3],
            [0, 1],
            {
              easing: Easing.bezier(0.16, 1, 0.3, 1),
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            },
          );
          return (
            <div
              key={`${item}-${index}`}
              style={{
                alignItems: "center",
                borderBottom: "1px solid #303540",
                color: "#e5e7eb",
                display: "flex",
                fontSize: "0.88em",
                gap: 10,
                opacity: reveal,
                padding: "0.64em 0.25em",
                translate: `${interpolate(reveal, [0, 1], [16, 0])}px 0`,
              }}
            >
              <span style={{ color: TOKENS.color.muted }}>⌕</span>
              <span>{item}</span>
            </div>
          );
        })}
      </Stack>
    </div>
  );
};

const KineticHeadlineContent: React.FC<{
  accent?: string;
  eyebrow?: string;
  headline: string;
}> = ({ accent, eyebrow, headline }) => {
  const frame = useCurrentFrame();
  const words = headline.split(/\s+/).filter(Boolean).slice(0, 12);
  const effectiveAccent = (
    accent ||
    words[words.length - 1] ||
    ""
  ).toLocaleLowerCase();
  return (
    <Stack style={{ alignItems: "center", gap: TOKENS.spacing.md }}>
      {eyebrow ? (
        <div
          style={{
            background: TOKENS.color.socialYellow,
            borderRadius: TOKENS.radius.pill,
            color: "#080808",
            fontSize: "0.92em",
            fontWeight: 950,
            letterSpacing: "0.08em",
            padding: "0.35em 0.72em",
            textTransform: "uppercase",
          }}
        >
          {eyebrow}
        </div>
      ) : null}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.02em 0.3em",
          justifyContent: "center",
          maxWidth: "96%",
          textAlign: "center",
        }}
      >
        {words.map((word, index) => {
          const reveal = interpolate(
            frame,
            [index * 3, index * 3 + 7],
            [0, 1],
            {
              easing: Easing.bezier(0.34, 1.35, 0.64, 1),
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            },
          );
          const normalizedWord = word
            .replace(/[^\p{L}\p{N}]/gu, "")
            .toLocaleLowerCase();
          return (
            <span
              key={`${word}-${index}`}
              style={{
                color:
                  normalizedWord === effectiveAccent
                    ? TOKENS.color.socialYellow
                    : TOKENS.color.ink,
                display: "inline-block",
                filter: `blur(${interpolate(reveal, [0, 1], [7, 0])}px)`,
                fontSize: "3.25em",
                fontWeight: 950,
                letterSpacing: "-0.055em",
                lineHeight: 0.94,
                marginInline: "0.08em",
                opacity: reveal,
                scale: `${interpolate(reveal, [0, 1], [1.24, 1])}`,
                textShadow: "0 5px 0 #050505, 0 16px 38px rgba(0,0,0,0.7)",
                textTransform: "uppercase",
                translate: `0 ${interpolate(reveal, [0, 1], [22, 0])}px`,
                WebkitTextStroke: "2px #050505",
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </Stack>
  );
};

const PriceComparisonGraphic: React.FC<{ graphic: Graphic }> = ({
  graphic,
}) => {
  const frame = useCurrentFrame();
  const values = [
    {
      color: TOKENS.color.socialRed,
      heading: "LOW",
      value: stringProp(graphic, "lowValue", "$1"),
    },
    {
      color: TOKENS.color.socialGreen,
      heading: "HIGH",
      value: stringProp(graphic, "highValue", "$10K"),
    },
  ];
  return (
    <Stack
      style={{ alignItems: "center", gap: TOKENS.spacing.lg, width: "100%" }}
    >
      <div style={{ fontSize: "1.35em", fontWeight: 900 }}>
        {stringProp(graphic, "label", "VALUE")}
      </div>
      <div
        style={{
          display: "grid",
          gap: TOKENS.spacing.md,
          gridTemplateColumns: "1fr 1fr",
          width: "100%",
        }}
      >
        {values.map((item, index) => {
          const reveal = interpolate(
            frame,
            [index * 5, index * 5 + 8],
            [0, 1],
            {
              easing: Easing.bezier(0.16, 1, 0.3, 1),
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            },
          );
          return (
            <Stack
              key={item.heading}
              style={{
                alignItems: "center",
                background: `${item.color}18`,
                border: `4px solid ${item.color}`,
                borderRadius: TOKENS.radius.large,
                boxShadow: `0 0 34px ${item.color}40`,
                opacity: reveal,
                padding: "1.05em 0.6em",
                scale: `${interpolate(reveal, [0, 1], [0.82, 1])}`,
              }}
            >
              <div
                style={{
                  color: item.color,
                  fontSize: "0.85em",
                  fontWeight: 950,
                  letterSpacing: "0.1em",
                }}
              >
                {item.heading}
              </div>
              <div
                style={{
                  color: item.color,
                  fontSize: "3.3em",
                  fontWeight: 950,
                  letterSpacing: "-0.05em",
                  lineHeight: 1,
                  textShadow: "0 8px 24px rgba(0,0,0,0.5)",
                }}
              >
                {item.value}
              </div>
            </Stack>
          );
        })}
      </div>
    </Stack>
  );
};

const Comparison: React.FC<{ graphic: Graphic }> = ({ graphic }) => (
  <div
    style={{
      display: "grid",
      gap: TOKENS.spacing.md,
      gridTemplateColumns: "1fr 1fr",
    }}
  >
    {(
      [
        ["leftTitle", "leftItems", TOKENS.color.accent],
        ["rightTitle", "rightItems", TOKENS.color.positive],
      ] as const
    ).map(([titleKey, itemsKey, color]) => (
      <Stack
        key={titleKey}
        style={{
          background: "rgba(255,255,255,0.06)",
          borderRadius: TOKENS.radius.medium,
          padding: "1em",
        }}
      >
        <div style={{ color, fontSize: "1.55em", fontWeight: 900 }}>
          {stringProp(graphic, titleKey)}
        </div>
        <List items={listProp(graphic, itemsKey)} />
      </Stack>
    ))}
  </div>
);

const Timeline: React.FC<{ items: string[] }> = ({ items }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      position: "relative",
    }}
  >
    <div
      style={{
        background: TOKENS.color.accent,
        height: 4,
        left: "4%",
        opacity: 0.6,
        position: "absolute",
        right: "4%",
        top: 16,
      }}
    />
    {items.slice(0, 6).map((item, index) => (
      <Stack
        key={`${item}-${index}`}
        style={{
          alignItems: "center",
          maxWidth: "16%",
          textAlign: "center",
          zIndex: 1,
        }}
      >
        <div
          style={{
            background: TOKENS.color.accent,
            border: "5px solid #07101f",
            borderRadius: "50%",
            height: 34,
            width: 34,
          }}
        />
        <div style={{ fontSize: "0.9em", fontWeight: 750 }}>{item}</div>
      </Stack>
    ))}
  </div>
);

const LayoutMarker: React.FC<{
  label: string;
  mode: "pip" | "fullscreen" | "split";
}> = ({ label, mode }) => {
  const common: CSSProperties = {
    alignItems: "center",
    border: `3px solid ${TOKENS.color.accent}`,
    display: "flex",
    justifyContent: "center",
  };
  if (mode === "pip") {
    return (
      <div
        style={{
          ...common,
          borderRadius: TOKENS.radius.medium,
          height: 140,
          marginLeft: "auto",
          width: "34%",
        }}
      >
        {label || "Picture in picture"}
      </div>
    );
  }
  if (mode === "split") {
    return (
      <div
        style={{
          display: "grid",
          gap: 8,
          gridTemplateColumns: "1fr 1fr",
          height: 190,
        }}
      >
        <div style={common}>{label || "Left"}</div>
        <div style={common}>Right</div>
      </div>
    );
  }
  return (
    <div style={{ ...common, borderRadius: TOKENS.radius.medium, height: 220 }}>
      {label || "Fullscreen B-roll"}
    </div>
  );
};

const GraphicContent: React.FC<{
  design: RenderInput["design"];
  graphic: Graphic;
}> = ({ design, graphic }) => {
  switch (graphic.component) {
    case "HookTitle":
      if (design.stylePreset === "viral-social") {
        return (
          <KineticHeadlineContent
            accent={stringProp(graphic, "title")
              .split(/\s+/)
              .filter(Boolean)
              .pop()}
            eyebrow={stringProp(graphic, "subtitle")}
            headline={stringProp(graphic, "title", "Untitled")}
          />
        );
      }
      return (
        <Stack style={{ textAlign: "center" }}>
          <Title accent>{stringProp(graphic, "title", "Untitled")}</Title>
          <Body>{stringProp(graphic, "subtitle")}</Body>
        </Stack>
      );
    case "DefinitionCard":
      return (
        <Stack>
          <Title accent>{stringProp(graphic, "term", "Term")}</Title>
          <Body>
            {stringProp(graphic, "definition", "Definition unavailable")}
          </Body>
        </Stack>
      );
    case "LowerThird":
      return (
        <Stack>
          <Title>{stringProp(graphic, "name", "Speaker")}</Title>
          <Body>{stringProp(graphic, "role")}</Body>
        </Stack>
      );
    case "EndCallToAction":
      return (
        <Stack style={{ alignItems: "center", textAlign: "center" }}>
          <Title accent>{stringProp(graphic, "text", "Continue")}</Title>
          <div
            style={{
              background: TOKENS.color.accent,
              borderRadius: TOKENS.radius.pill,
              color: "#07101f",
              fontSize: "1.1em",
              fontWeight: 900,
              padding: "0.6em 1.2em",
            }}
          >
            NEXT STEP
          </div>
        </Stack>
      );
    case "StepCard":
      return (
        <div
          style={{
            alignItems: "center",
            display: "grid",
            gap: TOKENS.spacing.md,
            gridTemplateColumns: "auto 1fr",
          }}
        >
          <div
            style={{
              alignItems: "center",
              background: TOKENS.color.accent,
              borderRadius: "50%",
              color: "#07101f",
              display: "flex",
              fontSize: "2em",
              fontWeight: 950,
              height: 90,
              justifyContent: "center",
              width: 90,
            }}
          >
            {numberProp(graphic, "step", 1)}
          </div>
          <Stack>
            <Title>{stringProp(graphic, "title", "Step")}</Title>
            <Body>{stringProp(graphic, "body")}</Body>
          </Stack>
        </div>
      );
    case "ComparisonCard":
      return <Comparison graphic={graphic} />;
    case "ToolLogoRow":
      return (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: TOKENS.spacing.md,
            justifyContent: "center",
          }}
        >
          {listProp(graphic, "tools").map((tool) => (
            <div
              key={tool}
              style={{
                alignItems: "center",
                background: "rgba(255,255,255,0.08)",
                borderRadius: TOKENS.radius.medium,
                display: "flex",
                fontSize: "1.15em",
                fontWeight: 850,
                height: 100,
                justifyContent: "center",
                padding: "0 1em",
                minWidth: 100,
              }}
            >
              {tool}
            </div>
          ))}
        </div>
      );
    case "BrowserWindow":
      return (
        <BrowserChrome
          address={stringProp(graphic, "address")}
          title={stringProp(graphic, "title", "Browser demo")}
        >
          <List items={listProp(graphic, "steps")} ordered />
        </BrowserChrome>
      );
    case "MobileScreenFrame":
      return (
        <div style={{ display: "flex", justifyContent: "center" }}>
          <MobileChrome
            items={listProp(graphic, "steps")}
            title={stringProp(graphic, "title", "Mobile demo")}
          />
        </div>
      );
    case "QuoteCard":
      return (
        <Stack style={{ textAlign: "center" }}>
          <div
            style={{
              color: TOKENS.color.accent,
              fontSize: "4em",
              lineHeight: 0.6,
            }}
          >
            “
          </div>
          <Title>{stringProp(graphic, "quote", "Quote unavailable")}</Title>
          <Body>{stringProp(graphic, "attribution")}</Body>
        </Stack>
      );
    case "StatisticCard":
      return (
        <Stack style={{ alignItems: "center", textAlign: "center" }}>
          <div
            style={{
              color: TOKENS.color.accent,
              fontSize: "5em",
              fontWeight: 950,
              lineHeight: 1,
            }}
          >
            {stringProp(graphic, "value", "0")}
          </div>
          <Title>{stringProp(graphic, "label", "Statistic")}</Title>
          <Body>{stringProp(graphic, "source")}</Body>
        </Stack>
      );
    case "WarningCard":
      return (
        <div
          style={{
            alignItems: "center",
            display: "grid",
            gap: TOKENS.spacing.md,
            gridTemplateColumns: "auto 1fr",
          }}
        >
          <div style={{ color: TOKENS.color.warning, fontSize: "4em" }}>⚠</div>
          <Stack>
            <Title>{stringProp(graphic, "title", "Warning")}</Title>
            <Body>{stringProp(graphic, "body")}</Body>
          </Stack>
        </div>
      );
    case "QuestionCard":
      return (
        <Stack style={{ alignItems: "center", textAlign: "center" }}>
          <div
            style={{
              color: TOKENS.color.highlight,
              fontSize: "4em",
              fontWeight: 950,
            }}
          >
            ?
          </div>
          <Title>{stringProp(graphic, "question", "What happens next?")}</Title>
        </Stack>
      );
    case "TimelineGraphic":
      return <Timeline items={listProp(graphic, "items")} />;
    case "FeatureList":
      return (
        <Stack>
          <Title accent>{stringProp(graphic, "title", "Features")}</Title>
          <List items={listProp(graphic, "items")} />
        </Stack>
      );
    case "ProgressIndicator": {
      const value = Math.max(0, Math.min(100, numberProp(graphic, "value")));
      return (
        <Stack>
          <div
            style={{
              display: "flex",
              fontSize: "1.4em",
              fontWeight: 850,
              justifyContent: "space-between",
            }}
          >
            <span>{stringProp(graphic, "label", "Progress")}</span>
            <span>{Math.round(value)}%</span>
          </div>
          <div
            style={{
              background: "rgba(255,255,255,0.12)",
              borderRadius: TOKENS.radius.pill,
              height: 28,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                background: `linear-gradient(90deg, ${TOKENS.color.accent}, ${TOKENS.color.positive})`,
                borderRadius: TOKENS.radius.pill,
                height: "100%",
                width: `${value}%`,
              }}
            />
          </div>
        </Stack>
      );
    }
    case "PictureInPicture":
      return <LayoutMarker label={stringProp(graphic, "label")} mode="pip" />;
    case "FullscreenBroll":
      return (
        <LayoutMarker label={stringProp(graphic, "label")} mode="fullscreen" />
      );
    case "SplitScreen":
      return (
        <LayoutMarker label={stringProp(graphic, "leftLabel")} mode="split" />
      );
    case "KineticHeadline":
      return (
        <KineticHeadlineContent
          accent={stringProp(graphic, "accent")}
          eyebrow={stringProp(graphic, "eyebrow")}
          headline={stringProp(graphic, "headline", "Make it clear")}
        />
      );
    case "PriceComparison":
      return <PriceComparisonGraphic graphic={graphic} />;
    default:
      return <Title>Graphic unavailable</Title>;
  }
};

const GraphicCard: React.FC<{
  design: RenderInput["design"];
  graphic: Graphic;
}> = ({ design, graphic }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({
    config: { damping: 18, mass: 0.8, stiffness: 150 },
    fps,
    frame,
  });
  const lowerThird = graphic.component === "LowerThird";
  const screen =
    graphic.component === "BrowserWindow" ||
    graphic.component === "MobileScreenFrame";
  const full = [
    "EndCallToAction",
    "PictureInPicture",
    "FullscreenBroll",
    "SplitScreen",
    "KineticHeadline",
    "MobileScreenFrame",
    "PriceComparison",
  ].includes(graphic.component);
  const viralFocal =
    design.stylePreset === "viral-social" &&
    [
      "HookTitle",
      "KineticHeadline",
      "MobileScreenFrame",
      "PriceComparison",
    ].includes(graphic.component);
  return (
    <AbsoluteFill
      style={{
        alignItems: lowerThird ? "flex-start" : "center",
        justifyContent: lowerThird
          ? "flex-end"
          : full
            ? "center"
            : "flex-start",
        opacity: interpolate(progress, [0, 1], [0, 1]),
        padding: lowerThird ? "0 7% 22%" : full ? "9%" : "9% 7%",
        translate: `0 ${interpolate(progress, [0, 1], [28, 0])}px`,
      }}
    >
      <div
        style={{
          ...panelStyle(
            viralFocal ||
              graphic.component === "KineticHeadline" ||
              graphic.component === "PriceComparison"
              ? displayFont(design)
              : primaryFont(design),
          ),
          background: screen ? "rgba(7,13,27,0.72)" : TOKENS.color.panel,
          ...(viralFocal
            ? { background: "transparent", border: "none", boxShadow: "none" }
            : {}),
          fontSize: "clamp(15px, 2.6vw, 30px)",
          maxHeight: lowerThird ? "32%" : "78%",
          maxWidth: lowerThird ? "70%" : screen ? "92%" : "86%",
          overflow: "hidden",
          padding: screen ? "0.7em" : "1.25em 1.45em",
          width: screen ? "92%" : undefined,
        }}
      >
        <GraphicContent design={design} graphic={graphic} />
      </div>
    </AbsoluteFill>
  );
};

export const Graphics: React.FC<Pick<RenderInput, "design" | "scenes">> = ({
  design,
  scenes,
}) => {
  const { fps } = useVideoConfig();
  return scenes.flatMap((scene: Scene) =>
    scene.graphics.map((graphic) => {
      const from = frameAt(scene.start + graphic.startOffset, fps);
      const end = frameAt(scene.start + graphic.endOffset, fps);
      return (
        <Sequence
          key={graphic.id}
          from={from}
          durationInFrames={Math.max(1, end - from)}
          premountFor={fps}
        >
          <GraphicCard design={design} graphic={graphic} />
        </Sequence>
      );
    }),
  );
};
