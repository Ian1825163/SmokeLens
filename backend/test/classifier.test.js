const assert = require("node:assert/strict");
const test = require("node:test");

const { inferReading, modelInfo } = require("../src/classifier");

test("loads the selected seed 46 MLP", () => {
  const info = modelInfo();
  assert.equal(info.model_version, "smokelens_mlp_7x2x4_seed46");
  assert.equal(info.architecture, "7_to_2_to_4_relu");
  assert.equal(info.feature_columns.length, 7);
});

test("classifies representative readings with softmax confidence", () => {
  const cases = [
    {
      expected: "normal_air",
      score: 0.807050347328186,
      reading: { voc_mv: 2154, co_mv: 2735, pm1_0: 0, pm2_5: 0, pm10: 0, temperature: 23.3, humidity: 76.5 }
    },
    {
      expected: "cooking_fume",
      score: 0.7823778986930847,
      reading: { voc_mv: 2495, co_mv: 3139, pm1_0: 29, pm2_5: 48, pm10: 59, temperature: 28.5, humidity: 64.9 }
    },
    {
      expected: "vehicle_exhaust",
      score: 0.882064700126648,
      reading: { voc_mv: 2263, co_mv: 2889, pm1_0: 13, pm2_5: 32, pm10: 36, temperature: 27.0, humidity: 73.7 }
    },
    {
      expected: "cigarette_smoke",
      score: 0.9092634320259094,
      reading: { voc_mv: 2155, co_mv: 2746, pm1_0: 37, pm2_5: 91, pm10: 98, temperature: 22.8, humidity: 77.4 }
    }
  ];

  for (const item of cases) {
    const result = inferReading({ ...item.reading, pms_valid: true });
    assert.equal(result.inference_class, item.expected);
    assert.ok(Math.abs(result.inference_score - item.score) < 1e-6);
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
      model_version: "smokelens_mlp_7x2x4_seed46",
      classification: "unclassified"
    });
  }
});
