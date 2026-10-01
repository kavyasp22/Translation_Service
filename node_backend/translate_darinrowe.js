const tr = require("googletrans").default;

const text = process.argv[2];
const from = process.argv[3] || 'auto';
const to = process.argv[4] || 'en';

tr(text, {from: from, to: to})
  .then(res => {
    const output = {
      translated_text: res.text,
      detected_language: res.src,
      has_corrected_text: res.hasCorrectedText,
      corrected_text: res.correctedText || "",
      pronunciation: res.pronunciation || ""
    };
    console.log(JSON.stringify(output));
  })
  .catch(err => {
    console.log(JSON.stringify({error: err.message}));
  });
