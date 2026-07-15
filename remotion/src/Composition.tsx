import { Audio, Video } from "@remotion/media";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { CSSProperties, ReactNode } from "react";
import { Captions, DesignFontLoader } from "./Captions";
import { Graphics } from "./Graphics";
import { ScreenTreatments, screenZoomStyle } from "./ScreenTreatments";
import { TransitionOverlays } from "./Transitions";
import { presentationStyle } from "./design-tokens";
import type { CaptionWord, RenderInput, Scene } from "./types";

const frameAt = (seconds: number, fps: number) => Math.round(seconds * fps);
const dbToVolume = (db: number) => 10 ** (db / 20);

const SpeakerTrack: React.FC<
  Pick<RenderInput, "videoSrc" | "timelineSegments" | "globalAudio">
> = ({ videoSrc, timelineSegments, globalAudio }) => {
  const { fps } = useVideoConfig();
  return timelineSegments.map((segment) => {
    const from = frameAt(segment.outputStart, fps);
    const end = frameAt(segment.outputEnd, fps);
    return (
      <Sequence
        key={segment.id}
        from={from}
        durationInFrames={Math.max(1, end - from)}
        premountFor={fps}
      >
        <Video
          src={staticFile(videoSrc)}
          trimBefore={frameAt(segment.sourceStart, fps)}
          trimAfter={frameAt(segment.sourceEnd, fps)}
          volume={() => dbToVolume(globalAudio.voiceGainDb)}
          objectFit="cover"
          style={{ height: "100%", width: "100%" }}
        />
      </Sequence>
    );
  });
};

const CameraLayer: React.FC<{
  children: ReactNode;
  design: RenderInput["design"];
  scenes: Scene[];
}> = ({ children, design, scenes }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seconds = frame / fps;
  const scene = scenes.find(
    (item) => seconds >= item.start && seconds < item.end,
  );
  const progress = scene
    ? interpolate(seconds, [scene.start, scene.end], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;
  const cameraScale = scene
    ? interpolate(
        progress,
        [0, 1],
        [scene.camera.scaleStart, scene.camera.scaleEnd],
      )
    : 1;
  const x =
    scene?.camera.focus === "left"
      ? "3%"
      : scene?.camera.focus === "right"
        ? "-3%"
        : "0%";
  const screen =
    scene?.layout === "browser-demo" || scene?.layout === "mobile-demo";
  const zoom = scene ? screenZoomStyle(scene, seconds - scene.start) : {};
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          ...presentationStyle(design, screen),
          scale: zoom.scale ?? `${cameraScale}`,
          transformOrigin: zoom.transformOrigin,
          translate: `${x} 0`,
        }}
      >
        {children}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const isImage = (path: string) => /\.(avif|gif|jpe?g|png|webp)$/i.test(path);

const BrollMedia: React.FC<{
  design: RenderInput["design"];
  path: string;
  scene: Scene;
}> = ({ design, path, scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = Math.max(1, frameAt(scene.end - scene.start, fps));
  const progress = interpolate(frame, [0, duration - 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const effectScale =
    scene.broll.effect === "kenburns-in"
      ? interpolate(progress, [0, 1], [1, 1.08])
      : scene.broll.effect === "kenburns-out"
        ? interpolate(progress, [0, 1], [1.08, 1])
        : 1;
  const effectX =
    scene.broll.effect === "slow-pan-left"
      ? interpolate(progress, [0, 1], ["3%", "-3%"])
      : scene.broll.effect === "slow-pan-right"
        ? interpolate(progress, [0, 1], ["-3%", "3%"])
        : "0%";
  const screen =
    scene.layout === "browser-demo" || scene.layout === "mobile-demo";
  const zoom = screenZoomStyle(scene, frame / fps);
  const mediaStyle: CSSProperties = {
    ...presentationStyle(design, screen),
    height: "100%",
    objectFit: scene.broll.fit,
    scale: zoom.scale ?? `${effectScale}`,
    transformOrigin: zoom.transformOrigin,
    translate: `${effectX} 0`,
    width: "100%",
  };
  return isImage(path) ? (
    <Img src={staticFile(path)} style={mediaStyle} />
  ) : (
    <Video
      muted
      src={staticFile(path)}
      objectFit={scene.broll.fit}
      style={mediaStyle}
    />
  );
};

const Broll: React.FC<Pick<RenderInput, "assets" | "design" | "scenes">> = ({
  assets,
  design,
  scenes,
}) => {
  const { fps } = useVideoConfig();
  return scenes.map((scene) => {
    const path = scene.broll.assetId ? assets[scene.broll.assetId] : undefined;
    if (!path || scene.broll.mode === "none") return null;
    const from = frameAt(scene.start, fps);
    const end = frameAt(scene.end, fps);
    const layerStyle: CSSProperties =
      scene.broll.mode === "picture-in-picture"
        ? {
            border: "3px solid white",
            borderRadius: 20,
            boxShadow: "0 16px 42px rgba(0,0,0,0.45)",
            height: "28%",
            overflow: "hidden",
            position: "absolute",
            right: "7%",
            top: "8%",
            width: "38%",
          }
        : scene.broll.mode === "split-screen"
          ? { height: "50%", overflow: "hidden", top: "50%" }
          : scene.broll.mode === "overlay"
            ? { height: "100%", opacity: 0.82, width: "100%" }
            : { height: "100%", overflow: "hidden", width: "100%" };
    return (
      <Sequence
        key={`broll-${scene.id}`}
        from={from}
        durationInFrames={Math.max(1, end - from)}
        premountFor={fps}
      >
        <div style={layerStyle}>
          <BrollMedia design={design} path={path} scene={scene} />
        </div>
      </Sequence>
    );
  });
};

const musicVolume = (
  frame: number,
  fps: number,
  words: CaptionWord[],
  gainDb: number,
  duckingEnabled: boolean,
) => {
  if (!duckingEnabled || words.length === 0) return dbToVolume(gainDb);
  const time = frame / fps;
  const distance = Math.min(
    ...words.map((word) => {
      const start = word.start - 0.08;
      const end = word.end + 0.12;
      if (time >= start && time <= end) return 0;
      return Math.min(Math.abs(time - start), Math.abs(time - end));
    }),
  );
  const duckDb = interpolate(distance, [0, 0.15], [-6, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return dbToVolume(gainDb + duckDb);
};

const AudioLayers: React.FC<
  Pick<RenderInput, "scenes" | "assets" | "globalAudio" | "captions">
> = ({ scenes, assets, globalAudio, captions }) => {
  const { fps } = useVideoConfig();
  const music = globalAudio.musicAssetId
    ? assets[globalAudio.musicAssetId]
    : undefined;
  return (
    <>
      {music ? (
        <Audio
          loop
          loopVolumeCurveBehavior="extend"
          src={staticFile(music)}
          volume={(frame) =>
            musicVolume(
              frame,
              fps,
              captions.words,
              globalAudio.musicGainDb,
              globalAudio.duckingEnabled,
            )
          }
        />
      ) : null}
      {scenes.flatMap((scene) =>
        scene.sfx.map((sfx, index) => {
          const path = assets[sfx.assetId];
          if (!path) return null;
          return (
            <Sequence
              key={`${scene.id}-sfx-${index}`}
              from={frameAt(scene.start + sfx.offset, fps)}
              premountFor={fps}
            >
              <Audio
                src={staticFile(path)}
                volume={() => dbToVolume(sfx.gainDb)}
              />
            </Sequence>
          );
        }),
      )}
    </>
  );
};

export const CutMachineDraft: React.FC<RenderInput> = (input) => (
  <AbsoluteFill
    style={{
      backgroundColor: "#050811",
      color: "white",
      fontSize: 16,
      overflow: "hidden",
    }}
  >
    <DesignFontLoader font={input.design.font} />
    <CameraLayer design={input.design} scenes={input.scenes}>
      <SpeakerTrack
        videoSrc={input.videoSrc}
        timelineSegments={input.timelineSegments}
        globalAudio={input.globalAudio}
      />
    </CameraLayer>
    <Broll assets={input.assets} design={input.design} scenes={input.scenes} />
    <ScreenTreatments design={input.design} scenes={input.scenes} />
    <Graphics design={input.design} scenes={input.scenes} />
    <Captions captions={input.captions} design={input.design} />
    <TransitionOverlays scenes={input.scenes} />
    <AudioLayers
      scenes={input.scenes}
      assets={input.assets}
      globalAudio={input.globalAudio}
      captions={input.captions}
    />
  </AbsoluteFill>
);
