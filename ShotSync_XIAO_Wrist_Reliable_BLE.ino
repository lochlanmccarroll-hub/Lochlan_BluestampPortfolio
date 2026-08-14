
#include <ArduinoBLE.h>
#include <Wire.h>
#include "LSM6DS3.h"
#include <math.h>
#include <stdint.h>

LSM6DS3 imu(I2C_MODE, 0x6A);

// New UUID set prevents the Mac from reusing the old cached GATT layout.
#define SERVICE_UUID \
  "7A1E0001-6A7B-4C5D-9E10-112233445566"

#define EVENT_CHARACTERISTIC_UUID \
  "7A1E0003-6A7B-4C5D-9E10-112233445566"

#define SAMPLE_CHARACTERISTIC_UUID \
  "7A1E0004-6A7B-4C5D-9E10-112233445566"

BLEService wristService(SERVICE_UUID);

BLECharacteristic eventCharacteristic(
  EVENT_CHARACTERISTIC_UUID,
  BLERead | BLEIndicate,
  20
);

BLECharacteristic sampleCharacteristic(
  SAMPLE_CHARACTERISTIC_UUID,
  BLERead | BLEIndicate,
  20,
  true
);

volatile bool bleConnected = false;
bool bleReadyWasAnnounced = false;

const float G_TO_MPS2 = 9.80665f;
const uint32_t SAMPLE_PERIOD_US = 9615;  // ~104 Hz

// Shot Thresholds
const float MIN_TOTAL_GYRO_DPS = 500.0f;
const float GY_RELEASE_THRESHOLD_DPS = -400.0f;
const float GZ_RELEASE_THRESHOLD_DPS = -80.0f;
const float MIN_Y_DOMINANCE_RATIO = 0.60f;
const int REQUIRED_MATCHING_SAMPLES = 1;

// 500ms before/after releaseee
const size_t PRE_SAMPLES = 52;
const size_t POST_SAMPLES = 52;
const size_t MAX_SHOT_SAMPLES =
  PRE_SAMPLES + POST_SAMPLES;
const size_t TRANSMIT_STRIDE = 2;
const uint32_t COOLDOWN_MS = 700;

// Indication pacing
const uint32_t EVENT_SETTLE_MS = 20;
const uint32_t SAMPLE_SETTLE_MS = 24;
const int MAX_SEND_ATTEMPTS = 5;

struct MotionSample {
  uint32_t timeUs;
  float ax;
  float ay;
  float az;
  float gx;
  float gy;
  float gz;
};

enum DetectorState {
  WAITING,
  CAPTURING_POST_RELEASE,
  TRANSMITTING,
  COOLDOWN
};

DetectorState state = WAITING;

MotionSample preBuffer[PRE_SAMPLES];
MotionSample shotSamples[MAX_SHOT_SAMPLES];

size_t preWriteIndex = 0;
size_t preSampleCount = 0;

size_t shotSampleCount = 0;
size_t triggerIndex = 0;
size_t postSamplesCaptured = 0;

uint32_t nextSampleTimeUs = 0;
uint32_t candidateTimeMs = 0;
uint32_t triggerTimeUs = 0;
uint32_t cooldownStartMs = 0;
uint32_t wristShotId = 0;

int consecutiveMatches = 0;



// BLE setup and reliable indications


void bleConnectHandler(BLEDevice central) {
  bleConnected = true;
  bleReadyWasAnnounced = false;

  Serial.print("BLE_CONNECTED,");
  Serial.println(central.address());
}

void bleDisconnectHandler(BLEDevice central) {
  bleConnected = false;
  bleReadyWasAnnounced = false;

  Serial.print("BLE_DISCONNECTED,");
  Serial.println(central.address());

  BLE.advertise();
}

bool bleTransportReady() {
  return (
    bleConnected &&
    eventCharacteristic.subscribed() &&
    sampleCharacteristic.subscribed()
  );
}

void setupBle() {
  if (!BLE.begin()) {
    Serial.println("ERROR: BLE.begin() failed.");

    while (true) {
      delay(100);
    }
  }

  BLE.setLocalName("ShotSyncWristXIAO");
  BLE.setDeviceName("ShotSyncWristXIAO");
  BLE.setAdvertisedService(wristService);

  wristService.addCharacteristic(
    eventCharacteristic
  );

  wristService.addCharacteristic(
    sampleCharacteristic
  );

  BLE.addService(wristService);

  BLE.setEventHandler(
    BLEConnected,
    bleConnectHandler
  );

  BLE.setEventHandler(
    BLEDisconnected,
    bleDisconnectHandler
  );

  BLE.advertise();

  Serial.println(
    "BLE advertising as ShotSyncWristXIAO."
  );
}

bool writeIndication(
  BLECharacteristic &characteristic,
  const uint8_t *data,
  size_t length,
  uint32_t settleMs
) {
  if (
    !bleConnected ||
    !characteristic.subscribed()
  ) {
    return false;
  }

  for (
    int attempt = 1;
    attempt <= MAX_SEND_ATTEMPTS;
    attempt++
  ) {
    int result = characteristic.writeValue(
      data,
      (int)length
    );

    if (result) {
      uint32_t startMs = millis();

      while (
        millis() - startMs < settleMs
      ) {
        BLE.poll();
        delay(1);
      }

      return true;
    }

    BLE.poll();
    delay(10);
  }

  return false;
}

bool sendEventLine(const String &line) {
  String message = line + "\n";

  for (
    size_t start = 0;
    start < message.length();
    start += 20
  ) {
    size_t remaining =
      message.length() - start;

    size_t chunkLength =
      remaining < 20 ? remaining : 20;

    bool sent = writeIndication(
      eventCharacteristic,
      reinterpret_cast<const uint8_t*>(
        message.c_str() + start
      ),
      chunkLength,
      EVENT_SETTLE_MS
    );

    if (!sent) {
      Serial.print(
        "ERROR: failed to send event chunk: "
      );
      Serial.println(line);
      return false;
    }
  }

  Serial.println(line);
  return true;
}



// Compact binary packets

void writeUint16LE(
  uint8_t *destination,
  uint16_t value
) {
  destination[0] = value & 0xFF;
  destination[1] = (value >> 8) & 0xFF;
}

void writeInt16LE(
  uint8_t *destination,
  int16_t value
) {
  writeUint16LE(
    destination,
    (uint16_t)value
  );
}

int16_t scaledInt16(
  float value,
  float scale
) {
  float scaled = value * scale;

  if (scaled > 32767.0f) {
    scaled = 32767.0f;
  }

  if (scaled < -32768.0f) {
    scaled = -32768.0f;
  }

  return (int16_t)lroundf(scaled);
}

bool sendSamplePacket(
  uint16_t shotId,
  uint16_t transmittedIndex,
  int16_t relativeTimeMs,
  const MotionSample &sample
) {
  uint8_t packet[20];

  packet[0] = 0x53;
  packet[1] = 1;

  writeUint16LE(
    packet + 2,
    shotId
  );

  writeUint16LE(
    packet + 4,
    transmittedIndex
  );

  writeInt16LE(
    packet + 6,
    relativeTimeMs
  );

  writeInt16LE(
    packet + 8,
    scaledInt16(sample.ax, 100.0f)
  );

  writeInt16LE(
    packet + 10,
    scaledInt16(sample.ay, 100.0f)
  );

  writeInt16LE(
    packet + 12,
    scaledInt16(sample.az, 100.0f)
  );

  writeInt16LE(
    packet + 14,
    scaledInt16(sample.gx, 10.0f)
  );

  writeInt16LE(
    packet + 16,
    scaledInt16(sample.gy, 10.0f)
  );

  writeInt16LE(
    packet + 18,
    scaledInt16(sample.gz, 10.0f)
  );

  return writeIndication(
    sampleCharacteristic,
    packet,
    sizeof(packet),
    SAMPLE_SETTLE_MS
  );
}

// IMU and coordinate transformation

MotionSample readMotionSample(
  uint32_t sampleTimeUs
) {
  MotionSample sample;

  float rawAx =
    imu.readFloatAccelX() * G_TO_MPS2;

  float rawAy =
    imu.readFloatAccelY() * G_TO_MPS2;

  float rawAz =
    imu.readFloatAccelZ() * G_TO_MPS2;

  float rawGx = imu.readFloatGyroX();
  float rawGy = imu.readFloatGyroY();
  float rawGz = imu.readFloatGyroZ();

  sample.timeUs = sampleTimeUs;

  // Match the coordinate direction used by the previous wrist system.
  sample.ax = rawAx;
  sample.ay = -rawAy;
  sample.az = rawAz;

  sample.gx = rawGx;
  sample.gy = -rawGy;
  sample.gz = rawGz;

  return sample;
}


// Capture and release detection
void pushPreSample(
  const MotionSample &sample
) {
  preBuffer[preWriteIndex] = sample;

  preWriteIndex =
    (preWriteIndex + 1) % PRE_SAMPLES;

  if (preSampleCount < PRE_SAMPLES) {
    preSampleCount++;
  }
}

void appendShotSample(
  const MotionSample &sample
) {
  if (
    shotSampleCount <
    MAX_SHOT_SAMPLES
  ) {
    shotSamples[shotSampleCount] = sample;
    shotSampleCount++;
  }
}

void copyPreBufferIntoShot() {
  shotSampleCount = 0;

  size_t oldestIndex =
    (
      preWriteIndex +
      PRE_SAMPLES -
      preSampleCount
    ) % PRE_SAMPLES;

  for (
    size_t index = 0;
    index < preSampleCount;
    index++
  ) {
    size_t sourceIndex =
      (oldestIndex + index) %
      PRE_SAMPLES;

    appendShotSample(
      preBuffer[sourceIndex]
    );
  }
}

bool matchesReleasePattern(
  const MotionSample &sample
) {
  float gyroTotal = sqrtf(
    sample.gx * sample.gx +
    sample.gy * sample.gy +
    sample.gz * sample.gz
  );

  if (gyroTotal <= 0.0f) {
    return false;
  }

  float yDominance =
    fabsf(sample.gy) / gyroTotal;

  return (
    gyroTotal >= MIN_TOTAL_GYRO_DPS &&
    sample.gy <= GY_RELEASE_THRESHOLD_DPS &&
    sample.gz <= GZ_RELEASE_THRESHOLD_DPS &&
    yDominance >= MIN_Y_DOMINANCE_RATIO
  );
}

void startShotCapture(
  const MotionSample &triggerSample,
  uint32_t nowMs
) {
  wristShotId++;

  candidateTimeMs = nowMs;
  triggerTimeUs = triggerSample.timeUs;

  postSamplesCaptured = 0;
  consecutiveMatches = 0;

  copyPreBufferIntoShot();

  triggerIndex = shotSampleCount - 1;

  String triggerLine =
    String("WRIST_TRIGGER,") +
    String(wristShotId) + "," +
    String(candidateTimeMs);

  if (!sendEventLine(triggerLine)) {
    Serial.println(
      "ERROR: trigger transmission failed."
    );
  }

  state = CAPTURING_POST_RELEASE;
}

void checkForCandidate(
  const MotionSample &sample,
  uint32_t nowMs
) {
  if (!bleTransportReady()) {
    consecutiveMatches = 0;
    return;
  }

  if (matchesReleasePattern(sample)) {
    consecutiveMatches++;
  } else {
    consecutiveMatches = 0;
  }

  if (
    consecutiveMatches >=
    REQUIRED_MATCHING_SAMPLES
  ) {
    startShotCapture(sample, nowMs);
  }
}


// Reliable shot transmission

void transmitCompletedShot() {
  size_t startIndex =
    triggerIndex % TRANSMIT_STRIDE;

  size_t transmittedCount =
    (
      shotSampleCount - 1 - startIndex
    ) / TRANSMIT_STRIDE + 1;

  size_t transmittedTriggerIndex =
    (
      triggerIndex - startIndex
    ) / TRANSMIT_STRIDE;

  String beginLine =
    String("WRIST_BEGIN,") +
    String(wristShotId) + "," +
    String(candidateTimeMs) + "," +
    String((unsigned int)transmittedCount) + "," +
    String(
      (unsigned int)transmittedTriggerIndex
    );

  if (!sendEventLine(beginLine)) {
    Serial.println(
      "ERROR: WRIST_BEGIN transmission failed."
    );
  }

  delay(30);
  BLE.poll();

  size_t transmittedIndex = 0;
  size_t successfulSamples = 0;

  for (
    size_t sourceIndex = startIndex;
    sourceIndex < shotSampleCount;
    sourceIndex += TRANSMIT_STRIDE
  ) {
    MotionSample &sample =
      shotSamples[sourceIndex];

    int32_t relativeTimeUs =
      (int32_t)(
        sample.timeUs - triggerTimeUs
      );

    int16_t relativeTimeMs =
      (int16_t)lroundf(
        relativeTimeUs / 1000.0f
      );

    bool sent = sendSamplePacket(
      (uint16_t)wristShotId,
      (uint16_t)transmittedIndex,
      relativeTimeMs,
      sample
    );

    if (sent) {
      successfulSamples++;
    } else {
      Serial.print(
        "ERROR: sample packet failed, index "
      );
      Serial.println(transmittedIndex);
    }

    transmittedIndex++;
  }

  String endLine =
    String("WRIST_END,") +
    String(wristShotId);

  delay(30);
  BLE.poll();

  sendEventLine(endLine);

  Serial.print("SHOT_TRANSFER_COMPLETE,");
  Serial.print(wristShotId);
  Serial.print(",");
  Serial.print(successfulSamples);
  Serial.print("/");
  Serial.println(transmittedCount);
}



// Setup and loop


void setup() {
  Serial.begin(115200);

  uint32_t serialWaitStartMs = millis();

  while (
    !Serial &&
    millis() - serialWaitStartMs < 1800
  ) {
    delay(10);
  }

  Serial.println();
  Serial.println(
    "ShotSync XIAO reliable BLE wrist"
  );

  Wire.begin();

  imu.settings.accelRange = 16;
  imu.settings.accelSampleRate = 104;
  imu.settings.accelBandWidth = 100;

  imu.settings.gyroRange = 2000;
  imu.settings.gyroSampleRate = 104;
  imu.settings.gyroBandWidth = 400;

  int imuStatus = imu.begin();

  if (imuStatus != 0) {
    Serial.print(
      "ERROR: onboard IMU failed. Status: "
    );
    Serial.println(imuStatus);

    while (true) {
      delay(100);
    }
  }

  Serial.println("IMU initialized.");

  setupBle();

  nextSampleTimeUs = micros();

  Serial.println(
    "Detector profile: XIAO_RELIABLE_V2"
  );

  Serial.println(
    "Waiting for Python to subscribe to both BLE channels..."
  );
}

void loop() {
  BLE.poll();

  bool ready = bleTransportReady();

  if (
    ready &&
    !bleReadyWasAnnounced
  ) {
    bleReadyWasAnnounced = true;

    Serial.println(
      "BLE_READY: event and sample channels subscribed."
    );
  }

  if (!ready) {
    bleReadyWasAnnounced = false;
  }

  if (state == TRANSMITTING) {
    transmitCompletedShot();

    cooldownStartMs = millis();
    state = COOLDOWN;

    nextSampleTimeUs =
      micros() + SAMPLE_PERIOD_US;

    return;
  }

  uint32_t nowUs = micros();

  if (
    (int32_t)(nowUs - nextSampleTimeUs) < 0
  ) {
    return;
  }

  nextSampleTimeUs += SAMPLE_PERIOD_US;

  MotionSample sample =
    readMotionSample(nowUs);

  uint32_t nowMs = millis();

  switch (state) {
    case WAITING:
      pushPreSample(sample);
      checkForCandidate(sample, nowMs);
      break;

    case CAPTURING_POST_RELEASE:
      appendShotSample(sample);
      postSamplesCaptured++;

      if (
        postSamplesCaptured >= POST_SAMPLES
      ) {
        state = TRANSMITTING;
      }

      break;

    case TRANSMITTING:
      // Handled before timed sampling.
      break;

    case COOLDOWN:
      pushPreSample(sample);

      if (
        nowMs - cooldownStartMs >=
        COOLDOWN_MS
      ) {
        consecutiveMatches = 0;
        state = WAITING;
      }

      break;
  }
}
