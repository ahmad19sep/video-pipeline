import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { TOKENS } from "./design-tokens";
import type { Scene } from "./types";

const frameAt = (seconds: number, fps: number) => Math.round(seconds * fps);

const TransitionOverlay: React.FC<{
  duration: number;
  type: Scene["transitionOut"]["type"];
}> = ({ duration, type }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, Math.max(1, duration - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (type === "crossfade") {
    return (
      <AbsoluteFill
        style={{ background: "#050811", opacity: progress * 0.45 }}
      />
    );
  }
  if (type === "directional-slide") {
    return (
      <AbsoluteFill
        style={{
          background: `linear-gradient(90deg, transparent, ${TOKENS.color.panelSolid})`,
          translate: `${interpolate(progress, [0, 1], ["100%", "0%"])} 0`,
        }}
      />
    );
  }
  if (type === "blur") {
    return (
      <AbsoluteFill
        style={{
          backdropFilter: `blur(${progress * 18}px)`,
          background: `rgba(5,8,17,${progress * 0.28})`,
        }}
      />
    );
  }
  if (type === "zoom") {
    return (
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle, transparent 18%, rgba(5,8,17,0.78) 100%)",
          opacity: progress,
          scale: `${interpolate(progress, [0, 1], [1.35, 0.72])}`,
        }}
      />
    );
  }
  if (type === "mask-reveal") {
    return (
      <AbsoluteFill
        style={{
          background: TOKENS.color.panelSolid,
          clipPath: `circle(${interpolate(progress, [0, 1], [0, 78])}% at 50% 50%)`,
          opacity: 0.75,
        }}
      />
    );
  }
  return null;
};

export const TransitionOverlays: React.FC<{ scenes: Scene[] }> = ({
  scenes,
}) => {
  const { fps } = useVideoConfig();
  return scenes.map((scene) => {
    const duration = scene.transitionOut.durationFrames;
    if (duration <= 0 || scene.transitionOut.type === "clean-cut") return null;
    const end = frameAt(scene.end, fps);
    return (
      <Sequence
        key={`transition-${scene.id}`}
        from={Math.max(0, end - duration)}
        durationInFrames={duration}
      >
        <TransitionOverlay
          duration={duration}
          type={scene.transitionOut.type}
        />
      </Sequence>
    );
  });
};
