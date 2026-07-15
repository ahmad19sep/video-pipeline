import type { GraphicComponent, RenderInput } from "./types";

const GRAPHICS = new Set<GraphicComponent>([
  "HookTitle",
  "DefinitionCard",
  "LowerThird",
  "EndCallToAction",
  "StepCard",
  "ComparisonCard",
  "ToolLogoRow",
  "BrowserWindow",
  "MobileScreenFrame",
  "QuoteCard",
  "StatisticCard",
  "WarningCard",
  "QuestionCard",
  "TimelineGraphic",
  "FeatureList",
  "ProgressIndicator",
  "PictureInPicture",
  "FullscreenBroll",
  "SplitScreen",
]);

const TRANSITIONS = new Set([
  "clean-cut",
  "crossfade",
  "directional-slide",
  "blur",
  "zoom",
  "mask-reveal",
]);

const finite = (value: number, label: string) => {
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be finite`);
  }
};

const safeRelative = (path: string) =>
  !/^(?:[A-Za-z]:|[\\/~])/.test(path) && !/(^|[\\/])\.\.([\\/]|$)/.test(path);

const normalized = (value: number) =>
  Number.isFinite(value) && value >= 0 && value <= 1;

export const validateRenderInput = (input: RenderInput): RenderInput => {
  if (input.version !== 2) throw new Error("Unsupported render-input version");
  if (!/^[A-Za-z0-9_-]+$/.test(input.projectId))
    throw new Error("Invalid projectId");
  if (!safeRelative(input.videoSrc)) {
    throw new Error("videoSrc must be a safe relative public path");
  }
  const { fps, width, height, durationInSeconds } = input.video;
  [fps, width, height, durationInSeconds].forEach((value, index) =>
    finite(value, ["fps", "width", "height", "duration"][index]),
  );
  if (fps <= 0 || width < 240 || height < 240 || durationInSeconds <= 0) {
    throw new Error("Invalid video metadata");
  }
  if (input.design.colorIntensity < 0 || input.design.colorIntensity > 0.5) {
    throw new Error("Color intensity exceeds the conservative design limit");
  }
  const font = input.design.font;
  if (
    font.path !== null &&
    font.path !== "fonts/NotoNaskhArabic-Variable.ttf"
  ) {
    throw new Error("Unapproved font path");
  }
  if (
    (font.path === null && (font.sha256 !== null || font.license !== null)) ||
    (font.path !== null && (font.sha256 === null || font.license !== "OFL-1.1"))
  ) {
    throw new Error("Font evidence is inconsistent");
  }
  if (
    (input.captions.preset === "urdu-script") !==
    (input.captions.language === "urdu-script")
  ) {
    throw new Error("Urdu caption preset and language must match");
  }
  let outputCursor = 0;
  for (const segment of input.timelineSegments) {
    if (
      segment.sourceStart < 0 ||
      segment.sourceEnd <= segment.sourceStart ||
      Math.abs(segment.outputStart - outputCursor) > 0.002 ||
      segment.outputEnd <= segment.outputStart
    ) {
      throw new Error(`Invalid timeline segment ${segment.id}`);
    }
    outputCursor = segment.outputEnd;
  }
  if (Math.abs(outputCursor - durationInSeconds) > 0.002) {
    throw new Error("Timeline does not cover the declared duration");
  }
  for (const word of input.captions.words) {
    if (
      word.start < 0 ||
      word.end <= word.start ||
      word.end > durationInSeconds + 0.002
    ) {
      throw new Error(`Invalid caption word ${word.id}`);
    }
    if (input.captions.preset === "urdu-script" && !word.scriptText?.trim()) {
      throw new Error(`Urdu caption word ${word.id} lacks script text`);
    }
  }
  const graphicIds = new Set<string>();
  let sceneCursor = 0;
  input.scenes.forEach((scene, sceneIndex) => {
    if (
      scene.start < 0 ||
      Math.abs(scene.start - sceneCursor) > 0.002 ||
      scene.end <= scene.start ||
      scene.end > durationInSeconds + 0.002
    ) {
      throw new Error(`Invalid scene ${scene.id}`);
    }
    const sceneDuration = scene.end - scene.start;
    for (const graphic of scene.graphics) {
      if (
        !GRAPHICS.has(graphic.component) ||
        graphicIds.has(graphic.id) ||
        graphic.startOffset < 0 ||
        graphic.endOffset <= graphic.startOffset ||
        graphic.endOffset > sceneDuration + 0.002
      ) {
        throw new Error(`Invalid graphic ${graphic.id}`);
      }
      graphicIds.add(graphic.id);
    }
    const transition = scene.transitionOut;
    if (
      !TRANSITIONS.has(transition.type) ||
      (transition.type === "clean-cut") !== (transition.durationFrames === 0) ||
      (sceneIndex === input.scenes.length - 1 &&
        transition.type !== "clean-cut")
    ) {
      throw new Error(`Invalid transition on ${scene.id}`);
    }
    const treatment = scene.screenTreatment;
    if (treatment) {
      const screenLayout =
        scene.layout === "browser-demo" || scene.layout === "mobile-demo";
      const expectedFrame =
        scene.layout === "browser-demo" ? "browser" : "phone";
      if (!screenLayout || treatment.frame !== expectedFrame) {
        throw new Error(`Invalid screen treatment on ${scene.id}`);
      }
      const points = [
        ...(treatment.cursor ? [treatment.cursor] : []),
        ...treatment.clicks,
        ...treatment.labels,
      ];
      if (
        points.some((point) => !normalized(point.x) || !normalized(point.y))
      ) {
        throw new Error(`Unbounded screen point on ${scene.id}`);
      }
      if (
        treatment.clicks.some(
          (click) => click.offset < 0 || click.offset >= sceneDuration,
        ) ||
        treatment.labels.some(
          (label) => label.offset < 0 || label.offset >= sceneDuration,
        )
      ) {
        throw new Error(`Screen event exceeds ${scene.id}`);
      }
      if (
        treatment.sensitiveRegions.some(
          (region) =>
            !normalized(region.x) ||
            !normalized(region.y) ||
            region.width <= 0 ||
            region.height <= 0 ||
            region.x + region.width > 1 ||
            region.y + region.height > 1,
        )
      ) {
        throw new Error(`Invalid privacy region on ${scene.id}`);
      }
    }
    sceneCursor = scene.end;
  });
  if (Math.abs(sceneCursor - durationInSeconds) > 0.002) {
    throw new Error("Scenes do not cover the declared duration");
  }
  for (const path of Object.values(input.assets)) {
    if (!safeRelative(path))
      throw new Error("Asset paths must be safe relative public paths");
  }
  return input;
};
