import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { CSSProperties, ReactNode } from "react";
import { TOKENS, primaryFont } from "./design-tokens";
import type { RenderInput, Scene, ScreenPoint, ScreenTreatment } from "./types";

const frameAt = (seconds: number, fps: number) => Math.round(seconds * fps);

export const screenZoomStyle = (
  scene: Scene,
  localSeconds: number,
): CSSProperties => {
  const zoom = scene.screenTreatment?.zoom;
  if (!zoom) return {};
  const ramp = Math.min(0.18, (zoom.endOffset - zoom.startOffset) / 3);
  const scale = interpolate(
    localSeconds,
    [
      zoom.startOffset,
      zoom.startOffset + ramp,
      zoom.endOffset - ramp,
      zoom.endOffset,
    ],
    [1, zoom.scale, zoom.scale, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return {
    scale: `${scale}`,
    transformOrigin: `${zoom.x * 100}% ${zoom.y * 100}%`,
  };
};

const ScreenFrame: React.FC<{
  children: ReactNode;
  frame: ScreenTreatment["frame"];
}> = ({ children, frame }) => {
  const phone = frame === "phone";
  return (
    <div
      style={{
        background: "rgba(248,250,252,0.08)",
        border: phone ? "9px solid #e2e8f0" : "4px solid #cbd5e1",
        borderRadius: phone ? 42 : TOKENS.radius.medium,
        bottom: "22%",
        boxShadow: TOKENS.shadow.panel,
        left: phone ? "20%" : "5%",
        overflow: "hidden",
        position: "absolute",
        right: phone ? "20%" : "5%",
        top: phone ? "5%" : "7%",
      }}
    >
      {phone ? (
        <div
          style={{
            background: "#e2e8f0",
            borderRadius: TOKENS.radius.pill,
            height: 7,
            left: "40%",
            position: "absolute",
            right: "40%",
            top: 8,
            zIndex: 4,
          }}
        />
      ) : (
        <div
          style={{
            alignItems: "center",
            background: "#cbd5e1",
            display: "flex",
            gap: 8,
            height: "7%",
            minHeight: 26,
            padding: "0 0.7em",
          }}
        >
          <span style={{ color: "#ef4444" }}>●</span>
          <span style={{ color: "#eab308" }}>●</span>
          <span style={{ color: "#22c55e" }}>●</span>
          <div
            style={{
              background: "#f8fafc",
              borderRadius: TOKENS.radius.pill,
              height: "48%",
              marginLeft: 8,
              width: "62%",
            }}
          />
        </div>
      )}
      <div
        style={{
          bottom: 0,
          left: 0,
          overflow: "hidden",
          position: "absolute",
          right: 0,
          top: phone ? "4%" : "7%",
        }}
      >
        {children}
      </div>
    </div>
  );
};

const AtPoint: React.FC<{ children: ReactNode; point: ScreenPoint }> = ({
  children,
  point,
}) => (
  <div
    style={{
      left: `${point.x * 100}%`,
      position: "absolute",
      top: `${point.y * 100}%`,
    }}
  >
    {children}
  </div>
);

const ClickRipple: React.FC<{ point: ScreenPoint }> = ({ point }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(1, fps * 0.45)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AtPoint point={point}>
      <div
        style={{
          border: `4px solid ${TOKENS.color.accent}`,
          borderRadius: "50%",
          height: interpolate(progress, [0, 1], [18, 86]),
          opacity: interpolate(progress, [0, 1], [0.95, 0]),
          translate: "-50% -50%",
          width: interpolate(progress, [0, 1], [18, 86]),
        }}
      />
    </AtPoint>
  );
};

const Cursor: React.FC<{ point: ScreenPoint }> = ({ point }) => (
  <AtPoint point={point}>
    <div
      style={{
        filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.8))",
        fontSize: 34,
        lineHeight: 1,
        translate: "-15% -10%",
      }}
    >
      ➤
    </div>
  </AtPoint>
);

const TreatmentContents: React.FC<{
  design: RenderInput["design"];
  scene: Scene;
}> = ({ design, scene }) => {
  const { fps } = useVideoConfig();
  const treatment = scene.screenTreatment;
  if (!treatment) return null;
  const durationFrames = frameAt(scene.end - scene.start, fps);
  return (
    <>
      {treatment.sensitiveRegions.map((region, index) => (
        <div
          key={`sensitive-${index}`}
          style={{
            backdropFilter: `blur(${region.blur}px)`,
            background: "rgba(15,23,42,0.45)",
            border: "1px solid rgba(255,255,255,0.3)",
            height: `${region.height * 100}%`,
            left: `${region.x * 100}%`,
            position: "absolute",
            top: `${region.y * 100}%`,
            width: `${region.width * 100}%`,
          }}
        />
      ))}
      {treatment.cursor ? <Cursor point={treatment.cursor} /> : null}
      {treatment.clicks.map((click, index) => {
        const from = frameAt(click.offset, fps);
        return (
          <Sequence
            key={`click-${index}`}
            from={from}
            durationInFrames={Math.min(
              frameAt(0.5, fps),
              Math.max(1, durationFrames - from),
            )}
          >
            <ClickRipple point={click} />
          </Sequence>
        );
      })}
      {treatment.labels.map((label, index) => {
        const from = frameAt(label.offset, fps);
        return (
          <Sequence
            key={`label-${index}`}
            from={from}
            durationInFrames={Math.max(1, durationFrames - from)}
          >
            <AtPoint point={label}>
              <div
                style={{
                  background: TOKENS.color.panelSolid,
                  border: `2px solid ${TOKENS.color.accent}`,
                  borderRadius: TOKENS.radius.pill,
                  boxShadow: TOKENS.shadow.panel,
                  fontFamily: primaryFont(design),
                  fontSize: "clamp(13px, 2vw, 24px)",
                  fontWeight: 850,
                  maxWidth: 280,
                  padding: "0.42em 0.72em",
                  translate: "-50% -120%",
                }}
              >
                {index + 1}. {label.text}
              </div>
            </AtPoint>
          </Sequence>
        );
      })}
    </>
  );
};

const ZoomTrackedContents: React.FC<{
  design: RenderInput["design"];
  scene: Scene;
}> = ({ design, scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Mirror the zoom applied to the underlying content in CameraLayer so
  // cursor, click, label, and blur annotations stay glued to what they mark.
  const zoom = screenZoomStyle(scene, frame / fps);
  return (
    <div
      style={{
        bottom: 0,
        left: 0,
        position: "absolute",
        right: 0,
        scale: zoom.scale,
        top: 0,
        transformOrigin: zoom.transformOrigin,
      }}
    >
      <TreatmentContents design={design} scene={scene} />
    </div>
  );
};

export const ScreenTreatments: React.FC<
  Pick<RenderInput, "design" | "scenes">
> = ({ design, scenes }) => {
  const { fps } = useVideoConfig();
  return scenes.map((scene) => {
    if (!scene.screenTreatment) return null;
    const from = frameAt(scene.start, fps);
    const end = frameAt(scene.end, fps);
    return (
      <Sequence
        key={`screen-${scene.id}`}
        from={from}
        durationInFrames={Math.max(1, end - from)}
        premountFor={fps}
      >
        <AbsoluteFill style={{ pointerEvents: "none" }}>
          <ScreenFrame frame={scene.screenTreatment.frame}>
            <ZoomTrackedContents design={design} scene={scene} />
          </ScreenFrame>
        </AbsoluteFill>
      </Sequence>
    );
  });
};
