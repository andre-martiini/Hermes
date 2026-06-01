const fs = require('fs');
const content = fs.readFileSync('dist/assets/index-B3trA2Fh.js', 'utf8');
const lines = content.split('\n');
console.log("Number of lines:", lines.length);
if (lines.length >= 4680) {
  const lineContent = lines[4679];
  console.log("Length of line 4680:", lineContent.length);
  const start = Math.max(0, 41926 - 150);
  const end = Math.min(lineContent.length, 41926 + 150);
  console.log("Context:\n", lineContent.substring(start, end));
} else {
  console.log("Line 4680 does not exist.");
}
