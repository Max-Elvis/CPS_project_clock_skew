#include <SPI.h>
#include <mcp_can.h>

#define CAN_CS 10

// ---- Node configuration ------------------------------------------------
#if defined(NODE_A)
  const unsigned long IDS[] = {0x11, 0x13};
#elif defined(NODE_B)
  const unsigned long IDS[] = {0x55};
#else
  #error "Define NODE_A or NODE_B in build_flags"
#endif
const byte NUM_IDS = sizeof(IDS) / sizeof(IDS[0]);

// Can shields have 8MHz clock
#define CAN_CLOCK MCP_8MHZ

#ifndef ATTACK_AT_S
  #define ATTACK_AT_S 400UL        // seconds after boot of this node
#endif

MCP_CAN CAN0(CAN_CS);

volatile bool tick = false;
volatile uint16_t missedTicks = 0;

// Fires every 50 ms, driven by the MCU clock
ISR(TIMER1_COMPA_vect) {
  if (tick) missedTicks++;   // previous frame not yet sent -> overrun
  tick = true;
}

void setupTimer1() {
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1  = 0;
  OCR1A  = 12499;                          // 16 MHz / 64 = 250 kHz; 12500 ticks = 50 ms
  TCCR1B = _BV(WGM12) | _BV(CS11) | _BV(CS10);  // CTC mode, prescaler 64
  TIMSK1 = _BV(OCIE1A);
  interrupts();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);

  if (CAN0.begin(MCP_ANY, CAN_500KBPS, CAN_CLOCK) != CAN_OK) {
    Serial.println("MCP2515 init FAILED");
    while (1);
  }
  CAN0.setMode(MCP_NORMAL);   // normal mode so the node ACKs other nodes' frames
  Serial.println("Sender ready");

  setupTimer1();
}

void loop() {
  static byte counter = 0;
  static byte blinkDiv = 0;
  static bool announced = false;

#ifdef ATTACK_MASQ_A
  static unsigned long last55 = 0;
  static unsigned int count55 = 0;
  static bool masq = false;
  while (CAN0.checkReceive() == CAN_MSGAVAIL) {
    unsigned long rid; byte rlen; byte rbuf[8];
    CAN0.readMsgBuf(&rid, &rlen, rbuf);
    if (rid == 0x55) { last55 = millis(); count55++; }
  }
  // take over only after 200+ frames seen and 300 ms of real silence
  if (!masq && count55 > 200 && millis() - last55 > 300) {
    masq = true;
    Serial.print("MASQUERADE ACTIVE at ms=");
    Serial.println(millis());
  }
#endif

  if (!tick) return;
  tick = false;

  bool attack = millis() >= ATTACK_AT_S * 1000UL;
  if (attack && !announced) {
    announced = true;
#if defined(ATTACK_SUSPEND) || defined(ATTACK_FABRICATE) || defined(ATTACK_MASQB)
    Serial.println("ATTACK ACTIVE");
#endif
  }

  byte data[8] = {counter, 0, 0, 0, 0, 0, 0, 0};

  for (byte i = 0; i < NUM_IDS; i++) {
#ifdef ATTACK_MASQ_B
    if (attack && IDS[i] == 0x55) continue;          // B goes silent on 0x55
#endif
#ifdef ATTACK_SUSPEND
    if (attack && IDS[i] == 0x11) continue;     // suspension: 0x11 goes silent, 0x13 keeps running
#endif
    byte st = CAN0.sendMsgBuf(IDS[i], 0, 8, data);
    if (st != CAN_OK) {
      Serial.print("TX error, id=0x");
      Serial.println(IDS[i], HEX);
    }
  }

#ifdef ATTACK_FABRICATE
  if (attack) {                                  // fabrication: B injects the ID normally owned by A
    byte fake[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    CAN0.sendMsgBuf(0x11, 0, 8, fake);
  }
#endif
#ifdef ATTACK_MASQ_A
  if (masq) CAN0.sendMsgBuf(0x55, 0, 8, data);       // A now sends B's ID, same period
#endif
  counter++;

  if (++blinkDiv >= 20) {
    blinkDiv = 0;
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    if (missedTicks) {
      Serial.print("missed ticks: ");
      Serial.println(missedTicks);
    }
  }
}