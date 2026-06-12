const fs = require("fs");

const config = require("./config");

function loadModel(modelPath) {
  const model = JSON.parse(fs.readFileSync(modelPath, "utf8"));
  const featureCount = model.feature_columns.length;
  if (
    model.feature_mean.length !== featureCount ||
    model.feature_std.length !== featureCount ||
    model.weights.length !== model.labels.length ||
    model.bias.length !== model.labels.length ||
    model.weights.some((row) => row.length !== featureCount)
  ) {
    throw new Error(`Invalid linear model shape: ${modelPath}`);
  }
  return model;
}

const model = loadModel(config.modelPath);

function finiteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isTrue(value) {
  return value === true || value === 1 || String(value).toLowerCase() === "true";
}

function softmax(logits) {
  const maximum = Math.max(...logits);
  const exponentials = logits.map((value) => Math.exp(value - maximum));
  const total = exponentials.reduce((sum, value) => sum + value, 0);
  return exponentials.map((value) => value / total);
}

function unavailableInference() {
  return {
    inference_class: null,
    cigarette_detected: false,
    inference_score: null,
    model_version: model.model_version,
    classification: "unclassified"
  };
}

function inferReading(reading) {
  if (!reading || !isTrue(reading.pms_valid)) {
    return unavailableInference();
  }

  const values = model.feature_columns.map((column) => finiteNumber(reading[column]));
  if (values.some((value) => value === null)) {
    return unavailableInference();
  }

  const standardized = values.map(
    (value, index) => (value - model.feature_mean[index]) / model.feature_std[index]
  );
  const logits = model.weights.map(
    (weights, labelIndex) =>
      weights.reduce(
        (sum, weight, featureIndex) => sum + weight * standardized[featureIndex],
        model.bias[labelIndex]
      )
  );
  const probabilities = softmax(logits);
  const predictedIndex = probabilities.reduce(
    (bestIndex, probability, index) =>
      probability > probabilities[bestIndex] ? index : bestIndex,
    0
  );
  const inferenceClass = model.labels[predictedIndex];

  return {
    inference_class: inferenceClass,
    cigarette_detected: inferenceClass === "cigarette_smoke",
    inference_score: probabilities[predictedIndex],
    model_version: model.model_version,
    classification: inferenceClass
  };
}

function classifyReading(reading) {
  if (reading && reading.mode === "inference") {
    return inferReading(reading).classification;
  }
  return "unclassified";
}

function modelInfo() {
  return {
    model_version: model.model_version,
    architecture: model.architecture,
    feature_columns: [...model.feature_columns],
    labels: [...model.labels],
    model_path: config.modelPath
  };
}

module.exports = {
  classifyReading,
  inferReading,
  modelInfo
};
