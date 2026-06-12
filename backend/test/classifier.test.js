const assert = require("node:assert/strict");
const test = require("node:test");

const { inferReading, modelInfo } = require("../src/classifier");

test("loads the selected seed 113 linear model", () => {
  const info = modelInfo();
  assert.equal(info.model_version, "smokelens_linear_seed113");
  assert.equal(info.architecture, "7_to_4_linear");
  assert.equal(info.feature_columns.length, 7);
});

test("classifies representative readings with softmax confidence", () => {
  const cases = [
    {
      expected: "normal_air",
      reading: { voc_mv: 2253, co_mv: 2872, pm1_0: 0, pm2_5: 0, pm10: 0, temperature: 25.3, humidity: 62.6 }
    },
    {
      expected: "cooking_fume",
      reading: { voc_mv: 2498, co_mv: 3139, pm1_0: 28, pm2_5: 44, pm10: 53, temperature: 28.6, humidity: 64.1 }
    },
    {
      expected: "vehicle_exhaust",
      reading: { voc_mv: 2262, co_mv: 2887, pm1_0: 14, pm2_5: 34, pm10: 40, temperature: 27.0, humidity: 76.7 }
    },
    {
      expected: "cigarette_smoke",
      reading: { voc_mv: 2283, co_mv: 2914, pm1_0: 32, pm2_5: 44, pm10: 53, temperature: 22.7, humidity: 55.2 }
    }
  ];

  for (const item of cases) {
    const result = inferReading({ ...item.reading, pms_valid: true });
    assert.equal(result.inference_class, item.expected);
    assert.ok(result.inference_score > 0 && result.inference_score <= 1);
  }
});

test("does not infer from invalid or incomplete sensor data", () => {
  for (const reading of [
    { pms_valid: false },
    { pms_valid: true, voc_mv: 2200 }
  ]) {
    assert.deepEqual(inferReading(reading), {
      inference_class: null,
      cigarette_detected: false,
      inference_score: null,
      model_version: "smokelens_linear_seed113",
      classification: "unclassified"
    });
  }
});
