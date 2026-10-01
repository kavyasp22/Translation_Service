/**
 * Script-aware token and text stat calculator.
 * Handles space-separated languages (English, Latin, Arabic, Urdu)
 * as well as complex Indic scripts (Devanagari, Bengali, Tamil, Telugu, etc.)
 * and non-spaced CJK scripts (Chinese, Japanese, Korean, Thai).
 */
export function countTokensAndStats(text) {
  if (!text || !text.trim()) {
    return { tokens: 0, words: 0, chars: 0 };
  }

  const trimmed = text.trim();
  const chars = trimmed.length;

  // Regex patterns for script detection
  const cjkRegex = /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f\u1780-\u17ff\u1000-\u109f]/g;
  const indicRegex = /[\u0900-\u0d7f]/g;

  const cjkMatches = trimmed.match(cjkRegex) || [];
  const indicMatches = trimmed.match(indicRegex) || [];

  const cjkCharCount = cjkMatches.length;
  const indicCharCount = indicMatches.length;
  const letterCount = (trimmed.match(/\p{L}/gu) || []).length;

  let words = 0;
  let tokens = 0;

  // Case 1: Non-space-delimited scripts (Chinese, Japanese, Korean, Thai, Khmer, Myanmar)
  if (cjkCharCount > 0 && cjkCharCount / Math.max(1, letterCount) > 0.3) {
    const nonCjkPart = trimmed.replace(cjkRegex, " ").trim();
    const nonCjkWords = nonCjkPart ? nonCjkPart.split(/\s+/).filter(Boolean).length : 0;

    words = cjkCharCount + nonCjkWords;
    tokens = Math.ceil(cjkCharCount * 1.15) + Math.ceil(nonCjkWords * 1.3);
  }
  // Case 2: Indic scripts (Hindi, Bengali, Tamil, Telugu, Malayalam, Kannada, Gujarati, Odia, Punjabi, etc.)
  else if (indicCharCount > 0 && indicCharCount / Math.max(1, letterCount) > 0.3) {
    const rawWords = trimmed.split(/\s+/).filter(Boolean).length;
    words = rawWords;
    // Indic subwords average ~1.7 tokens per space-separated word due to matras and conjuncts
    tokens = Math.ceil(words * 1.7);
  }
  // Case 3: Standard space-separated languages (English, Latin, Arabic, Urdu, Transliterated Hinglish, etc.)
  else {
    const rawWords = trimmed.split(/\s+/).filter(Boolean).length;
    words = rawWords;
    // English/Latin text averages ~1.28 tokens per word
    tokens = Math.ceil(words * 1.28);
  }

  tokens = Math.max(words, tokens);

  return { tokens, words, chars };
}
