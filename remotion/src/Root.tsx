import "./index.css";
import { Composition, type CalculateMetadataFunction } from "remotion";
import { CutMachineDraft } from "./Composition";
import type { RenderInput } from "./types";
import { validateRenderInput } from "./validate";

const defaultProps: RenderInput = {
  version: 2,
  projectId: "preview",
  videoSrc: "cutmachine/preview/proxy.mp4",
  video: { fps: 30, width: 540, height: 960, durationInSeconds: 1 },
  timelineSegments: [
    {
      id: "keep_000001",
      sourceStart: 0,
      sourceEnd: 1,
      outputStart: 0,
      outputEnd: 1,
    },
  ],
  captions: {
    preset: "roman-word-highlight",
    language: "roman-urdu",
    safeZone: "shorts-default",
    maxLines: 2,
    wordsPerPage: { min: 2, max: 5 },
    words: [],
  },
  scenes: [
    {
      id: "scene_000001",
      start: 0,
      end: 1,
      layout: "speaker-fullscreen",
      camera: { mode: "static", scaleStart: 1, scaleEnd: 1, focus: "face" },
      broll: { mode: "none", assetId: null, effect: "static", fit: "cover" },
      graphics: [],
      sfx: [],
      transitionOut: { type: "clean-cut", durationFrames: 0 },
      screenTreatment: null,
    },
  ],
  globalAudio: {
    voiceGainDb: 0,
    musicAssetId: null,
    musicGainDb: -24,
    duckingEnabled: true,
  },
  design: {
    stylePreset: "minimal-professional",
    colorPreset: "natural-clean",
    colorIntensity: 0.5,
    font: {
      family: "Noto Naskh Arabic",
      path: null,
      sha256: null,
      license: null,
      fallback: "Arial, sans-serif",
    },
  },
  assets: {},
};

const calculateMetadata: CalculateMetadataFunction<RenderInput> = ({
  props,
}) => {
  const valid = validateRenderInput(props);
  return {
    durationInFrames: Math.max(
      1,
      Math.ceil(valid.video.durationInSeconds * valid.video.fps),
    ),
    fps: valid.video.fps,
    width: valid.video.width,
    height: valid.video.height,
    props: valid,
  };
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="CutMachineDraft"
    component={CutMachineDraft}
    defaultProps={defaultProps}
    durationInFrames={30}
    fps={30}
    width={540}
    height={960}
    calculateMetadata={calculateMetadata}
  />
);
