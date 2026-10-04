import {LinkChecker} from 'linkinator';
const checker = new LinkChecker();
const result = await checker.check({
  path: 'static-site/dist', recurse: true, port: 8174,
  urlRewriteExpressions: [{pattern: /^https:\/\/(?:www\.)?arcadian-eu\.com(?=\/|$)/, replacement: 'http://localhost:8174'}],
  linksToSkip: ['linkedin\\.com|instagram\\.com|facebook\\.com|wa\\.me|maps\\.google\\.|google\\.com/maps'],
});
for (const link of result.links.filter((link) => link.state === 'BROKEN')) console.error(`${link.status}: ${link.url}`);
if (!result.passed) process.exitCode = 1;
else console.log(`PASS: ${result.links.length} links checked against the built site and external destinations.`);
