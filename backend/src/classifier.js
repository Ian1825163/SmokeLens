function classifyReading() {
  // Classification is intentionally deferred until baseline calibration exists.
  // The backend stores raw readings now so later rules/SVM training use real data.
  return null;
}

module.exports = {
  classifyReading
};
