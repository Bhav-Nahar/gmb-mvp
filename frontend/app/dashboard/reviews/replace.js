const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, 'page.tsx');
const tempPath = path.join(__dirname, 'temp_jsx.txt');

const pageContent = fs.readFileSync(pagePath, 'utf8');
const jsxContent = fs.readFileSync(tempPath, 'utf8');

// Find the start of the return block
// It starts with: `  return (\n    <div className={locationId ? "" : "min-h-screen bg-background text-foreground"}>`

const match = pageContent.indexOf('  return (\n    <div className={locationId ? "" : "min-h-screen bg-background text-foreground"}>');

if (match !== -1) {
    const newContent = pageContent.substring(0, match) + jsxContent;
    fs.writeFileSync(pagePath, newContent, 'utf8');
    console.log('Replaced JSX successfully.');
} else {
    // try to find just `  return (`
    const fallbackMatch = pageContent.indexOf('  return (');
    if (fallbackMatch !== -1) {
        const selectedMatch = pageContent.lastIndexOf('  const selectedReview = reviews.find(r => r.id === selectedReviewId)');
        if (selectedMatch !== -1) {
            const newContent = pageContent.substring(0, selectedMatch) + jsxContent;
            fs.writeFileSync(pagePath, newContent, 'utf8');
            console.log('Replaced JSX successfully via fallback.');
        } else {
             const newContent = pageContent.substring(0, fallbackMatch) + jsxContent;
             fs.writeFileSync(pagePath, newContent, 'utf8');
             console.log('Replaced JSX successfully via fallback 2.');
        }
    } else {
        console.error('Could not find the return block to replace.');
    }
}
