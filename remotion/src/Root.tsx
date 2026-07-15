import "./index.css";
import { Composition, type CalculateMetadataFunction } from "remotion";
import { CutMachineDraft } from "./Composition";
import type { RenderInput } from "./types";
import { validateRenderInput } from "./validate";

const defaultProps: RenderInput = {
  version: 2,
  projectId: "preview",
  videoSrc: "cutmachine/preview/proxy.mp4",
  video: { fps: 30, width: 540, height: 960, durationInSeconds: 3 },
  timelineSegments: [
    {
      id: "keep_000001",
      sourceStart: 0,
      sourceEnd: 3,
      outputStart: 0,
      outputEnd: 3,
    },
  ],
  captions: {
    preset: "viral-punch",
    language: "roman-urdu",
    safeZone: "shorts-default",
    maxLines: 2,
    wordsPerPage: { min: 2, max: 5 },
    words: [
      {
        id: "word_000001",
        text: "Typed",
        start: 0,
        end: 0.35,
        emphasis: true,
        confidence: 1,
      },
      {
        id: "word_000002",
        text: "local",
        start: 0.35,
        end: 0.7,
        emphasis: false,
        confidence: 1,
      },
      {
        id: "word_000003",
        text: "and",
        start: 0.7,
        end: 1,
        emphasis: false,
        confidence: 1,
      },
      {
        id: "word_000004",
        text: "deterministic",
        start: 1,
        end: 1.5,
        emphasis: true,
        confidence: 1,
      },
      {
        id: "word_000005",
        text: "compare",
        start: 1.5,
        end: 2,
        emphasis: false,
        confidence: 1,
      },
      {
        id: "word_000006",
        text: "every",
        start: 2,
        end: 2.45,
        emphasis: false,
        confidence: 1,
      },
      {
        id: "word_000007",
        text: "deal",
        start: 2.45,
        end: 3,
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
            title: "Make every second count",
            subtitle: "Viral social",
          },
        },
      ],
      sfx: [],
      transitionOut: { type: "clean-cut", durationFrames: 0 },
      screenTreatment: null,
    },
    {
      id: "scene_000002",
      start: 1,
      end: 2,
      layout: "graphic-fullscreen",
      camera: { mode: "static", scaleStart: 1, scaleEnd: 1, focus: "center" },
      broll: { mode: "none", assetId: null, effect: "static", fit: "cover" },
      graphics: [
        {
          id: "graphic_000002",
          component: "MobileScreenFrame",
          startOffset: 0,
          endOffset: 1,
          props: {
            title: "best editing style",
            steps: ["viral captions", "clean motion", "strong contrast"],
          },
        },
      ],
      sfx: [],
      transitionOut: { type: "clean-cut", durationFrames: 0 },
      screenTreatment: null,
    },
    {
      id: "scene_000003",
      start: 2,
      end: 3,
      layout: "graphic-fullscreen",
      camera: { mode: "static", scaleStart: 1, scaleEnd: 1, focus: "center" },
      broll: { mode: "none", assetId: null, effect: "static", fit: "cover" },
      graphics: [
        {
          id: "graphic_000003",
          component: "PriceComparison",
          startOffset: 0,
          endOffset: 1,
          props: { lowValue: "$1", highValue: "$10K", label: "VALUE" },
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
    stylePreset: "viral-social",
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
    durationInFrames={90}
    fps={30}
    width={540}
    height={960}
    calculateMetadata={calculateMetadata}
  />
);
