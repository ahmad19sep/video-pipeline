import type { CSSProperties } from "react";
import type { RenderInput } from "./types";

export const TOKENS = {
  color: {
    ink: "#f8fafc",
    muted: "#cbd5e1",
    panel: "rgba(7, 13, 27, 0.9)",
    panelSolid: "#07101f",
    accent: "#67e8f9",
    highlight: "#facc15",
    positive: "#86efac",
    danger: "#fda4af",
    warning: "#fdba74",
  },
  radius: { small: 12, medium: 20, large: 30, pill: 999 },
  shadow: {
    panel: "0 18px 54px rgba(0, 0, 0, 0.42)",
    text: "0 3px 12px rgba(0, 0, 0, 0.92)",
  },
  spacing: { xs: 8, sm: 14, md: 22, lg: 34, xl: 54 },
  timing: { fast: 0.16, standard: 0.28, slow: 0.5 },
  type: {
    body: 0.032,
    captionLandscape: 0.052,
    captionPortrait: 0.065,
    display: 0.09,
    title: 0.065,
  },
} as const;

export const primaryFont = (design: RenderInput["design"]) =>
  design.font.path
    ? `"${design.font.family}", ${design.font.fallback}`
    : design.font.fallback;

export const safeInsets = (
  safeZone: RenderInput["captions"]["safeZone"],
  portrait: boolean,
) => {
  if (!portrait || safeZone === "youtube-longform") {
    return { bottom: "7.5%", horizontal: "7%", top: "6%" };
  }
  if (safeZone === "tiktok-default") {
    return { bottom: "17%", horizontal: "9%", top: "11%" };
  }
  if (safeZone === "reels-default") {
    return { bottom: "14%", horizontal: "8%", top: "10%" };
  }
  return { bottom: "13%", horizontal: "7.5%", top: "9%" };
};

export const presentationStyle = (
  design: RenderInput["design"],
  isScreen: boolean,
): CSSProperties => {
  if (isScreen || design.colorPreset === "off" || design.colorIntensity === 0) {
    return {};
  }
  const amount = Math.min(0.5, design.colorIntensity);
  switch (design.colorPreset) {
    case "cinematic-warm":
      return {
        filter: `sepia(${amount * 0.12}) saturate(${1 + amount * 0.1}) contrast(${1 + amount * 0.06})`,
      };
    case "cinematic-cool":
      return {
        filter: `hue-rotate(${-amount * 7}deg) saturate(${1 - amount * 0.04}) contrast(${1 + amount * 0.06})`,
      };
    case "documentary":
      return {
        filter: `saturate(${1 - amount * 0.12}) contrast(${1 + amount * 0.1})`,
      };
    case "low-light-recovery":
      return {
        filter: `brightness(${1 + amount * 0.08}) contrast(${1 - amount * 0.04})`,
      };
    case "high-contrast-social":
      return {
        filter: `contrast(${1 + amount * 0.14}) saturate(${1 + amount * 0.08})`,
      };
    case "soft-professional":
      return {
        filter: `contrast(${1 - amount * 0.04}) saturate(${1 - amount * 0.04})`,
      };
    case "modern-ai":
      return {
        filter: `contrast(${1 + amount * 0.06}) saturate(${1 + amount * 0.07})`,
      };
    default:
      return {};
  }
};

export const panelStyle = (fontFamily: string): CSSProperties => ({
  background: TOKENS.color.panel,
  border: `2px solid ${TOKENS.color.accent}88`,
  borderRadius: TOKENS.radius.large,
  boxShadow: TOKENS.shadow.panel,
  color: TOKENS.color.ink,
  fontFamily,
});
