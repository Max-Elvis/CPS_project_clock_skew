#include <SPI.h>
#include <mcp_can.h>

#define CAN_INT 2
#define CAN_CLOCK MCP_8MHZ

MCP_CAN CAN0(10);

struct Rec { unsigned long t; unsigned long id; };
const byte BUF = 64;                    // power of two
volatile Rec ring[BUF];
volatile byte head = 0, tail = 0;
volatile unsigned int overflow = 0;

void canISR() {
  unsigned long t = micros();
  // INT is level-held: drain every pending frame so the line goes high again
  do {
    unsigned long id; byte len; byte rx[8];
    CAN0.readMsgBuf(&id, &len, rx);
    byte nh = (head + 1) & (BUF - 1);
    if (nh == tail) { overflow++; }
    else { ring[head].t = t; ring[head].id = id; head = nh; }
    t = micros();                       // a second pending frame gets a fresh (slightly late) stamp
  } while (!digitalRead(CAN_INT));
}

void setup() {
  Serial.begin(115200);
  pinMode(CAN_INT, INPUT);
  if (CAN0.begin(MCP_ANY, CAN_500KBPS, CAN_CLOCK) != CAN_OK) {
    Serial.println("# init FAILED"); while (1);
  }
  CAN0.setMode(MCP_LISTENONLY);         // A and B must stay powered to ACK each other
  attachInterrupt(digitalPinToInterrupt(CAN_INT), canISR, FALLING);
  Serial.println("# receiver ready");
  Serial.println("id,micros");
}

void loop() {
  static unsigned int lastOv = 0;
  while (tail != head) {
    unsigned long id, t;
    noInterrupts();
    id = ring[tail].id; t = ring[tail].t;
    tail = (tail + 1) & (BUF - 1);
    interrupts();
    Serial.print("0x"); Serial.print(id, HEX);
    Serial.print(','); Serial.println(t);
  }
  if (overflow != lastOv) {
    lastOv = overflow;
    Serial.print("# overflow "); Serial.println(lastOv);
  }
}