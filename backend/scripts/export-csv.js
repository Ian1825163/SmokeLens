const fs = require("fs");
const path = require("path");

const config = require("../src/config");
const { openDatabase } = require("../src/db");
const { READING_COLUMNS, rowToCsv } = require("../src/csv");

const outputPath =
  process.argv[2] ||
  path.join(config.dataDir, `smokelens_export_${Date.now()}.csv`);

fs.mkdirSync(path.dirname(outputPath), { recursive: true });

async function main() {
  const store = await openDatabase(config);
  const rows = store.historyReadings({
    limit: config.exportLimitMax,
    maxLimit: config.exportLimitMax,
    ascending: true
  });

  const stream = fs.createWriteStream(outputPath, { encoding: "utf8" });
  stream.write(`${READING_COLUMNS.join(",")}\n`);

  for (const row of rows) {
    stream.write(`${rowToCsv(row)}\n`);
  }

  stream.end(() => {
    store.close();
    console.log(`Exported ${rows.length} readings to ${outputPath}`);
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
