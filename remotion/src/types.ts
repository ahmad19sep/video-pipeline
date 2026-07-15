export type CaptionPreset =
  | "roman-word-highlight"
  | "clean-two-line"
  | "hook"
  | "definition"
  | "question"
  | "urdu-script";

export type TimelineSegment = {
  id: string;
  sourceStart: number;
  sourceEnd: number;
  outputStart: number;
  outputEnd: number;
};

export type CaptionWord = {
  id: string;
  text: string;
  scriptText?: string;
  start: number;
  end: number;
  emphasis: boolean;
  confidence: number;
};

export type GraphicComponent =
  | "HookTitle"
  | "DefinitionCard"
  | "LowerThird"
  | "EndCallToAction"
  | "StepCard"
  | "ComparisonCard"
  | "ToolLogoRow"
  | "BrowserWindow"
  | "MobileScreenFrame"
  | "QuoteCard"
  | "StatisticCard"
  | "WarningCard"
  | "QuestionCard"
  | "TimelineGraphic"
  | "FeatureList"
  | "ProgressIndicator"
  | "PictureInPicture"
  | "FullscreenBroll"
  | "SplitScreen";

export type Graphic = {
  id: string;
  component: GraphicComponent;
  startOffset: number;
  endOffset: number;
  props: Record<string, string | number | boolean | string[]>;
};

export type ScreenPoint = { x: number; y: number };

export type ScreenTreatment = {
  frame: "browser" | "phone";
  cursor: ScreenPoint | null;
  clicks: Array<ScreenPoint & { offset: number }>;
  zoom:
    | (ScreenPoint & { startOffset: number; endOffset: number; scale: number })
    | null;
  labels: Array<ScreenPoint & { offset: number; text: string }>;
  sensitiveRegions: Array<
    ScreenPoint & { width: number; height: number; blur: number }
  >;
};

export type Scene = {
  id: string;
  start: number;
  end: number;
  layout:
    | "speaker-fullscreen"
    | "speaker-with-title"
    | "speaker-with-broll"
    | "fullscreen-broll"
    | "split-screen"
    | "browser-demo"
    | "mobile-demo"
    | "graphic-fullscreen"
    | "picture-in-picture";
  camera: {
    mode:
      | "static"
      | "punch-in"
      | "slow-zoom"
      | "reframe-left"
      | "reframe-right"
      | "return-wide"
      | "face-follow";
    scaleStart: number;
    scaleEnd: number;
    focus: "center" | "face" | "left" | "right" | "custom";
  };
  broll: {
    mode:
      | "none"
      | "overlay"
      | "fullscreen"
      | "split-screen"
      | "picture-in-picture";
    assetId: string | null;
    effect:
      | "static"
      | "kenburns-in"
      | "kenburns-out"
      | "slow-pan-left"
      | "slow-pan-right";
    fit: "cover" | "contain";
  };
  graphics: Graphic[];
  sfx: Array<{ assetId: string; offset: number; gainDb: number }>;
  transitionOut: {
    type:
      | "clean-cut"
      | "crossfade"
      | "directional-slide"
      | "blur"
      | "zoom"
      | "mask-reveal";
    durationFrames: number;
  };
  screenTreatment: ScreenTreatment | null;
};

export type FontDesign = {
  family: "Noto Naskh Arabic";
  path: "fonts/NotoNaskhArabic-Variable.ttf" | null;
  sha256:
    | "67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f"
    | null;
  license: "OFL-1.1" | null;
  fallback: "Arial, sans-serif";
};

export type RenderInput = {
  version: 2;
  projectId: string;
  videoSrc: string;
  video: {
    fps: number;
    width: number;
    height: number;
    durationInSeconds: number;
  };
  timelineSegments: TimelineSegment[];
  captions: {
    preset: CaptionPreset;
    language: "roman-urdu" | "urdu-script" | "english";
    safeZone:
      | "shorts-default"
      | "reels-default"
      | "tiktok-default"
      | "youtube-longform"
      | "custom";
    maxLines: number;
    wordsPerPage: { min: number; max: number };
    words: CaptionWord[];
  };
  scenes: Scene[];
  globalAudio: {
    voiceGainDb: number;
    musicAssetId: string | null;
    musicGainDb: number;
    duckingEnabled: boolean;
  };
  design: {
    stylePreset:
      | "modern-ai"
      | "minimal-professional"
      | "documentary"
      | "custom";
    colorPreset:
      | "off"
      | "natural-clean"
      | "modern-ai"
      | "soft-professional"
      | "high-contrast-social"
      | "cinematic-warm"
      | "cinematic-cool"
      | "documentary"
      | "low-light-recovery"
      | "custom";
    colorIntensity: number;
    font: FontDesign;
  };
  assets: Record<string, string>;
};
