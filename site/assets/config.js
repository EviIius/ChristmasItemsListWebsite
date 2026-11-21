// Site settings. Change these if the repository is renamed or moved.
window.SITE_CONFIG = {
  repo: "EviIius/ChristmasItemsListWebsite",        // owner/name on GitHub
  branch: "main",
  workflow: "scrape.yml",                           // .github/workflows/<file> that re-scrapes and republishes
  schedule: "twice a day, around 6:45 AM and 6:45 PM Eastern", // keep in sync with the cron lines in that workflow
  maintainer: "Jake",                               // who hands out refresh keys
  siteUrl: "https://eviiius.github.io/ChristmasItemsListWebsite/", // GitHub Pages address
  christmas: { month: 12, day: 25 },
};
