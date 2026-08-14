
#include <Arduino.h>
#include <limits.h>

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// Pins and sensor configuration
const int IR_PIN = D2;
const int PIEZO_PIN = A4;

const int MINIMUM_PIEZO_THRESHOLD = 400;
int activePiezoThreshold = MINIMUM_PIEZO_THRESHOLD;

bool beamWasBroken = false;
bool irArmed = false;

int clearIrState = HIGH;

unsigned long beamBreakStart = 0;
unsigned long latestValidBeamBreakMs = 0;
unsigned long clearStateStartMs = 0;

const unsigned long MINIMUM_BREAK_MS = 15;
const unsigned long MAXIMUM_BREAK_MS = 500;
const unsigned long REQUIRED_CLEAR_MS = 250;

bool piezoEventWaiting = false;
bool irEventWaiting = false;

unsigned long piezoEventTime = 0;
unsigned long irEventTime = 0;

int piezoPeak = 0;

const unsigned long EVENT_WINDOW_MS = 700;

unsigned long lastShotEventTime = 0;
const unsigned long SHOT_COOLDOWN_MS = 900;

unsigned long eventNumber = 0;



// BLE
#define HOOP_SERVICE_UUID \
  "7A1E1001-6A7B-4C5D-9E10-112233445566"

#define HOOP_EVENT_CHARACTERISTIC_UUID \
  "7A1E1003-6A7B-4C5D-9E10-112233445566"

BLEServer* bleServer = nullptr;
BLECharacteristic* hoopEventCharacteristic = nullptr;

volatile bool bleConnected = false;

enum HoopResultCode : uint8_t {
  RESULT_CLEAN_MAKE = 1,
  RESULT_RIM_MAKE = 2,
  RESULT_RIM_MISS = 3
};

enum HoopContactCode : uint8_t {
  CONTACT_NONE = 0,
  CONTACT_RIM = 1
};

struct __attribute__((packed)) HoopBlePacket {
  uint8_t marker;
  uint8_t version;
  uint16_t eventNumber;
  uint32_t boardTimeMs;
  uint8_t resultCode;
  uint8_t contactCode;
  uint16_t piezoPeak;
  uint16_t beamBreakMs;
  uint16_t reserved;
};

static_assert(
  sizeof(HoopBlePacket) == 16,
  "Hoop BLE packet must be exactly 16 bytes."
);


class HoopServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* server) override {
    bleConnected = true;
    Serial.println("HOOP_BLE_CONNECTED");
  }

  void onDisconnect(BLEServer* server) override {
    bleConnected = false;
    Serial.println("HOOP_BLE_DISCONNECTED");

    delay(100);
    server->startAdvertising();
    Serial.println("HOOP_BLE_ADVERTISING");
  }
};


void setupBle() {
  BLEDevice::init("ShotSyncHoop");

  bleServer = BLEDevice::createServer();

  bleServer->setCallbacks(
    new HoopServerCallbacks()
  );

  BLEService* service =
    bleServer->createService(
      HOOP_SERVICE_UUID
    );

  hoopEventCharacteristic =
    service->createCharacteristic(
      HOOP_EVENT_CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ
      | BLECharacteristic::PROPERTY_NOTIFY
    );

  hoopEventCharacteristic->addDescriptor(
    new BLE2902()
  );

  service->start();

  BLEAdvertising* advertising =
    BLEDevice::getAdvertising();

  advertising->addServiceUUID(
    HOOP_SERVICE_UUID
  );

  advertising->setScanResponse(true);
  advertising->start();

  Serial.println("HOOP_BLE_ADVERTISING");
  Serial.println(
    "BLE device name: ShotSyncHoop"
  );
}


void sendHoopBlePacket(
  uint16_t eventId,
  uint32_t eventTimeMs,
  uint8_t resultCode,
  uint8_t contactCode,
  uint16_t recordedPiezoPeak,
  uint16_t beamBreakMs
) {
  if (
    !bleConnected
    || hoopEventCharacteristic == nullptr
  ) {
    return;
  }

  HoopBlePacket packet;

  packet.marker = 0x48;
  packet.version = 1;
  packet.eventNumber = eventId;
  packet.boardTimeMs = eventTimeMs;
  packet.resultCode = resultCode;
  packet.contactCode = contactCode;
  packet.piezoPeak = recordedPiezoPeak;
  packet.beamBreakMs = beamBreakMs;
  packet.reserved = 0;

  hoopEventCharacteristic->setValue(
    reinterpret_cast<uint8_t*>(&packet),
    sizeof(packet)
  );

  hoopEventCharacteristic->notify();

  /*
    Hoop events are infrequent. So with duplicate notification makes
    loss less likely where later the ython removes duplicates by event ID/time.
  */
  delay(25);

  if (bleConnected) {
    hoopEventCharacteristic->notify();
  }
}


// Setup and loop
void setup() {
  Serial.begin(115200);

  unsigned long serialWaitStart =
    millis();

  while (
    !Serial
    && millis() - serialWaitStart < 1800
  ) {
    delay(10);
  }

  analogReadResolution(10);

  analogSetPinAttenuation(
    PIEZO_PIN,
    ADC_11db
  );

  pinMode(IR_PIN, INPUT_PULLUP);

  Serial.println();
  Serial.println(
    "ShotSync Nano ESP32 hoop detector"
  );

  Serial.println(
    "Keep the beam clear and do not touch "
    "the rim during calibration."
  );

  calibratePiezoNoise();
  calibrateIrClearState();

  Serial.print("Piezo threshold: ");
  Serial.println(activePiezoThreshold);

  Serial.print("IR clear state: ");
  Serial.println(clearIrState);

  setupBle();

  Serial.println("HOOP_READY");
}


void loop() {
  unsigned long now = millis();

  readPiezo(now);
  readIr(now);
  classifyEvents(now);
}


// Calibration and sensor reads

void calibratePiezoNoise() {
  int largestNoiseWindow = 0;

  unsigned long calibrationStart =
    millis();

  while (
    millis() - calibrationStart < 900
  ) {
    int minimumReading = INT_MAX;
    int maximumReading = INT_MIN;

    unsigned long windowStart =
      micros();

    while (
      micros() - windowStart < 5000
    ) {
      int reading =
        analogRead(PIEZO_PIN);

      if (reading < minimumReading) {
        minimumReading = reading;
      }

      if (reading > maximumReading) {
        maximumReading = reading;
      }
    }

    int peakToPeak =
      maximumReading - minimumReading;

    if (
      peakToPeak > largestNoiseWindow
    ) {
      largestNoiseWindow =
        peakToPeak;
    }

    delay(2);
  }

  activePiezoThreshold = max(
    MINIMUM_PIEZO_THRESHOLD,
    largestNoiseWindow + 5
  );

  Serial.print(
    "Piezo startup noise peak-to-peak: "
  );

  Serial.println(
    largestNoiseWindow
  );
}


void calibrateIrClearState() {
  int lowCount = 0;
  int highCount = 0;

  for (
    int index = 0;
    index < 250;
    index++
  ) {
    int state = digitalRead(IR_PIN);

    if (state == HIGH) {
      highCount++;
    } else {
      lowCount++;
    }

    delay(2);
  }

  clearIrState = (
    highCount >= lowCount
    ? HIGH
    : LOW
  );

  beamWasBroken = false;
  irArmed = false;
  clearStateStartMs = millis();
}


void readPiezo(
  unsigned long now
) {
  int minimumReading = INT_MAX;
  int maximumReading = INT_MIN;

  unsigned long startTime =
    micros();

  while (
    micros() - startTime < 5000
  ) {
    int reading =
      analogRead(PIEZO_PIN);

    if (reading < minimumReading) {
      minimumReading = reading;
    }

    if (reading > maximumReading) {
      maximumReading = reading;
    }
  }

  int peakToPeak =
    maximumReading - minimumReading;

  if (
    peakToPeak
      >= activePiezoThreshold
    && now - lastShotEventTime
       > SHOT_COOLDOWN_MS
  ) {
    if (
      !piezoEventWaiting
      || peakToPeak > piezoPeak
    ) {
      piezoEventWaiting = true;
      piezoEventTime = now;
      piezoPeak = peakToPeak;
    }
  }
}


void readIr(
  unsigned long now
) {
  int sensorState =
    digitalRead(IR_PIN);

  bool beamBroken = (
    sensorState != clearIrState
  );

  if (!beamBroken) {
    if (beamWasBroken) {
      unsigned long breakDuration =
        now - beamBreakStart;

      if (
        irArmed
        && breakDuration
           >= MINIMUM_BREAK_MS
        && breakDuration
           <= MAXIMUM_BREAK_MS
        && now - lastShotEventTime
           > SHOT_COOLDOWN_MS
      ) {
        irEventWaiting = true;
        irEventTime = now;

        latestValidBeamBreakMs =
          breakDuration;
      }
    }

    beamWasBroken = false;

    if (clearStateStartMs == 0) {
      clearStateStartMs = now;
    }

    if (
      now - clearStateStartMs
      >= REQUIRED_CLEAR_MS
    ) {
      irArmed = true;
    }

    return;
  }

  clearStateStartMs = 0;

  if (
    beamBroken
    && !beamWasBroken
  ) {
    beamBreakStart = now;
    beamWasBroken = true;
  }
}

// Event classification and output
void classifyEvents(
  unsigned long now
) {
  if (
    piezoEventWaiting
    && irEventWaiting
  ) {
    unsigned long difference;

    if (
      piezoEventTime > irEventTime
    ) {
      difference =
        piezoEventTime - irEventTime;
    } else {
      difference =
        irEventTime - piezoEventTime;
    }

    if (
      difference <= EVENT_WINDOW_MS
    ) {
      emitHoopRecord(
        now,
        "MAKE_WITH_RIM_CONTACT",
        "RIM",
        RESULT_RIM_MAKE,
        CONTACT_RIM,
        piezoPeak,
        latestValidBeamBreakMs
      );

      clearEvents(now);
      return;
    }
  }

  if (
    irEventWaiting
    && now - irEventTime
       > EVENT_WINDOW_MS
  ) {
    emitHoopRecord(
      now,
      "CLEAN_MAKE",
      "NONE",
      RESULT_CLEAN_MAKE,
      CONTACT_NONE,
      0,
      latestValidBeamBreakMs
    );

    clearEvents(now);
    return;
  }

  if (
    piezoEventWaiting
    && now - piezoEventTime
       > EVENT_WINDOW_MS
  ) {
    emitHoopRecord(
      now,
      "RIM_MISS",
      "RIM",
      RESULT_RIM_MISS,
      CONTACT_RIM,
      piezoPeak,
      0
    );

    clearEvents(now);
  }
}


void emitHoopRecord(
  unsigned long eventTimeMs,
  const char* result,
  const char* contact,
  uint8_t resultCode,
  uint8_t contactCode,
  int recordedPiezoPeak,
  unsigned long beamBreakMs
) {
  eventNumber++;

  String line =
    String("HOOP,")
    + String(eventNumber)
    + ","
    + String(eventTimeMs)
    + ","
    + String(result)
    + ","
    + String(contact)
    + ","
    + String(recordedPiezoPeak)
    + ",0,"
    + (
      recordedPiezoPeak > 0
      ? String("100.0")
      : String("0.0")
    )
    + ","
    + String(beamBreakMs);

  Serial.println(line);

  uint16_t safeEventNumber =
    static_cast<uint16_t>(
      eventNumber & 0xFFFF
    );

  uint16_t safePiezoPeak =
    static_cast<uint16_t>(
      constrain(
        recordedPiezoPeak,
        0,
        65535
      )
    );

  uint16_t safeBeamBreak =
    static_cast<uint16_t>(
      min(
        beamBreakMs,
        65535UL
      )
    );

  sendHoopBlePacket(
    safeEventNumber,
    eventTimeMs,
    resultCode,
    contactCode,
    safePiezoPeak,
    safeBeamBreak
  );
}


void clearEvents(
  unsigned long now
) {
  piezoEventWaiting = false;
  irEventWaiting = false;

  piezoPeak = 0;
  latestValidBeamBreakMs = 0;

  lastShotEventTime = now;

  irArmed = false;
  clearStateStartMs = 0;
}
