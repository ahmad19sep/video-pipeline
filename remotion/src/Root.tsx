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
    preset: "clean-two-line",
    language: "roman-urdu",
    safeZone: "shorts-default",
    maxLines: 2,
    wordsPerPage: { min: 2, max: 5 },
    words: [
      {
        id: "word_000001",
        text: "Typed",
        start: 0,
        end: 0.28,
        emphasis: true,
        confidence: 1,
      },
      {
        id: "word_000002",
        text: "local",
        start: 0.28,
        end: 0.52,
        emphasis: false,
        confidence: 1,
      },
      {
        id: "word_000003",
        text: "and",
        start: 0.52,
        end: 0.68,
        emphasis: false,
        confidence: 1,
      },
      {
        id: "word_000004",
        text: "deterministic",
        start: 0.68,
        end: 1,
        emphasis: true,
        confidence: 1,
      },
    ],
  },
  scenes: [
    {
      id: "scene_000001",
      start: 0,
      end: 1,
      layout: "graphic-fullscreen",
      camera: { mode: "static", scaleStart: 1, scaleEnd: 1, focus: "face" },
      broll: { mode: "none", assetId: null, effect: "static", fit: "cover" },
      graphics: [
        {
          id: "graphic_000001",
          component: "HookTitle",
          startOffset: 0,
          endOffset: 1,
          props: {
            title: "CutMachine",
            subtitle: "Phase 10 design system",
          },
        },
      ],
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
