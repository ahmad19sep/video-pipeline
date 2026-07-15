# Bundled Urdu font

`NotoNaskhArabic-Variable.ttf` is the Noto Naskh Arabic variable font from the
Google Fonts repository. It is redistributed under the SIL Open Font License
1.1 in `OFL-NotoNaskhArabic.txt`.

- Source: https://github.com/google/fonts/tree/main/ofl/notonaskharabic
- SHA-256: `67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f`
- Render family: `Noto Naskh Arabic`
- Fallback: `Arial, sans-serif`

The render-input builder uses this file only when its hash matches. If the file
is absent or changed, the renderer emits a null font reference and continues
with the fallback family.
