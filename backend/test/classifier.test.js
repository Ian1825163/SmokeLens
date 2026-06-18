const assert = require("node:assert/strict");
const test = require("node:test");

const { inferReading, modelInfo } = require("../src/classifier");

test("loads the selected seed 46 MLP", () => {
  const info = modelInfo();
  assert.equal(info.model_version, "smokelens_mlp_7x2x4_seed46_pm_guard_v1");
  assert.equal(info.architecture, "7_to_2_to_4_relu");
  assert.equal(info.feature_columns.length, 7);
});

test("PM guard detects smoke when at least two particle thresholds are reached", () => {
  const result = inferReading({
    pms_valid: true,
    voc_mv: 2267,
    co_mv: 2889,
    pm1_0: 38,
    pm2_5: 56,
    pm10: 67,
    temperature: 23.6,
    humidity: 75.2
  });

  assert.equal(result.inference_class, "cigarette_smoke");
  assert.equal(result.cigarette_detected, true);
  assert.equal(result.inference_score, 1);
});

test("collapses the four-class model into normal air versus smoke", () => {
  const cases = [
    {
      expected: "normal_air",
      reading: { voc_mv: 2154, co_mv: 2735, pm1_0: 0, pm2_5: 0, pm10: 0, temperature: 23.3, humidity: 76.5 }
    },
    {
      expected: "normal_air",
      reading: { voc_mv: 2495, co_mv: 3139, pm1_0: 29, pm2_5: 48, pm10: 59, temperature: 28.5, humidity: 64.9 }
    },
    {
      expected: "normal_air",
      reading: { voc_mv: 2263, co_mv: 2889, pm1_0: 13, pm2_5: 32, pm10: 36, temperature: 27.0, humidity: 73.7 }
    },
    {
      expected: "cigarette_smoke",
      reading: { voc_mv: 2155, co_mv: 2746, pm1_0: 37, pm2_5: 91, pm10: 98, temperature: 22.8, humidity: 77.4 }
    }
  ];

  for (const item of cases) {
    const result = inferReading({ ...item.reading, pms_valid: true });
    assert.equal(result.inference_class, item.expected);
    assert.ok(result.inference_score >= 0.5 && result.inference_score <= 1);
    assert.equal(result.cigarette_detected, item.expected === "cigarette_smoke");
  }
});

test("classifies data collection readings without replacing their label", () => {
  const reading = {
    mode: "data_collection",
    collection_label: "cigarette_smoke",
    pms_valid: true,
    voc_mv: 2154,
    co_mv: 2735,
    pm1_0: 0,
    pm2_5: 0,
    pm10: 0,
    temperature: 23.3,
    humidity: 76.5
  };

  const result = inferReading(reading);
  assert.equal(result.inference_class, "normal_air");
  assert.ok(result.inference_score > 0);
  assert.equal(reading.collection_label, "cigarette_smoke");
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
      model_version: "smokelens_mlp_7x2x4_seed46_pm_guard_v1",
      classification: "unclassified"
    });
  }
});
