import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { CSSProperties, ReactNode } from "react";
import { TOKENS, panelStyle, primaryFont } from "./design-tokens";
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

const MobileChrome: React.FC<{ children: ReactNode; title: string }> = ({
  children,
  title,
}) => (
  <div
    style={{
      background: "#f8fafc",
      border: "10px solid #111827",
      borderRadius: 44,
      color: "#0f172a",
      maxHeight: "100%",
      padding: "1.2em 1em",
      width: "44%",
    }}
  >
    <div
      style={{
        background: "#111827",
        borderRadius: TOKENS.radius.pill,
        height: 8,
        margin: "0 auto 1.1em",
        width: "28%",
      }}
    />
    <Stack>
      <Title>{title}</Title>
      {children}
    </Stack>
  </div>
);

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

const GraphicContent: React.FC<{ graphic: Graphic }> = ({ graphic }) => {
  switch (graphic.component) {
    case "HookTitle":
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
          <MobileChrome title={stringProp(graphic, "title", "Mobile demo")}>
            <List items={listProp(graphic, "steps")} ordered />
          </MobileChrome>
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
          ...panelStyle(primaryFont(design)),
          background: screen ? "rgba(7,13,27,0.72)" : TOKENS.color.panel,
          fontSize: "clamp(15px, 2.6vw, 30px)",
          maxHeight: lowerThird ? "32%" : "78%",
          maxWidth: lowerThird ? "70%" : screen ? "92%" : "86%",
          overflow: "hidden",
          padding: screen ? "0.7em" : "1.25em 1.45em",
          width: screen ? "92%" : undefined,
        }}
      >
        <GraphicContent graphic={graphic} />
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
